#!/usr/bin/env python3
"""Secure interactive PayPal Sandbox configuration tool for VERITAS.

Prompts for PayPal credentials using non-echoing hidden terminal input (getpass),
validates them against the PayPal Sandbox REST API, and updates backend/.env safely.
Never prints or logs the client secret or raw access tokens.
"""

import getpass
import os
import re
import sys
import httpx


def print_banner():
    print("=" * 70)
    print("  VERITAS — PayPal Sandbox Configuration Assistant")
    print("=" * 70)
    print("Instructions to obtain PayPal Sandbox credentials:")
    print("  1. Log in to https://developer.paypal.com")
    print("  2. Navigate to 'Apps & Credentials' in the Sandbox environment.")
    print("  3. Create an App or select your Default Application.")
    print("  4. Copy your 'Client ID' and 'Secret'.")
    print("  5. (Optional) In Webhooks, register your endpoint:")
    print("     https://<your-domain>/api/v1/payments/paypal/webhook")
    print("     and copy the generated Webhook ID.")
    print("=" * 70)
    print()


def verify_sandbox_credentials(client_id: str, client_secret: str, base_url: str) -> bool:
    """Validate credentials against PayPal OAuth2 endpoint."""
    print("Verifying credentials against PayPal Sandbox OAuth2 endpoint...")
    token_url = f"{base_url.rstrip('/')}/v1/oauth2/token"
    try:
        response = httpx.post(
            token_url,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            timeout=15.0,
        )
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                print("SUCCESS: Authenticated with PayPal Sandbox successfully! (Token acquired)")
                return True
        print(f"FAILED: PayPal returned status {response.status_code}: {response.text}")
        return False
    except Exception as e:
        print(f"ERROR: Unable to connect to PayPal API: {e}")
        return False


def update_env_file(env_path: str, updates: dict[str, str]):
    """Update or append environment variables in .env without losing existing lines."""
    if not os.path.exists(env_path):
        lines = []
    else:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        matched = False
        for key, val in updates.items():
            if re.match(rf"^{key}\s*=", line):
                new_lines.append(f"{key}={val}\n")
                updated_keys.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"Updated configuration saved securely to {env_path}")


def main():
    print_banner()

    client_id = input("Enter PayPal Sandbox Client ID: ").strip()
    if not client_id:
        print("Error: Client ID cannot be empty.")
        sys.exit(1)

    client_secret = getpass.getpass("Enter PayPal Sandbox Client Secret (hidden, no-echo): ").strip()
    if not client_secret:
        print("Error: Client Secret cannot be empty.")
        sys.exit(1)

    webhook_id = input("Enter PayPal Webhook ID (optional, press Enter to skip): ").strip()
    receiver_account = input("Enter Sandbox Merchant Receiver Email (optional, press Enter to default): ").strip()
    if not receiver_account:
        receiver_account = "merchant_sandbox@veritas.local"

    base_url = "https://api-m.sandbox.paypal.com"
    is_valid = verify_sandbox_credentials(client_id, client_secret, base_url)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.abspath(os.path.join(script_dir, ".."))
    env_path = os.path.join(backend_dir, ".env")

    updates = {
        "PAYPAL_CLIENT_ID": client_id,
        "PAYPAL_CLIENT_SECRET": client_secret,
        "PAYPAL_BASE_URL": base_url,
        "PAYPAL_WEBHOOK_ID": webhook_id,
        "PAYPAL_ENVIRONMENT": "sandbox",
        "PAYPAL_RECEIVER_ACCOUNT": receiver_account,
        "MOCK_PAYPAL": "false" if is_valid else "true",
    }

    update_env_file(env_path, updates)
    if is_valid:
        print("\nPayPal Sandbox is now LIVE and configured for VERITAS ACCORD settlement!")
    else:
        print("\nNote: Credentials could not be validated. MOCK_PAYPAL is set to true for safety.")


if __name__ == "__main__":
    main()

