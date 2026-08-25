#!/usr/bin/env python3
"""
Master Encryption Key Rotation Utility

Use this script to re-encrypt all stored tenant PhonePe secrets when rotating
MASTER_ENCRYPTION_KEY.

Usage:
    python scripts/rotate_master_key.py --old-key "<OLD_FERNET_KEY>" --new-key "<NEW_FERNET_KEY>"
"""

import argparse
import asyncio
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decrypt_secret, encrypt_secret
from app.database import AsyncSessionLocal
from app.models.tenant import Tenant


async def rotate_keys(old_key: str, new_key: str):
    print("Connecting to database...")
    async with AsyncSessionLocal() as session:
        query = select(Tenant)
        result = await session.execute(query)
        tenants = result.scalars().all()

        print(f"Found {len(tenants)} tenant(s) to re-encrypt.")
        re_encrypted_count = 0

        for tenant in tenants:
            try:
                # Decrypt with old key
                decrypted_secret = decrypt_secret(tenant.phonepe_client_secret, custom_key=old_key)
                try:
                    decrypted_client_id = decrypt_secret(tenant.phonepe_client_id, custom_key=old_key)
                except Exception:
                    decrypted_client_id = tenant.phonepe_client_id

                # Encrypt with new key
                tenant.phonepe_client_secret = encrypt_secret(decrypted_secret, custom_key=new_key)
                tenant.phonepe_client_id = encrypt_secret(decrypted_client_id, custom_key=new_key)
                re_encrypted_count += 1
                print(f"  [OK] Re-encrypted secrets for tenant ID: {tenant.id} ({tenant.name})")
            except Exception as e:
                print(f"  [ERROR] Failed to re-encrypt tenant {tenant.id}: {e}", file=sys.stderr)
                await session.rollback()
                sys.exit(1)

        await session.commit()
        print(f"\nSuccessfully rotated encryption keys for {re_encrypted_count} tenant(s).")
        print("Remember to update MASTER_ENCRYPTION_KEY in your .env / production secrets manager!")


def main():
    parser = argparse.ArgumentParser(description="Rotate PhonePe Gateway Master Encryption Key")
    parser.add_argument("--old-key", required=True, help="Current MASTER_ENCRYPTION_KEY")
    parser.add_argument("--new-key", required=True, help="New MASTER_ENCRYPTION_KEY")
    args = parser.parse_args()

    asyncio.run(rotate_keys(args.old_key, args.new_key))


if __name__ == "__main__":
    main()
