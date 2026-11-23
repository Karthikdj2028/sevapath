#!/bin/bash
# ==============================================================================
# SevaPath Database Backup Automation (Phase 5.3)
# Six-hourly automated backup, SQLite VACUUM snapshot, Age encryption,
# local GFS deduplication, and Cloudflare R2 offsite publication.
# ==============================================================================
set -euo pipefail

# ------------------------------------------------------------------------------
# 1. Environment and Configuration Loading
# ------------------------------------------------------------------------------
ENV_FILE="${SEVAPATH_CONFIG:-/etc/sevapath/production.env}"
if [ -f "$ENV_FILE" ]; then
    # Load environment variables safely
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

DATABASE_PATH="${DATABASE_PATH:-/var/lib/sevapath/sevapath.sqlite}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sevapath}"
LOCAL_ARCHIVE_DIR="${BACKUP_DIR}/archive"
AGE_PUBLIC_KEY_FILE="${AGE_PUBLIC_KEY_FILE:-/etc/sevapath/backup.pub}"
AGE_PUBLIC_KEY="${AGE_PUBLIC_KEY:-}"
R2_REMOTE="${R2_REMOTE:-cloudflare-r2}"
R2_BUCKET="${R2_BUCKET:-sevapath-backups}"
R2_ENABLED="${R2_ENABLED:-true}"
LAST_PROMOTED_MONTH_FILE="${BACKUP_DIR}/last_promoted_month.txt"

# ------------------------------------------------------------------------------
# 2. Preflight Disk Space and Dependency Verification
# ------------------------------------------------------------------------------
if [ ! -f "$DATABASE_PATH" ]; then
    echo "ERROR: Database file '$DATABASE_PATH' does not exist or is not a regular file." >&2
    exit 1
fi

DB_BYTES=$(stat -f "%z" "$DATABASE_PATH" 2>/dev/null || stat -c "%s" "$DATABASE_PATH" 2>/dev/null || echo 0)
if [ "$DB_BYTES" -le 0 ]; then
    echo "ERROR: Measured database size ($DB_BYTES bytes) is invalid or empty." >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR" "$LOCAL_ARCHIVE_DIR"

# Sizing gate: max(50 MB, 7 * DB_BYTES)
MIN_SPACE_BYTES=$(( 50 * 1024 * 1024 ))
REQUIRED_SPACE_BYTES=$(( 7 * DB_BYTES ))
if [ "$REQUIRED_SPACE_BYTES" -lt "$MIN_SPACE_BYTES" ]; then
    REQUIRED_SPACE_BYTES="$MIN_SPACE_BYTES"
fi

AVAILABLE_SPACE_BYTES=$(df -k "$BACKUP_DIR" | awk 'NR==2 { print $4 * 1024 }')
if [ "$AVAILABLE_SPACE_BYTES" -lt "$REQUIRED_SPACE_BYTES" ]; then
    echo "CRITICAL: Insufficient disk space on '$BACKUP_DIR'." >&2
    echo "Required: $REQUIRED_SPACE_BYTES bytes, Available: $AVAILABLE_SPACE_BYTES bytes." >&2
    exit 1
fi

# Load Age public recipient key
if [ -z "$AGE_PUBLIC_KEY" ]; then
    if [ -f "$AGE_PUBLIC_KEY_FILE" ]; then
        AGE_PUBLIC_KEY=$(tr -d '\r\n' < "$AGE_PUBLIC_KEY_FILE")
    else
        echo "ERROR: Age public key file '$AGE_PUBLIC_KEY_FILE' not found and AGE_PUBLIC_KEY not set." >&2
        exit 1
    fi
fi

if [[ ! "$AGE_PUBLIC_KEY" =~ ^age1[a-z0-9]+ ]]; then
    echo "ERROR: Invalid Age public recipient key format." >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# 3. SQLite WAL Monitoring & Checkpoint Management
# ------------------------------------------------------------------------------
WAL_PATH="${DATABASE_PATH}-wal"
if [ -f "$WAL_PATH" ]; then
    WAL_BYTES=$(stat -f "%z" "$WAL_PATH" 2>/dev/null || stat -c "%s" "$WAL_PATH" 2>/dev/null || echo 0)
    # Passive checkpoint threshold: 25 MB
    if [ "$WAL_BYTES" -gt $(( 25 * 1024 * 1024 )) ]; then
        echo "INFO: WAL size ($WAL_BYTES bytes) exceeds 25 MB. Running passive checkpoint..." >&2
        sqlite3 "$DATABASE_PATH" "PRAGMA wal_checkpoint(PASSIVE);" >/dev/null 2>&1 || true
    fi
    # Warning threshold: 100 MB
    if [ "$WAL_BYTES" -gt $(( 100 * 1024 * 1024 )) ]; then
        echo "WARNING: WAL_ACCUMULATION_WARNING: WAL size is $WAL_BYTES bytes." >&2
    fi
