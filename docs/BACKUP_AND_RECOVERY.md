# SevaPath Backup and Recovery Runbook (Phase 5.3)

This document governs the operational architecture, automated procedures, disaster recovery protocols, and cryptographic boundaries for SevaPath's database backup and recovery infrastructure.

---

## 1. Architecture and Trust Boundaries

SevaPath employs a zero-trust offsite backup model designed around SQLite WAL mode, asymmetric Age/X25519 encryption, and Cloudflare R2 object storage.

```
+----------------------------------------------------------------------------------------------------+
|                                    SEVAPATH ARCHITECTURE BOUNDARY                                  |
|                                                                                                    |
|  [VPS Production Host (Unprivileged Daemon: sevapath)]                                             |
|  - Holds: /etc/sevapath/backup.pub (Age Public Key ONLY)                                           |
|  - Executes: backup.sh (VACUUM INTO -> Pre-encrypt Integrity -> Age Encrypt -> Upload)             |
|  - Status Assigned: PUBLISHED (Transport & ciphertext verified)                                    |
|  * STRICT BOUNDARY: VPS NEVER holds the Age private key and NEVER assigns OWNER_QUALIFIED.          |
|                                         |                                                          |
|                                         | rclone (Scoped Token: Object Read & Write)               |
|                                         v                                                          |
|  [Cloudflare R2 Object Storage (WORM Immutability)]                                                |
|  - verified/daily/     [Bucket Lock: 14 Days   | Lifecycle: 14 Days]                               |
|  - verified/weekly/    [Bucket Lock: 56 Days   | Lifecycle: 56 Days]                               |
|  - verified/protected/ [Bucket Lock: INDEFINITE| Lifecycle: DISABLED]                              |
|  - incoming/           [Bucket Lock: None      | Lifecycle: 24 Hours]                              |
|  - pointers/           [Bucket Lock: None      | Lifecycle: None]                                  |
|                                         |                                                          |
|                                         | Manual / Air-Gapped Retrieval                            |
|                                         v                                                          |
|  [Owner Recovery Workstation (Offline / Linux Isolated Memory)]                                    |
|  - Holds: Age Private Decryption Key (Escrowed in offline vault / password manager)                |
|  - Executes: Decryption -> Plaintext Hash Match -> SQLite PRAGMA integrity -> PRAGMA FK            |
|  - Maintains: Owner Qualification Ledger (Outside VPS and Outside R2)                              |
|  - Status Assigned: OWNER_QUALIFIED (Guarantees true post-decryption recoverability)               |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Six-Hourly Backup Schedule & Local Retention

Automated backups are triggered deterministically by `sevapath-backup.timer` on the host:
- **Execution Schedule:** `00:00, 06:00, 12:00, 18:00 UTC`
- **Snapshot Engine:** Non-blocking `VACUUM INTO` executing on live SQLite database in WAL mode.

### Local GFS Deduplication & Retention Invariant
The local volume `/var/backups/sevapath/archive/` satisfies decision **D-05** by maintaining **18 logical retention slots**:
- **4 Six-Hourly Slots:** The last 4 consecutive runs (covering 24 hours).
- **7 Daily Slots:** The first successful run of each day for the last 7 calendar days.
- **4 Weekly Slots:** The first successful run of Sunday for the last 4 calendar weeks.
- **3 Monthly Slots:** The first successful run of the 1st day for the last 3 calendar months.

#### Deterministic Deduplication Rule:
$$\text{KeepSet} = \text{Slots}_{\text{6h}} \cup \text{Slots}_{\text{daily}} \cup \text{Slots}_{\text{weekly}} \cup \text{Slots}_{\text{monthly}}$$
- **Retention Invariant:** An artifact is **never unlinked** if it remains a qualifying member of *any* active retention slot.
- **Inventory Reporting:** Because a single artifact (e.g. Sunday the 1st at 00:00 UTC) satisfies multiple slots simultaneously, the steady-state unique physical artifact count is strictly $\le 18$ (typically 11 to 14 files). The system reports slot coverage (18/18) and unique files separately.

---

## 3. Offsite Retention Tiers & Cloudflare R2 Bucket Lock Schema

### Cloudflare R2 Full Replacement Lock Specification
The Cloudflare R2 Bucket Lock API (`PUT /accounts/{account_id}/r2/buckets/{bucket_name}/lock`) **completely replaces the bucket's entire rule configuration**.

The complete production payload is specified below:

```json
{
  "rules": [
    {
      "id": "sevapath-protected-archives-indefinite",
      "enabled": true,
      "prefix": "verified/protected/",
      "condition": {
        "type": "Indefinite"
      }
    },
    {
      "id": "sevapath-protected-manifests-indefinite",
      "enabled": true,
      "prefix": "manifests/protected/",
      "condition": {
        "type": "Indefinite"
      }
    },
    {
      "id": "sevapath-weekly-archives-56d",
      "enabled": true,
      "prefix": "verified/weekly/",
      "condition": {
        "type": "Age",
        "max_age_seconds": 4838400
      }
    },
    {
      "id": "sevapath-weekly-manifests-56d",
      "enabled": true,
      "prefix": "manifests/weekly/",
      "condition": {
        "type": "Age",
        "max_age_seconds": 4838400
      }
    },
    {
      "id": "sevapath-daily-archives-14d",
      "enabled": true,
      "prefix": "verified/daily/",
      "condition": {
        "type": "Age",
        "max_age_seconds": 1209600
      }
    },
    {
      "id": "sevapath-daily-manifests-14d",
      "enabled": true,
      "prefix": "manifests/daily/",
      "condition": {
        "type": "Age",
        "max_age_seconds": 1209600
      }
    }
  ]
}
```

---

## 4. Monthly Promotion & Offsite Target Distinction

- **Monthly Promotion:** On each six-hourly run, `backup.sh` detects if the current UTC calendar month (`YYYY-MM`) has already been promoted. If not, the run is promoted to `verified/protected/` with a unique immutable name: `sevapath_backup_<YYYYMMDD_HHMMSS>_<UUID>.sqlite.enc`.
- **Monthly GFS Target:** Up to 12 independently owner-qualified monthly recovery points.
- **Hard Safety Floor:** At least **3 independently owner-qualified recovery points** must remain in `verified/protected/` at all times.
- **Shortfall Reporting:** If fewer than 12 qualified monthly points exist, telemetry must explicitly report the shortfall and never claim full GFS compliance.

---

## 5. Owner Pruning & Sequential Credential Rotation Protocol

Because `verified/protected/` is locked indefinitely, deleting obsolete monthly points (> 12 months old) requires owner administrative action. To prevent a compromised VPS from deleting unlocked archives during maintenance, the owner strictly adheres to this protocol:

### Mandatory Rehearsal Prerequisite
Before executing pruning against the production bucket, the owner **must rehearse the complete lock modification and deletion sequence on a separate disposable test bucket** (`sevapath-backups-test`).

### Production Pruning Sequence:
1. **Revoke VPS Token:** Revoke the active VPS token via Cloudflare Dashboard / API.
2. **Negative Authorization Verification:** Send a signed S3 request (`GET /sevapath-backups?list-type=2&max-keys=1`) with the old token. **Must fail with HTTP 401 `Unauthorized`**. (Reject 403 `AccessDenied` or network errors as proof).
3. **Archive Rule Configuration:** Query and save `GET /accounts/{id}/r2/buckets/sevapath-backups/lock` to `~/.sevapath/lock_rules_backup_<TS>.json`.
4. **Audit Qualification Ledger:** Verify that target deletion will leave $\ge 3$ qualified recovery points and $\ge 12$ points (unless owner approves reduced coverage).
5. **Adjust Rule & Prune:** Submit replacement configuration temporarily removing the target rule; delete only the eligible obsolete objects.
6. **Restore Indefinite Lock:** Submit the complete production rule payload restoring `Indefinite` lock on `verified/protected/`.
7. **Read-Back Verification:** Query `GET /lock`. Confirm `rule.enabled === true`, `rule.condition.type === "Indefinite"`, and exact prefixes.
8. **Enforcement Probe:** Attempt an overwrite on an existing protected object; confirm it fails with **HTTP 409 `ObjectLockedByBucketPolicy`**.
9. **Fail-Closed Rollback:** If read-back or enforcement probe fails, immediately submit the archived rule configuration. If rollback fails, **halt all automation and escalate to manual intervention**. Never assume rollback succeeded.
10. **Reissue VPS Token:** Only after step 8 passes, issue a new scoped VPS API token.

---

## 6. Verification Boundaries: VPS Publication vs. Owner Qualification

| Attribute | VPS Publication Verification (`backup.sh` / `verify_backup.py`) | Owner Recovery Qualification (`verify_backup.py --qualify`) |
| :--- | :--- | :--- |
| **Executing Environment** | VPS Production Host | Owner Workstation (Isolated Linux Memory) |
| **Key Required** | None (VPS holds Age Public Key only) | Age Private Decryption Key |
| **Integrity Checks** | Pre-encryption SQLite checks & remote ciphertext SHA-256 match | Post-decryption SQLite `integrity_check` & `foreign_key_check` |
| **Assigned Status** | `PUBLISHED` / `VERIFIED_CIPHERTEXT` | `OWNER_QUALIFIED` |
| **Authority** | Proves publication & transport integrity | Sole authority for Safety Floor ($\ge 3$) and GFS compliance |

---

## 7. Two-Phase Restore Procedure & Safety Gates

Database restoration on the host (`deployment/scripts/restore_backup.sh`) operates under strict fail-closed constraints:

```bash
sudo /opt/sevapath/deployment/scripts/restore_backup.sh --candidate /path/to/decrypted_candidate.sqlite
```

### Safety Gates:
1. **Gate 1 (Pre-Shutdown Space Check):**
   - Validates available space on `/var/lib/sevapath` while `sevapath.service` is active:
     $$\text{Free Space} \ge 2 \times S_{\text{DB}} + S_{\text{WAL}} + 20\text{ MB}$$
   - If insufficient, aborts immediately. Zero service downtime.
2. **Graceful Shutdown & Process Inspection:**
   - Stops `sevapath.service`.
   - Inspects open file descriptors via `fuser` / `lsof`. If processes linger after 15 seconds, **strictly refuses `kill -9`**, restarts the service safely, and aborts.
3. **Gate 2 (Post-Shutdown Re-verification):**
   - Re-measures exact database and WAL sizes.
   - If space is insufficient, leaves the database untouched, restarts the service, and aborts.
4. **Safety Copy Preservation:**
   - Copies live `sevapath.sqlite`, `-wal`, and `-shm` to `/var/backups/sevapath/pre_restore_safety_<TS>/`.
5. **Atomic Swap & In-Place Verification:**
   - Atomically replaces database file, unlinks stale WAL/SHM sidecars, verifies SQLite integrity, restarts service, and probes `http://127.0.0.1:8000/health?check=ready`.
   - If any check fails, automatically rolls back to the safety copy.

