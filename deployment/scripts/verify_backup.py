#!/usr/bin/env python3
"""
SevaPath Backup Verification Utility (Phase 5.3)

Provides two distinct verification boundaries:
1. Publication Verification (VPS-side):
   Validates manifest structure, file sizes, local/remote ciphertext SHA-256.
   Does NOT require the Age private key. Status: PUBLISHED.

2. Recovery Qualification (Owner Recovery Workstation):
   Decrypts candidate using the independently escrowed Age private key in secure memory.
   Verifies plaintext SHA-256 against manifest, executes SQLite integrity_check and
   foreign_key_check. Generates qualification audit record for Owner Qualification Ledger.
   Status: OWNER_QUALIFIED.
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile


def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest_schema(manifest: dict) -> None:
    required_keys = [
        "backup_id", "created_at", "schema_version", "database_bytes",
        "database_sha256", "ciphertext_bytes", "ciphertext_sha256",
        "integrity_check", "foreign_key_check", "status"
    ]
    for k in required_keys:
        if k not in manifest:
            raise ValueError(f"Manifest missing required key: {k}")
    if manifest["integrity_check"] != "ok":
        raise ValueError(f"Manifest integrity_check is not ok: {manifest['integrity_check']}")
    if manifest["foreign_key_check"] != "ok":
        raise ValueError(f"Manifest foreign_key_check is not ok: {manifest['foreign_key_check']}")


def verify_publication(manifest_path: str, ciphertext_path: str) -> dict:
    """VPS Publication Verification: No private key used."""
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    if not os.path.isfile(ciphertext_path):
        raise FileNotFoundError(f"Ciphertext not found: {ciphertext_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    verify_manifest_schema(manifest)

    actual_cipher_bytes = os.path.getsize(ciphertext_path)
    if actual_cipher_bytes != manifest["ciphertext_bytes"]:
        raise ValueError(
            f"Ciphertext size mismatch: expected {manifest['ciphertext_bytes']}, got {actual_cipher_bytes}"
        )

    actual_cipher_hash = sha256_file(ciphertext_path)
    if actual_cipher_hash != manifest["ciphertext_sha256"]:
        raise ValueError(
            f"Ciphertext SHA-256 mismatch: expected {manifest['ciphertext_sha256']}, got {actual_cipher_hash}"
        )

    return {
        "status": "PUBLISHED",
        "backup_id": manifest["backup_id"],
        "ciphertext_sha256": actual_cipher_hash,
        "ciphertext_bytes": actual_cipher_bytes,
        "publication_verified": True
    }


def qualify_recovery(manifest_path: str, ciphertext_path: str, private_key_file: str, workspace_dir: str = None) -> dict:
    """Owner Recovery Workstation Qualification: Full decryption and database integrity checks."""
    if not os.path.isfile(private_key_file):
        raise FileNotFoundError(f"Private key file not found: {private_key_file}")

    pub_result = verify_publication(manifest_path, ciphertext_path)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    temp_dir = tempfile.mkdtemp(prefix="sevapath_qualify_", dir=workspace_dir)
    decrypted_db = os.path.join(temp_dir, "candidate.sqlite")

    try:
        # Decrypt with age
        cmd = ["age", "--decrypt", "-i", private_key_file, "-o", decrypted_db, ciphertext_path]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Age decryption failed: {proc.stderr.strip()}")

        actual_db_bytes = os.path.getsize(decrypted_db)
        if actual_db_bytes != manifest["database_bytes"]:
            raise ValueError(
                f"Decrypted database size mismatch: expected {manifest['database_bytes']}, got {actual_db_bytes}"
            )

        actual_db_hash = sha256_file(decrypted_db)
        if actual_db_hash != manifest["database_sha256"]:
            raise ValueError(
                f"Decrypted database SHA-256 mismatch: expected {manifest['database_sha256']}, got {actual_db_hash}"
            )

        # Run SQLite PRAGMA checks on decrypted database
        conn = sqlite3.connect(decrypted_db)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            integrity_rows = cursor.fetchall()
            if not integrity_rows or integrity_rows[0][0] != "ok":
                raise ValueError(f"SQLite PRAGMA integrity_check failed: {integrity_rows}")

            cursor.execute("PRAGMA foreign_key_check;")
            fk_violations = cursor.fetchall()
            if fk_violations:
                raise ValueError(f"SQLite PRAGMA foreign_key_check violations: {fk_violations}")

            # Verify core table existence
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            for expected_table in ["services", "requirements"]:
                if expected_table not in tables:
                    raise ValueError(f"Decrypted database missing expected table: {expected_table}")
        finally:
            conn.close()

        # Build qualification ledger entry
        ledger_entry = {
            "backup_id": manifest["backup_id"],
            "status": "OWNER_QUALIFIED",
            "qualified_at": manifest["created_at"],
            "database_sha256": actual_db_hash,
            "database_bytes": actual_db_bytes,
            "ciphertext_sha256": pub_result["ciphertext_sha256"],
            "ciphertext_bytes": pub_result["ciphertext_bytes"],
            "integrity_check": "ok",
            "foreign_key_check": "ok",
            "qualified_by": "owner-recovery-workstation"
        }
        return ledger_entry

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="SevaPath Backup Verification Utility")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON file")
    parser.add_argument("--ciphertext", required=True, help="Path to encrypted .sqlite.enc file")
    parser.add_argument("--qualify", action="store_true", help="Perform full owner recovery qualification")
    parser.add_argument("--private-key", help="Path to Age private key (required with --qualify)")
    parser.add_argument("--workspace", help="Optional scratch/tmpfs directory for qualification")

    args = parser.parse_args()

    try:
        if args.qualify:
            if not args.private_key:
                print("ERROR: --private-key is required when using --qualify", file=sys.stderr)
                sys.exit(1)
            result = qualify_recovery(args.manifest, args.ciphertext, args.private_key, args.workspace)
            print(json.dumps(result, indent=2))
            print("QUALIFICATION VERDICT: OWNER_QUALIFIED")
        else:
            result = verify_publication(args.manifest, args.ciphertext)
            print(json.dumps(result, indent=2))
            print("PUBLICATION VERDICT: PUBLISHED (Ciphertext verified; not owner-qualified)")
        sys.exit(0)
    except Exception as e:
        print(f"VERIFICATION FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