fi

# ------------------------------------------------------------------------------
# 4. Snapshot Generation via SQLite VACUUM INTO
# ------------------------------------------------------------------------------
ORIGINAL_STATUS=0
SNAPSHOT_CLEANUP_INVOKED=0

cleanup_transient_snapshot() {
    local exit_status=$?
    # Immediately disable traps to avoid recursive execution
    trap - EXIT INT TERM HUP
    if [ "$SNAPSHOT_CLEANUP_INVOKED" -eq 1 ]; then
        exit "$exit_status"
    fi
    SNAPSHOT_CLEANUP_INVOKED=1

    # Remove only the exact snapshot path created by this invocation
    if [ -n "${SNAPSHOT_PATH:-}" ] && [ -f "$SNAPSHOT_PATH" ]; then
        rm -f "$SNAPSHOT_PATH"
    fi

    # Preserve original signal exit status if non-zero
    if [ "$ORIGINAL_STATUS" -ne 0 ]; then
        exit_status="$ORIGINAL_STATUS"
    fi
    exit "$exit_status"
}

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
UUID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:12])")
BACKUP_ID="sevapath_backup_${TIMESTAMP}_${UUID}"
SNAPSHOT_PATH="${BACKUP_DIR}/${BACKUP_ID}.sqlite"
CIPHERTEXT_PATH="${LOCAL_ARCHIVE_DIR}/${BACKUP_ID}.sqlite.enc"
MANIFEST_PATH="${LOCAL_ARCHIVE_DIR}/${BACKUP_ID}.manifest.json"

# Install cleanup traps immediately after snapshot path is safely initialized
trap "ORIGINAL_STATUS=130; exit 130" INT
trap "ORIGINAL_STATUS=143; exit 143" TERM
trap "ORIGINAL_STATUS=129; exit 129" HUP
trap cleanup_transient_snapshot EXIT

echo "INFO: Creating snapshot for $BACKUP_ID..." >&2
sqlite3 "$DATABASE_PATH" "VACUUM INTO '${SNAPSHOT_PATH}';"

# ------------------------------------------------------------------------------
# 5. Pre-Encryption Snapshot Integrity & Foreign-Key Checks
# ------------------------------------------------------------------------------
INTEGRITY_CHECK=$(sqlite3 "$SNAPSHOT_PATH" "PRAGMA integrity_check;")
if [ "$INTEGRITY_CHECK" != "ok" ]; then
    echo "CRITICAL: Snapshot integrity check failed: $INTEGRITY_CHECK" >&2
    rm -f "$SNAPSHOT_PATH"
    exit 1
fi

FK_CHECK=$(sqlite3 "$SNAPSHOT_PATH" "PRAGMA foreign_key_check;")
if [ -n "$FK_CHECK" ]; then
    echo "CRITICAL: Snapshot foreign key check failed violations: $FK_CHECK" >&2
    rm -f "$SNAPSHOT_PATH"
    exit 1
fi

SNAPSHOT_BYTES=$(stat -f "%z" "$SNAPSHOT_PATH" 2>/dev/null || stat -c "%s" "$SNAPSHOT_PATH" 2>/dev/null || echo 0)
DATABASE_SHA256=$(python3 -c "import hashlib; print(hashlib.sha256(open('$SNAPSHOT_PATH', 'rb').read()).hexdigest())")

# ------------------------------------------------------------------------------
# 6. Age Public-Key Encryption
# ------------------------------------------------------------------------------
echo "INFO: Encrypting snapshot using Age public key..." >&2
if ! age -r "$AGE_PUBLIC_KEY" -o "$CIPHERTEXT_PATH" "$SNAPSHOT_PATH"; then
    echo "CRITICAL: Age encryption failed." >&2
    rm -f "$SNAPSHOT_PATH" "$CIPHERTEXT_PATH"
    exit 1
fi

# Securely unlink plaintext snapshot immediately
rm -f "$SNAPSHOT_PATH"

CIPHERTEXT_BYTES=$(stat -f "%z" "$CIPHERTEXT_PATH" 2>/dev/null || stat -c "%s" "$CIPHERTEXT_PATH" 2>/dev/null || echo 0)
if [ "$CIPHERTEXT_BYTES" -le 0 ]; then
    echo "CRITICAL: Encrypted artifact is empty." >&2
    rm -f "$CIPHERTEXT_PATH"
    exit 1
