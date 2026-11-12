import sqlite3
import os
from contextlib import contextmanager
from typing import Generator

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "argus.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Merchants Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS merchants (
            id TEXT PRIMARY KEY,
            paypal_merchant_id TEXT UNIQUE NOT NULL,
            legal_business_name TEXT NOT NULL,
            identity_status TEXT NOT NULL DEFAULT 'PENDING',
            overall_reputation_score INTEGER NOT NULL DEFAULT 50,
            verified_at TEXT,
            created_at TEXT NOT NULL
        );
        """)
        
        # 2. Websites Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS websites (
            id TEXT PRIMARY KEY,
            root_domain TEXT UNIQUE NOT NULL,
            tld TEXT NOT NULL,
            dns_hash TEXT,
            cert_fingerprint TEXT,
            has_mandatory_policies INTEGER NOT NULL DEFAULT 0,
            catalog_depth INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            last_scraped_at TEXT
        );
        """)
        
        # 3. Merchant-Website Associations Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS merchant_websites (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            website_id TEXT NOT NULL,
            brand_name_claimed TEXT NOT NULL,
            association_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            trust_score INTEGER NOT NULL DEFAULT 0,
            verified_at TEXT,
            expires_at TEXT,
            evidence_dossier TEXT,
            FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE,
            FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE CASCADE,
            UNIQUE(merchant_id, website_id)
        );
        """)
        
        # 4. Verification Jobs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS verification_jobs (
            id TEXT PRIMARY KEY,
            website_id TEXT,
            target_url TEXT NOT NULL,
            job_status TEXT NOT NULL DEFAULT 'PENDING',
            subscribers_count INTEGER NOT NULL DEFAULT 1,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE SET NULL
        );
        """)
        
        # 5. Audit Logs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            transaction_id TEXT UNIQUE NOT NULL,
            merchant_id TEXT,
            website_id TEXT,
            brand_name TEXT NOT NULL,
            target_url TEXT NOT NULL,
            product_name TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            trust_score INTEGER NOT NULL,
            verdict TEXT NOT NULL,
            merchant_state TEXT NOT NULL,
            latency_ms REAL NOT NULL,
            evidence_json TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE SET NULL,
            FOREIGN KEY (website_id) REFERENCES websites(id) ON DELETE SET NULL
        );
        """)
        
        # 6. Appeals Table (Merchant Grievance & Dispute Resolution)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS appeals (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            incident_reference_id TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN',
            reason_category TEXT NOT NULL,
            statement TEXT NOT NULL,
            submitted_documents TEXT,
            resolution_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE
        );
        """)
        
        # Create indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mw_lookup ON merchant_websites(merchant_id, website_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_website_domain ON websites(root_domain);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_merchant_paypal ON merchants(paypal_merchant_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status);")

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
