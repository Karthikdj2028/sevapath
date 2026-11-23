#!/usr/bin/env bash
# ==============================================================================
# SevaPath Production Code Rollback Script
#
# Usage:
#   sudo ./rollback.sh [TARGET_RELEASE_ID]
#
# Boundaries:
# - CODE ROLLBACK ONLY.
# - Atomically reverts /opt/sevapath/current to the previous known-good release.
# - Restarts the systemd service and polls the readiness endpoint.
# - STRICTLY: Never touches, modifies, or overwrites the SQLite database or sidecars.
# ==============================================================================

set -euo pipefail

SEVAPATH_ROOT="/opt/sevapath"
CURRENT_LINK="$SEVAPATH_ROOT/current"
PREVIOUS_FILE="$SEVAPATH_ROOT/.previous_release"

TARGET_RELEASE="${1:-}"

if [ -z "$TARGET_RELEASE" ]; then
    if [ -f "$PREVIOUS_FILE" ] && [ -n "$(cat "$PREVIOUS_FILE")" ]; then
        TARGET_RELEASE="$(cat "$PREVIOUS_FILE")"
    else
        echo "ERROR: No previous release record found at $PREVIOUS_FILE." >&2
        echo "Please specify target release directory explicitly: $0 <TARGET_RELEASE_DIR>" >&2
        exit 1
    fi
fi

# Resolve path
if [ -d "$TARGET_RELEASE" ]; then
    TARGET_DIR="$(cd "$TARGET_RELEASE" && pwd)"
elif [ -d "$SEVAPATH_ROOT/releases/$TARGET_RELEASE" ]; then
    TARGET_DIR="$SEVAPATH_ROOT/releases/$TARGET_RELEASE"
else
    echo "ERROR: Target rollback directory '$TARGET_RELEASE' does not exist." >&2
    exit 1
fi

echo "===================================================================="
echo "SevaPath Emergency Code Rollback: Reverting to $TARGET_DIR"
echo "NOTICE: Database remains strictly untouched."
echo "===================================================================="

# 1. Atomically restore symlink
ln -sfn "$TARGET_DIR" "$CURRENT_LINK.rollback"
mv -Tf "$CURRENT_LINK.rollback" "$CURRENT_LINK"
echo "Symlink reverted: $CURRENT_LINK -> $TARGET_DIR"

# 2. Restart systemd service
echo "Restarting service..."
systemctl restart sevapath

# 3. Poll readiness endpoint
echo "Verifying readiness after rollback..."
READY=0
for i in $(seq 1 15); do
    STATUS_CODE="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/health?check=ready" 2>/dev/null || echo "000")"
    if [ "$STATUS_CODE" = "200" ]; then
        READY=1
        echo "Rollback readiness confirmed on attempt $i (HTTP 200 OK)."
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "CRITICAL: Readiness probe failed after rollback restart. Manual operator intervention required." >&2
    exit 1
fi

echo "Rollback successfully completed. Active code is running from $TARGET_DIR."
echo "===================================================================="