fi

CIPHERTEXT_SHA256=$(python3 -c "import hashlib; print(hashlib.sha256(open('$CIPHERTEXT_PATH', 'rb').read()).hexdigest())")

# ------------------------------------------------------------------------------
# 7. Manifest Creation
# ------------------------------------------------------------------------------
CURRENT_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cat <<EOF > "$MANIFEST_PATH"
{
  "backup_id": "$BACKUP_ID",
  "created_at": "$CURRENT_ISO",
  "schema_version": "1.0",
  "database_bytes": $SNAPSHOT_BYTES,
  "database_sha256": "$DATABASE_SHA256",
  "ciphertext_bytes": $CIPHERTEXT_BYTES,
  "ciphertext_sha256": "$CIPHERTEXT_SHA256",
  "recipient_public_key": "$AGE_PUBLIC_KEY",
  "integrity_check": "ok",
  "foreign_key_check": "ok",
  "status": "PUBLISHED"
}
EOF

# ------------------------------------------------------------------------------
# 8. Local GFS Deduplication & Retention Slot Management
# ------------------------------------------------------------------------------
echo "INFO: Evaluating local GFS retention slots..." >&2
python3 - <<EOF
import os, re, json
from datetime import datetime, timezone

archive_dir = "$LOCAL_ARCHIVE_DIR"
pattern = re.compile(r"^sevapath_backup_(\d{8})_(\d{6})_([a-f0-9]+)\.manifest\.json$")

manifests = []
for f in os.listdir(archive_dir):
    m = pattern.match(f)
    if m:
        date_str, time_str, uid = m.groups()
        dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        path = os.path.join(archive_dir, f)
        manifests.append({"dt": dt, "base": f[:-14], "path": path})

manifests.sort(key=lambda x: x["dt"], reverse=True)

keep_bases = set()

# Slot 1: 4 six-hourly (last 4 runs)
for item in manifests[:4]:
    keep_bases.add(item["base"])

# Slot 2: 7 daily (1 per day for last 7 calendar days)
seen_days = set()
for item in manifests:
    day_key = item["dt"].strftime("%Y-%m-%d")
    if day_key not in seen_days:
        seen_days.add(day_key)
        keep_bases.add(item["base"])
    if len(seen_days) >= 7:
        break

# Slot 3: 4 weekly (1 per week on Sunday or earliest available)
seen_weeks = set()
for item in manifests:
    if item["dt"].weekday() == 6: # Sunday
        week_key = item["dt"].strftime("%Y-%W")
        if week_key not in seen_weeks:
            seen_weeks.add(week_key)
            keep_bases.add(item["base"])
    if len(seen_weeks) >= 4:
        break

# Slot 4: 3 monthly (1 per month on 1st day or earliest available)
seen_months = set()
for item in manifests:
    if item["dt"].day == 1:
        month_key = item["dt"].strftime("%Y-%m")
        if month_key not in seen_months:
            seen_months.add(month_key)
            keep_bases.add(item["base"])
    if len(seen_months) >= 3:
        break

# Report coverage vs unique files
print(f"Local Slot Coverage: 6h={min(4, len(manifests))}/4, daily={len(seen_days)}/7, weekly={len(seen_weeks)}/4, monthly={len(seen_months)}/3")
print(f"Unique Local Artifacts Retained: {len(keep_bases)} (across 18 logical slots)")

# Pruning: delete any file whose base name is not in keep_bases
for item in manifests:
    if item["base"] not in keep_bases:
        enc_file = os.path.join(archive_dir, item["base"] + ".sqlite.enc")
        man_file = item["path"]
        print(f"Pruning local expired artifact: {item['base']}")
        if os.path.exists(enc_file): os.remove(enc_file)
        if os.path.exists(man_file): os.remove(man_file)
EOF

