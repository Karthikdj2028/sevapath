#!/bin/bash
# ==============================================================================
# SevaPath Database Restoration Automation (Phase 5.3)
# Fail-closed database restoration with two-phase disk-space gates,
# non-destructive process lock checks, safety snapshot preservation,
# SQLite integrity verification, and automatic rollback on failure.
# ==============================================================================
set -euo pipefail

# ------------------------------------------------------------------------------
# 1. Environment and Parameter Parsing
# ------------------------------------------------------------------------------
ENV_FILE="${SEVAPATH_CONFIG:-/etc/sevapath/production.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

DATABASE_PATH="${DATABASE_PATH:-/var/lib/sevapath/sevapath.sqlite}"
DATABASE_DIR=$(dirname "$DATABASE_PATH")
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sevapath}"
SERVICE_NAME="${SEVAPATH_SERVICE_NAME:-sevapath.service}"
HEALTH_CHECK_URL="${HEALTH_CHECK_URL:-http://127.0.0.1:8000/health?check=ready}"

CANDIDATE_PATH=""

usage() {
    echo "Usage: $0 --candidate <path-to-decrypted-sqlite-file>" >&2
    echo "  --candidate: Pre-decrypted, verified SQLite database file to restore." >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --candidate)
            CANDIDATE_PATH="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

if [ -z "$CANDIDATE_PATH" ]; then
    echo "ERROR: --candidate path is required." >&2
    usage
fi

if [ ! -f "$CANDIDATE_PATH" ]; then
    echo "CRITICAL: Candidate database file '$CANDIDATE_PATH' does not exist." >&2
    exit 1
fi

# Pre-validate candidate SQLite integrity before doing anything
echo "INFO: Validating candidate database integrity..." >&2
CANDIDATE_INTEGRITY=$(sqlite3 "$CANDIDATE_PATH" "PRAGMA integrity_check;" 2>/dev/null || echo "failed")
if [ "$CANDIDATE_INTEGRITY" != "ok" ]; then
    echo "CRITICAL: Candidate database failed integrity_check: $CANDIDATE_INTEGRITY" >&2
    exit 1
fi

CANDIDATE_FK=$(sqlite3 "$CANDIDATE_PATH" "PRAGMA foreign_key_check;" 2>/dev/null || echo "failed")
if [ -n "$CANDIDATE_FK" ]; then
    echo "CRITICAL: Candidate database failed foreign_key_check: $CANDIDATE_FK" >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. Gate 1: Pre-Shutdown Disk Space Check (Zero Downtime)
# ------------------------------------------------------------------------------
DB_BYTES=0
if [ -f "$DATABASE_PATH" ]; then
    DB_BYTES=$(stat -f "%z" "$DATABASE_PATH" 2>/dev/null || stat -c "%s" "$DATABASE_PATH" 2>/dev/null || echo 0)
fi

WAL_BYTES=0
if [ -f "${DATABASE_PATH}-wal" ]; then
    WAL_BYTES=$(stat -f "%z" "${DATABASE_PATH}-wal" 2>/dev/null || stat -c "%s" "${DATABASE_PATH}-wal" 2>/dev/null || echo 0)
fi

# Gate 1 Requirement: 2 * DB + WAL + 20 MB
GATE1_REQUIRED_BYTES=$(( (2 * DB_BYTES) + WAL_BYTES + (20 * 1024 * 1024) ))
AVAILABLE_SPACE_BYTES=$(df -k "$DATABASE_DIR" | awk 'NR==2 { print $4 * 1024 }')

if [ "$AVAILABLE_SPACE_BYTES" -lt "$GATE1_REQUIRED_BYTES" ]; then
    echo "CRITICAL: INSUFFICIENT_PRE_RESTORE_SPACE. Gate 1 space check failed." >&2
    echo "Required: $GATE1_REQUIRED_BYTES bytes, Available: $AVAILABLE_SPACE_BYTES bytes." >&2
    echo "Aborting restore without stopping $SERVICE_NAME. Zero service interruption." >&2
    exit 1
fi

echo "INFO: Gate 1 passed. Available space is sufficient ($AVAILABLE_SPACE_BYTES >= $GATE1_REQUIRED_BYTES)." >&2

