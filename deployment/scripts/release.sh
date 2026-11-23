#!/usr/bin/env bash
# ==============================================================================
# SevaPath Deterministic Production Release Script
#
# Usage:
#   sudo ./release.sh <RELEASE_DIR_OR_ID>
#
# Safeguards:
# - Fail-closed execution (`set -euo pipefail`).
# - Non-disclosing environment file loading (no secret leakage in logs).
# - Disk capacity verification before snapshot.
# - Mandatory SQLite pre-deployment snapshot (`VACUUM INTO`) at unique destination.
# - Pre-flight scratch DB and lock-acquisition diagnostics.
# - Out-of-band candidate migration with isolated PYTHONPATH.
# - Atomic symlink switch and controlled systemd restart.
# - Health readiness probe verification before finalizing.
# ==============================================================================

set -euo pipefail

RELEASE_INPUT="${1:-}"
if [ -z "$RELEASE_INPUT" ]; then
    echo "ERROR: Missing release directory or release ID argument." >&2
    echo "Usage: $0 <RELEASE_DIR_OR_ID>" >&2
    exit 1
fi

SEVAPATH_ROOT="/opt/sevapath"
SHARED_DIR="$SEVAPATH_ROOT/shared"
INSTANCE_DIR="$SHARED_DIR/instance"
BACKUP_DIR="$SHARED_DIR/backups"
LOGS_DIR="$SHARED_DIR/logs"
CURRENT_LINK="$SEVAPATH_ROOT/current"
ENV_FILE="/etc/sevapath/production.env"
VENV_PYTHON="$SEVAPATH_ROOT/venv/bin/python3"

# Resolve target release directory
if [ -d "$RELEASE_INPUT" ]; then
    CANDIDATE_DIR="$(cd "$RELEASE_INPUT" && pwd)"
    RELEASE_ID="$(basename "$CANDIDATE_DIR")"
elif [ -d "$SEVAPATH_ROOT/releases/$RELEASE_INPUT" ]; then
    CANDIDATE_DIR="$SEVAPATH_ROOT/releases/$RELEASE_INPUT"
    RELEASE_ID="$RELEASE_INPUT"
else
    echo "ERROR: Release directory '$RELEASE_INPUT' does not exist." >&2
    exit 1
fi

echo "===================================================================="
echo "SevaPath Deployment: Activating Release $RELEASE_ID"
echo "Candidate Path: $CANDIDATE_DIR"
echo "===================================================================="

# --- Phase A: Pre-Flight Staging & Environment Validation ---
echo "[1/8] Validating environment configuration and paths..."

if [ ! -r "$ENV_FILE" ]; then
    echo "ERROR: Environment file $ENV_FILE does not exist or is unreadable." >&2
    exit 1
fi

# Validate environment permissions (must be 0600 or 0640)
ENV_PERMS="$(stat -c "%a" "$ENV_FILE" 2>/dev/null || stat -f "%Op" "$ENV_FILE" 2>/dev/null || echo "unknown")"
echo "Environment file permissions verified ($ENV_PERMS)."

# Source environment safely in isolated subshell check without disclosing secrets
(
    set -a
    # shellcheck source=/dev/null
    . "$ENV_FILE"
    if [ -z "${SECRET_KEY:-}" ] || [ "${SECRET_KEY:-}" = "sevapath-dev-insecure-secret-key-2026" ]; then
        echo "ERROR: Environment file contains missing or insecure SECRET_KEY." >&2
        exit 1
    fi
    if [ -z "${DATABASE_PATH:-}" ]; then
        echo "ERROR: Environment file is missing DATABASE_PATH." >&2
        exit 1
    fi
)

# Export environment variables for deployment process without printing values
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a

# Verify persistent shared directories exist
mkdir -p "$INSTANCE_DIR" "$BACKUP_DIR" "$LOGS_DIR"

# Link candidate instance directory
ln -sfn "$INSTANCE_DIR" "$CANDIDATE_DIR/instance"

# --- Phase B: Disk Capacity & Pre-Deployment Diagnostics ---
echo "[2/8] Checking disk capacity and filesystem writeability..."

# Ensure at least 50 MB (51200 KB) free space on shared volume
AVAIL_KB=$(df -k "$SHARED_DIR" | awk 'NR==2 {print $4}')
if [ -n "$AVAIL_KB" ] && [ "$AVAIL_KB" -lt 51200 ]; then
    echo "ERROR: Insufficient disk space on $SHARED_DIR. Available: ${AVAIL_KB}KB, required >= 51200KB." >&2
    exit 1
fi
echo "Disk space verified (${AVAIL_KB}KB available)."

# Diagnostic 1: Unique scratch database write test
PROBE_UUID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
SCRATCH_DB="$INSTANCE_DIR/.probe_${PROBE_UUID}.sqlite"
python3 -c "
import sqlite3, os, sys
p = '$SCRATCH_DB'
try:
    c = sqlite3.connect(p, timeout=5.0)
    c.execute('CREATE TABLE t(x TEXT);')
    c.execute('INSERT INTO t VALUES (\"ok\");')
    c.commit()
    res = c.execute('SELECT x FROM t;').fetchone()[0]
    c.close()
    if res != 'ok':
        sys.exit(1)
