import sqlite3

conn = sqlite3.connect(r'X:\hackathon\Veritas\veritas.db')
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
print(f"Created tables count: {len(tables)}")
print(sorted(tables))