# ------------------------------------------------------------------------------
# 3. Graceful Service Shutdown & Process Inspection (Non-destructive)
# ------------------------------------------------------------------------------
SERVICE_WAS_ACTIVE=false
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        SERVICE_WAS_ACTIVE=true
        echo "INFO: Stopping $SERVICE_NAME gracefully..." >&2
        systemctl stop "$SERVICE_NAME"
    fi
fi

# Wait and inspect for lingering processes holding database handles
GRACE_SECONDS=15
PROCESSES_CLEARED=false
for ((i=1; i<=GRACE_SECONDS; i++)); do
    LOCKING_PIDS=""
    if command -v fuser >/dev/null 2>&1; then
        LOCKING_PIDS=$(fuser "$DATABASE_PATH" 2>/dev/null || true)
    elif command -v lsof >/dev/null 2>&1; then
        LOCKING_PIDS=$(lsof -t "$DATABASE_PATH" 2>/dev/null || true)
    fi

    if [ -z "$LOCKING_PIDS" ]; then
        PROCESSES_CLEARED=true
        break
    fi
    echo "WAIT: Database is held by PID(s): $LOCKING_PIDS. Waiting ($i/$GRACE_SECONDS)..." >&2
    sleep 1
done

if [ "$PROCESSES_CLEARED" = false ]; then
    echo "CRITICAL: Database still locked by process(es): $LOCKING_PIDS after $GRACE_SECONDS seconds." >&2
    echo "FORCED TERMINATION (kill -9) IS STRICTLY FORBIDDEN. Aborting restore." >&2
    if [ "$SERVICE_WAS_ACTIVE" = true ]; then
        echo "INFO: Restarting $SERVICE_NAME safely..." >&2
        systemctl start "$SERVICE_NAME" || true
    fi
    exit 1
fi

# ------------------------------------------------------------------------------
# 4. Gate 2: Post-Shutdown Re-verification Gate (Pre-Mutation Gate)
# ------------------------------------------------------------------------------
# Re-measure actual file sizes post-shutdown (clean shutdown flushes WAL pages)
ACTUAL_DB_BYTES=$(stat -f "%z" "$DATABASE_PATH" 2>/dev/null || stat -c "%s" "$DATABASE_PATH" 2>/dev/null || echo 0)
ACTUAL_WAL_BYTES=0
if [ -f "${DATABASE_PATH}-wal" ]; then
    ACTUAL_WAL_BYTES=$(stat -f "%z" "${DATABASE_PATH}-wal" 2>/dev/null || stat -c "%s" "${DATABASE_PATH}-wal" 2>/dev/null || echo 0)
fi

GATE2_REQUIRED_BYTES=$(( (2 * ACTUAL_DB_BYTES) + ACTUAL_WAL_BYTES + (20 * 1024 * 1024) ))
POST_SHUTDOWN_AVAILABLE=$(df -k "$DATABASE_DIR" | awk 'NR==2 { print $4 * 1024 }')

if [ "$POST_SHUTDOWN_AVAILABLE" -lt "$GATE2_REQUIRED_BYTES" ]; then
    echo "CRITICAL: INSUFFICIENT_RESTORE_DISK_SPACE. Gate 2 post-shutdown check failed." >&2
    echo "Required: $GATE2_REQUIRED_BYTES bytes, Available: $POST_SHUTDOWN_AVAILABLE bytes." >&2
    echo "Leaving live database completely untouched." >&2
    if [ "$SERVICE_WAS_ACTIVE" = true ]; then
        echo "INFO: Restarting $SERVICE_NAME..." >&2
        systemctl start "$SERVICE_NAME"
    fi
    exit 1
fi

echo "INFO: Gate 2 passed. Disk space verified for atomic swap." >&2

# ------------------------------------------------------------------------------
# 5. Live Database Safety Snapshot Preservation
# ------------------------------------------------------------------------------
RESTORE_TS=$(date -u +"%Y%m%d_%H%M%S")
SAFETY_DIR="${BACKUP_DIR}/pre_restore_safety_${RESTORE_TS}"
mkdir -p "$SAFETY_DIR"

