"""
Administrative Command-Line Interface.

This module provides a secure, out-of-band method for managing the API's zero-trust 
boundary. It allows server administrators to generate, list, and revoke UUID-based 
Bearer tokens via the local terminal without exposing authentication endpoints 
to the public web.
"""

import argparse
import sqlite3
import uuid
from datetime import datetime

from core.config import settings
from core.security import init_db

def create_key(client_name: str):
    """
    Generates a new UUID v4 API key and provisions it in the database.
    
    Args:
        client_name (str): A descriptive identifier for the system or user 
            that will authenticate with this key.
    """
    init_db()
    new_key = f"mdserver_{uuid.uuid4().hex}"
    
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(settings.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO api_keys (key_value, client_name) VALUES (?, ?)",
                (new_key, client_name)
            )
            conn.commit()
            
        print("\n" + "="*50)
        print(f"✅ API Key Successfully Generated for: {client_name}")
        print("="*50)
        print(f"Key: {new_key}")
        print("="*50)
        print("Store this key securely. It is required for the Authorization header.\n")
        
    except sqlite3.Error as e:
        print(f"❌ Failed to create API key. Database error: {e}")

def list_keys():
    """
    Retrieves and displays a formatted table of all provisioned API keys.
    
    Provides administrators with a quick overview of active and revoked 
    tokens, their creation dates, and truncated key previews for auditing.
    """
    init_db()
    try:
        with sqlite3.connect(settings.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, client_name, is_active, created_at, key_value FROM api_keys")
            rows = cursor.fetchall()
            
        print("\n" + "="*80)
        print(f"{'ID':<5} | {'Client Name':<25} | {'Status':<10} | {'Created At':<20} | {'Key Preview'}")
        print("="*80)
        
        for row in rows:
            status = "Active" if row[2] else "Revoked"
            masked_key = f"{row[4][:12]}..."
            print(f"{row[0]:<5} | {row[1]:<25} | {status:<10} | {row[3][:19]:<20} | {masked_key}")
            
        print("="*80 + "\n")
        
    except sqlite3.Error as e:
        print(f"❌ Failed to read API keys. Database error: {e}")

def revoke_key(key_id: int):
    """
    Immediately revokes access for a specific API key.
    
    Instead of deleting the record, this soft-deletes the key by setting 
    its `is_active` flag to 0, preserving the security audit trail.
    
    Args:
        key_id (int): The database primary key ID of the token to revoke.
    """
    try:
        with sqlite3.connect(settings.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
            if cursor.rowcount == 0:
                print(f"❌ Key ID {key_id} not found.")
            else:
                conn.commit()
                print(f"✅ Successfully revoked Key ID: {key_id}")
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MDServer Security Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create Key Command
    parser_create = subparsers.add_parser("create-key", help="Create a new API key")
    parser_create.add_argument("--client", required=True, help="Name of the client/system using this key")

    parser_revoke = subparsers.add_parser("revoke-key", help="Revoke an active API key")
    parser_revoke.add_argument("--id", type=int, required=True, help="The ID of the key to revoke")

    # List Keys Command
    parser_list = subparsers.add_parser("list-keys", help="List all API keys")

    args = parser.parse_args()

    if args.command == "create-key":
        create_key(args.client)
    elif args.command == "list-keys":
        list_keys()
    elif args.command == "revoke-key":
        revoke_key(args.id)
    else:
        parser.print_help()