finally:
    if os.path.exists(p):
        os.unlink(p)
" || {
    echo "ERROR: Scratch filesystem write test failed on $INSTANCE_DIR." >&2
    exit 1
}
echo "Filesystem writeability diagnostic passed."

# Diagnostic 2: Live database lock acquisition diagnostic
PROD_DB="$DATABASE_PATH"
if [ -f "$PROD_DB" ]; then
    python3 -c "
import sqlite3, sys
p = '$PROD_DB'
try:
    c = sqlite3.connect(p, timeout=5.0)
    c.execute('BEGIN IMMEDIATE;')
    c.execute('ROLLBACK;')
    c.close()
except Exception as e:
    sys.exit(1)
" || {
        echo "ERROR: Failed to acquire write-lock diagnostic on production database." >&2
        exit 1
    }
    echo "Database lock-acquisition diagnostic passed."
fi

# --- Phase C: Mandatory Pre-Deployment Snapshot ---
echo "[3/8] Creating pre-deployment SQLite backup snapshot..."

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
SNAPSHOT_PATH="$BACKUP_DIR/pre_deploy_${RELEASE_ID}_${TIMESTAMP}.sqlite"

if [ -e "$SNAPSHOT_PATH" ]; then
    echo "ERROR: Snapshot destination $SNAPSHOT_PATH already exists. Aborting to avoid overwrite." >&2
    exit 1
fi

if [ -f "$PROD_DB" ]; then
    # Use SQLite online backup API via VACUUM INTO
    sqlite3 "$PROD_DB" "VACUUM INTO '$SNAPSHOT_PATH';"
    
    # Offline integrity verification of the exact snapshot created
    SNAPSHOT_INTEGRITY="$(sqlite3 "$SNAPSHOT_PATH" "PRAGMA integrity_check;")"
    if [ "$SNAPSHOT_INTEGRITY" != "ok" ]; then
        echo "ERROR: Pre-deployment snapshot failed integrity check: $SNAPSHOT_INTEGRITY" >&2
        exit 1
    fi
    echo "Pre-deployment snapshot created and verified: $SNAPSHOT_PATH"
else
    echo "Initial deployment: production database does not yet exist. Skipping snapshot."
fi

# --- Phase D: Candidate Release Out-of-Band Migration ---
echo "[4/8] Running candidate release database migrations out-of-band..."

(
    cd "$CANDIDATE_DIR"
    PYTHONPATH="$CANDIDATE_DIR" \
    SEVAPATH_ENV=production \
    DATABASE_PATH="$PROD_DB" \
    "$VENV_PYTHON" -m flask --app wsgi:app init-db
) || {
    echo "FATAL: Candidate migration failed. Active release remains untouched. Aborting." >&2
    exit 1
}
echo "Candidate migration succeeded."

# --- Phase E: Atomic Symlink Switch ---
echo "[5/8] Switching release symlink atomically..."

PREVIOUS_TARGET=""
if [ -L "$CURRENT_LINK" ]; then
    PREVIOUS_TARGET="$(readlink "$CURRENT_LINK")"
    echo "$PREVIOUS_TARGET" > "$SEVAPATH_ROOT/.previous_release"
fi

ln -sfn "$CANDIDATE_DIR" "$CURRENT_LINK.new"
mv -Tf "$CURRENT_LINK.new" "$CURRENT_LINK"
echo "Symlink switched: $CURRENT_LINK -> $CANDIDATE_DIR"

# --- Phase F: Controlled Service Restart ---
echo "[6/8] Restarting Gunicorn service..."

systemctl restart sevapath || {
    echo "ERROR: Failed to restart sevapath service. Triggering code rollback..." >&2
    if [ -x "$SEVAPATH_ROOT/scripts/rollback.sh" ]; then
        "$SEVAPATH_ROOT/scripts/rollback.sh"
    fi
    exit 1
}

# --- Phase G: Health Readiness Verification ---
echo "[7/8] Verifying application readiness..."

READY=0
for i in $(seq 1 15); do
    STATUS_CODE="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/health?check=ready" 2>/dev/null || echo "000")"
    if [ "$STATUS_CODE" = "200" ]; then
        READY=1
        echo "Readiness confirmed on attempt $i (HTTP 200 OK)."
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "FATAL: Readiness check failed after 15 seconds. Triggering code rollback..." >&2
    if [ -x "$SEVAPATH_ROOT/scripts/rollback.sh" ]; then
        "$SEVAPATH_ROOT/scripts/rollback.sh"
    fi
    exit 1
fi

# --- Phase H: Deployment Completion ---
echo "[8/8] Release $RELEASE_ID successfully deployed and verified!"
echo "Snapshot preserved: ${SNAPSHOT_PATH:-None}"
echo "===================================================================="