# ------------------------------------------------------------------------------
# 9. Offsite Publication to Cloudflare R2
# ------------------------------------------------------------------------------
if [ "$R2_ENABLED" = "true" ]; then
    echo "INFO: Publishing backup to Cloudflare R2 ($R2_REMOTE:$R2_BUCKET)..." >&2
    
    CURRENT_MONTH=$(date -u +"%Y-%m")
    LAST_PROMOTED_MONTH=""
    if [ -f "$LAST_PROMOTED_MONTH_FILE" ]; then
        LAST_PROMOTED_MONTH=$(tr -d '\r\n' < "$LAST_PROMOTED_MONTH_FILE")
    fi

    # Determine Offsite Tier
    IS_MONTHLY=false
    if [ "$CURRENT_MONTH" != "$LAST_PROMOTED_MONTH" ]; then
        IS_MONTHLY=true
        TARGET_PREFIX="verified/protected"
        MANIFEST_PREFIX="manifests/protected"
    elif [ "$(date -u +%u)" -eq 7 ]; then # Sunday
        TARGET_PREFIX="verified/weekly"
        MANIFEST_PREFIX="manifests/weekly"
    else
        TARGET_PREFIX="verified/daily"
        MANIFEST_PREFIX="manifests/daily"
    fi

    echo "INFO: Target offsite tier: $TARGET_PREFIX (Monthly promotion: $IS_MONTHLY)" >&2

    # Upload to staging: incoming/
    INCOMING_ENC="incoming/${BACKUP_ID}.sqlite.enc"
    INCOMING_MAN="incoming/${BACKUP_ID}.manifest.json"

    rclone copyto "$CIPHERTEXT_PATH" "${R2_REMOTE}:${R2_BUCKET}/${INCOMING_ENC}"
    rclone copyto "$MANIFEST_PATH" "${R2_REMOTE}:${R2_BUCKET}/${INCOMING_MAN}"

    # Verify remote hash using rclone check or hash comparison
    REMOTE_HASH=$(rclone hashsum sha256 "${R2_REMOTE}:${R2_BUCKET}/${INCOMING_ENC}" | awk '{ print $1 }')
    if [ "$REMOTE_HASH" != "$CIPHERTEXT_SHA256" ]; then
        echo "CRITICAL: Remote ciphertext SHA-256 mismatch ($REMOTE_HASH != $CIPHERTEXT_SHA256)." >&2
        rclone deletefile "${R2_REMOTE}:${R2_BUCKET}/${INCOMING_ENC}" 2>/dev/null || true
        rclone deletefile "${R2_REMOTE}:${R2_BUCKET}/${INCOMING_MAN}" 2>/dev/null || true
        exit 1
    fi

    # Promote from incoming to target verified prefix
    TARGET_ENC="${TARGET_PREFIX}/${BACKUP_ID}.sqlite.enc"
    TARGET_MAN="${MANIFEST_PREFIX}/${BACKUP_ID}.manifest.json"

    rclone moveto "${R2_REMOTE}:${R2_BUCKET}/${INCOMING_ENC}" "${R2_REMOTE}:${R2_BUCKET}/${TARGET_ENC}"
    rclone moveto "${R2_REMOTE}:${R2_BUCKET}/${INCOMING_MAN}" "${R2_REMOTE}:${R2_BUCKET}/${TARGET_MAN}"

    # Update mutable pointer: pointers/latest_verified.json
    POINTER_TMP="${BACKUP_DIR}/latest_verified.json"
    cat <<EOF > "$POINTER_TMP"
{
  "latest_verified_id": "$BACKUP_ID",
  "published_at": "$CURRENT_ISO",
  "target_tier": "$TARGET_PREFIX",
  "ciphertext_path": "$TARGET_ENC",
  "manifest_path": "$TARGET_MAN",
  "status": "PUBLISHED"
}
EOF
    rclone copyto "$POINTER_TMP" "${R2_REMOTE}:${R2_BUCKET}/pointers/latest_verified.json"
    rm -f "$POINTER_TMP"

    # If monthly promotion, advance marker and update latest_protected.json pointer
    if [ "$IS_MONTHLY" = true ]; then
        echo "$CURRENT_MONTH" > "$LAST_PROMOTED_MONTH_FILE"
        PROTECTED_POINTER_TMP="${BACKUP_DIR}/latest_protected.json"
        cat <<EOF > "$PROTECTED_POINTER_TMP"
{
  "latest_protected_id": "$BACKUP_ID",
  "promoted_month": "$CURRENT_MONTH",
  "published_at": "$CURRENT_ISO",
  "ciphertext_path": "$TARGET_ENC",
  "manifest_path": "$TARGET_MAN",
  "status": "PUBLISHED"
}
EOF
        rclone copyto "$PROTECTED_POINTER_TMP" "${R2_REMOTE}:${R2_BUCKET}/pointers/latest_protected.json"
        rm -f "$PROTECTED_POINTER_TMP"
    fi

    echo "INFO: Backup publication verified successfully. Status: PUBLISHED" >&2
fi

echo "SUCCESS: SevaPath backup completed for $BACKUP_ID"
exit 0
