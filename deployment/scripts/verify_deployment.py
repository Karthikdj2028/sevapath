#!/usr/bin/env python3
"""
SevaPath Deployment Diagnostic and Verification Tool.

Usage:
    python3 verify_deployment.py --check-liveness [--url URL]
    python3 verify_deployment.py --check-readiness [--url URL]
    python3 verify_deployment.py --check-scratch-write INSTANCE_DIR
    python3 verify_deployment.py --check-lock-diagnostic DB_PATH
    python3 verify_deployment.py --check-snapshot-integrity SNAPSHOT_PATH
"""

import sys
import os
import uuid
import sqlite3
import argparse
import urllib.request
import urllib.error


def check_liveness(url: str = "http://127.0.0.1:8000/health") -> bool:
    """Verifies HTTP liveness check endpoint returns 200 without database reliance."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SevaPath-Deployment-Verifier"})
        with urllib.request.urlopen(req, timeout=5) as res:
            if res.status == 200:
                print(f"Liveness OK: {url} returned HTTP 200")
                return True
            print(f"Liveness FAILED: {url} returned HTTP {res.status}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Liveness FAILED: Could not connect to {url}: {e}", file=sys.stderr)
        return False


def check_readiness(url: str = "http://127.0.0.1:8000/health?check=ready") -> bool:
    """Verifies HTTP readiness check endpoint returns 200 with database connectivity."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SevaPath-Deployment-Verifier"})
        with urllib.request.urlopen(req, timeout=5) as res:
            if res.status == 200:
                print(f"Readiness OK: {url} returned HTTP 200")
                return True
            print(f"Readiness FAILED: {url} returned HTTP {res.status}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Readiness FAILED: Could not connect to {url}: {e}", file=sys.stderr)
        return False


def check_scratch_write(instance_dir: str) -> bool:
    """Creates a unique temporary SQLite file in instance_dir, verifies rw, and deletes it."""
    if not os.path.isdir(instance_dir):
        print(f"Scratch write FAILED: Directory {instance_dir} does not exist", file=sys.stderr)
        return False

    probe_id = uuid.uuid4().hex
    temp_db_path = os.path.join(instance_dir, f".probe_{probe_id}.sqlite")

    try:
        conn = sqlite3.connect(temp_db_path, timeout=5.0)
        conn.execute("CREATE TABLE _probe (id INTEGER PRIMARY KEY, msg TEXT);")
        conn.execute("INSERT INTO _probe (msg) VALUES ('probe_test');")
        conn.commit()
        row = conn.execute("SELECT msg FROM _probe WHERE id = 1;").fetchone()
        conn.close()

        if row and row[0] == "probe_test":
            print(f"Scratch write OK: Verified write/read on {temp_db_path}")
            return True
        else:
            print(f"Scratch write FAILED: Verification value mismatch in {temp_db_path}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Scratch write FAILED: Exception on {temp_db_path}: {e}", file=sys.stderr)
        return False
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.unlink(temp_db_path)
            except OSError as cleanup_err:
                print(f"WARNING: Cleanup failed for {temp_db_path}: {cleanup_err}", file=sys.stderr)


def check_lock_diagnostic(db_path: str) -> bool:
    """Attempts BEGIN IMMEDIATE; ROLLBACK; against production database to verify write-lock availability."""
    if not os.path.isfile(db_path):
        print(f"Lock diagnostic SKIPPED: Database {db_path} does not exist yet (fresh install)")
        return True

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("ROLLBACK;")
        conn.close()
        print(f"Lock diagnostic OK: Successfully acquired and released write-lock on {db_path}")
        return True
    except Exception as e:
        print(f"Lock diagnostic FAILED: Could not acquire write-lock on {db_path}: {e}", file=sys.stderr)
        return False


def check_snapshot_integrity(snapshot_path: str) -> bool:
    """Verifies PRAGMA integrity_check and PRAGMA foreign_key_check on an offline snapshot."""
    if not os.path.isfile(snapshot_path):
        print(f"Snapshot integrity FAILED: File {snapshot_path} does not exist", file=sys.stderr)
        return False

    try:
        conn = sqlite3.connect(snapshot_path)
        cur = conn.cursor()
        integrity = cur.execute("PRAGMA integrity_check;").fetchone()
        fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
        conn.close()

        if integrity and integrity[0] == "ok" and not fk_violations:
            print(f"Snapshot integrity OK: {snapshot_path} passed integrity and foreign key checks")
            return True
        else:
            print(
                f"Snapshot integrity FAILED: {snapshot_path} (integrity={integrity}, fk_violations={fk_violations})",
                file=sys.stderr
            )
            return False
    except Exception as e:
        print(f"Snapshot integrity FAILED on {snapshot_path}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="SevaPath Deployment Diagnostic and Verification Tool")
    parser.add_argument("--check-liveness", action="store_true", help="Check HTTP liveness probe")
    parser.add_argument("--check-readiness", action="store_true", help="Check HTTP readiness probe")
    parser.add_argument("--url", default=None, help="Custom URL for HTTP checks")
    parser.add_argument("--check-scratch-write", metavar="INSTANCE_DIR", help="Verify filesystem scratch writeability")
    parser.add_argument("--check-lock-diagnostic", metavar="DB_PATH", help="Verify SQLite write-lock acquisition")
    parser.add_argument("--check-snapshot-integrity", metavar="SNAPSHOT_PATH", help="Verify offline SQLite snapshot")

    args = parser.parse_args()
    success = True

    if args.check_liveness:
        target_url = args.url or "http://127.0.0.1:8000/health"
        success = success and check_liveness(target_url)

    if args.check_readiness:
        target_url = args.url or "http://127.0.0.1:8000/health?check=ready"
        success = success and check_readiness(target_url)

    if args.check_scratch_write:
        success = success and check_scratch_write(args.check_scratch_write)

    if args.check_lock_diagnostic:
        success = success and check_lock_diagnostic(args.check_lock_diagnostic)

    if args.check_snapshot_integrity:
        success = success and check_snapshot_integrity(args.check_snapshot_integrity)

    if not any([args.check_liveness, args.check_readiness, args.check_scratch_write,
                args.check_lock_diagnostic, args.check_snapshot_integrity]):
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