echo "INFO: Creating safety copy of live database and sidecars in '$SAFETY_DIR'..." >&2
if [ -f "$DATABASE_PATH" ]; then
    cp "$DATABASE_PATH" "${SAFETY_DIR}/sevapath.sqlite"
fi
if [ -f "${DATABASE_PATH}-wal" ]; then
    cp "${DATABASE_PATH}-wal" "${SAFETY_DIR}/sevapath.sqlite-wal"
fi
if [ -f "${DATABASE_PATH}-shm" ]; then
    cp "${DATABASE_PATH}-shm" "${SAFETY_DIR}/sevapath.sqlite-shm"
fi

# ------------------------------------------------------------------------------
# 6. Atomic Database Replacement & Clean Sidecar Teardown
# ------------------------------------------------------------------------------
echo "INFO: Performing atomic database replacement..." >&2
TEMP_REPLACEMENT="${DATABASE_DIR}/.restoring_sevapath_${RESTORE_TS}.sqlite"

# Copy candidate to same filesystem for atomic rename
cp "$CANDIDATE_PATH" "$TEMP_REPLACEMENT"
mv "$TEMP_REPLACEMENT" "$DATABASE_PATH"

# Clean up stale WAL and SHM sidecars from prior database state
rm -f "${DATABASE_PATH}-wal" "${DATABASE_PATH}-shm"

# Ensure correct file permissions
chmod 0640 "$DATABASE_PATH" 2>/dev/null || true

# ------------------------------------------------------------------------------
# 7. Post-Restore Verification & Readiness Check
# ------------------------------------------------------------------------------
RESTORE_SUCCESS=true

# Check restored database integrity in place
RESTORED_INTEGRITY=$(sqlite3 "$DATABASE_PATH" "PRAGMA integrity_check;" 2>/dev/null || echo "failed")
if [ "$RESTORED_INTEGRITY" != "ok" ]; then
    echo "CRITICAL: In-place integrity check failed after restore: $RESTORED_INTEGRITY" >&2
    RESTORE_SUCCESS=false
fi

if [ "$SERVICE_WAS_ACTIVE" = true ] && [ "$RESTORE_SUCCESS" = true ]; then
    echo "INFO: Starting $SERVICE_NAME..." >&2
    if ! systemctl start "$SERVICE_NAME"; then
        echo "CRITICAL: Failed to start $SERVICE_NAME post-restore." >&2
        RESTORE_SUCCESS=false
    fi

    # Readiness probe check
    if [ "$RESTORE_SUCCESS" = true ]; then
        echo "INFO: Checking application readiness ($HEALTH_CHECK_URL)..." >&2
        sleep 2
        READY=false
        for ((retry=1; retry<=10; retry++)); do
            if curl -sf "$HEALTH_CHECK_URL" >/dev/null 2>&1; then
                READY=true
                break
            fi
            sleep 1
        done

        if [ "$READY" = false ]; then
            echo "CRITICAL: Readiness probe failed after restart." >&2
            RESTORE_SUCCESS=false
        fi
    fi
fi

# ------------------------------------------------------------------------------
# 8. Rollback on Failure
# ------------------------------------------------------------------------------
if [ "$RESTORE_SUCCESS" = false ]; then
    echo "CRITICAL: Restoration failed validation or readiness. Executing automatic rollback..." >&2
    if [ -f "${SAFETY_DIR}/sevapath.sqlite" ]; then
        cp "${SAFETY_DIR}/sevapath.sqlite" "$DATABASE_PATH"
    fi
    if [ -f "${SAFETY_DIR}/sevapath.sqlite-wal" ]; then
        cp "${SAFETY_DIR}/sevapath.sqlite-wal" "${DATABASE_PATH}-wal"
    fi
    if [ -f "${SAFETY_DIR}/sevapath.sqlite-shm" ]; then
        cp "${SAFETY_DIR}/sevapath.sqlite-shm" "${DATABASE_PATH}-shm"
    fi

    if [ "$SERVICE_WAS_ACTIVE" = true ]; then
        systemctl restart "$SERVICE_NAME" || true
    fi
    echo "ALERT: Rollback completed. Live database restored to pre-restore safety copy." >&2
    exit 1
fi

echo "SUCCESS: SevaPath database successfully restored from candidate. Live safety copy archived in '$SAFETY_DIR'."
exit 0