---

## 8. Hardened Recovery Workstation tmpfs Procedure (Linux-Only)

> **PLATFORM NOTICE:** This procedure requires Linux kernel interfaces (`/proc/swaps`, `tmpfs`, `findmnt`). macOS is **strictly unsupported** due to unconfigurable kernel virtual memory paging.

### Step-by-Step Operator Procedure:

```bash
#!/bin/bash
set -euo pipefail

DB_PATH="/var/lib/sevapath/sevapath.sqlite"

# 1. Strict size measurement (fail-closed, no hard-coded fallback)
if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database file missing. Aborting." >&2; exit 1
fi
DB_BYTES=$(stat -c%s "$DB_PATH" 2>/dev/null || echo 0)
if [ "$DB_BYTES" -le 0 ]; then
    echo "ERROR: Invalid database size ($DB_BYTES). Aborting." >&2; exit 1
fi

S_DB_MB=$(( (DB_BYTES + 1048575) / 1048576 ))
CALCULATED_MB=$(( 4 * S_DB_MB + 10 ))
REQUIRED_TMPFS_MB=$(( CALCULATED_MB < 32 ? 32 : CALCULATED_MB ))

# 2. Check RAM availability before touching swap
AVAILABLE_RAM_MB=$(free -m | awk '/Mem:/ { print $7 }')
MAX_ALLOWED_TMPFS_MB=$(( AVAILABLE_RAM_MB / 2 ))
if [ $MAX_ALLOWED_TMPFS_MB -gt 512 ]; then MAX_ALLOWED_TMPFS_MB=512; fi

if [ $REQUIRED_TMPFS_MB -gt $MAX_ALLOWED_TMPFS_MB ]; then
    echo "ERROR: Required tmpfs (${REQUIRED_TMPFS_MB}MB) exceeds allowed maximum (${MAX_ALLOWED_TMPFS_MB}MB)." >&2; exit 1
fi
if [ $AVAILABLE_RAM_MB -lt $(( 2 * REQUIRED_TMPFS_MB )) ]; then
    echo "ERROR: Insufficient RAM. Aborting." >&2; exit 1
fi

# 3. Fail-closed swap precondition (Must be disabled manually beforehand)
ACTIVE_SWAPS=$(tail -n +2 /proc/swaps 2>/dev/null | wc -l)
if [ "$ACTIVE_SWAPS" -ne 0 ]; then
    echo "ERROR: Active swap detected. Recovery must occur on a system with swap disabled." >&2
    echo "Execute 'sudo swapoff -a' manually after evaluating memory, then retry." >&2
    exit 1
fi

# 4. Mount with explicit operator ownership and restrictive mode
MOUNT_POINT="/mnt/secure-recovery"
sudo mkdir -p "$MOUNT_POINT"
sudo mount -t tmpfs \
    -o size="${REQUIRED_TMPFS_MB}M",mode=0700,uid="$(id -u)",gid="$(id -g)" \
    tmpfs "$MOUNT_POINT"

# 5. Signal-safe idempotent cleanup trap
ORIGINAL_STATUS=0
CLEANUP_INVOKED=0

cleanup() {
    local exit_status=$?
    trap - EXIT INT TERM HUP
    if [ "$CLEANUP_INVOKED" -eq 1 ]; then exit "$exit_status"; fi
    CLEANUP_INVOKED=1
    if [ "$ORIGINAL_STATUS" -ne 0 ]; then exit_status="$ORIGINAL_STATUS"; fi

    echo "Cleaning up recovery workspace..." >&2
    if awk -v target="$MOUNT_POINT" '$2 == target && $3 == "tmpfs" { found=1 } END { exit !found }' /proc/mounts; then
        find "$MOUNT_POINT" -mindepth 1 -delete 2>/dev/null || true
        sudo umount "$MOUNT_POINT" 2>/dev/null || {
            echo "ALERT: umount failed (target busy). FORCED UNMOUNT IS FORBIDDEN." >&2
            fuser -v "$MOUNT_POINT" 2>/dev/null || true
            exit_status=1
        }
    fi
    exit "$exit_status"
}

trap "ORIGINAL_STATUS=130; exit 130" INT
trap "ORIGINAL_STATUS=143; exit 143" TERM
trap "ORIGINAL_STATUS=129; exit 129" HUP
trap cleanup EXIT

# 6. Execute Age Decryption and SQLite Validation in $MOUNT_POINT
# ...
```

#### Forensic DRAM Limitation Notice:
Neither file unlinking via `find ... -delete`, `tmpfs` unmounting, nor host reboot guarantees physical erasure of RAM. Volatile memory remanence and cold-boot vulnerabilities persist until electrical charge in physical DRAM capacitors fully dissipates.

---

## 9. RPO, RTO and Service Level Objectives

- **Target Provisional RPO:** $\le 6\text{ hours}$ (governed by six-hourly UTC schedule). Calculated from the latest owner-qualified offsite recovery point, distinguishing publication timestamp from owner qualification timestamp.
- **Target Provisional Local RTO:** $\le 15\text{ minutes}$ (local database restoration via `restore_backup.sh`).
- **Target Provisional Disaster RTO:** $\le 30\text{ minutes}$ (retrieval from Cloudflare R2, decryption on recovery workstation, and host restoration).
- **Provisional Notice:** These targets represent architectural design criteria; they are **not claimed as proven** until demonstrated through scheduled disaster-recovery drills.

---

## 10. Known Risks & Deferred Phase 5.4 Work

1. **Upload Abuse on Protected Prefix:** Because Cloudflare S3 tokens cannot restrict `PutObject` on specific prefixes, a compromised VPS could upload arbitrary junk objects to `verified/protected/`.
   - *Mitigation:* The owner qualification ledger filters out unverified uploads; Cloudflare billing alerts flag anomalous storage growth.
   - *Deferred Work:* Delegating protected promotion exclusively to an owner CI/CD runner is deferred to Phase 5.4.
2. **Manual Pruning Overhead:** Pruning requires sequential token revocation and rule restoration.
   - *Status:* Accepted security trade-off to avoid complex external KMS dependencies.
