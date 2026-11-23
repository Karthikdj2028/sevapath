# SevaPath Production Deployment & Operations Guide

**Project:** SevaPath — Tamil Nadu Citizen Preparation Platform  
**Target Architecture:** Single-Host Linux (Debian 12 / Ubuntu 22.04 LTS)  
**Web & WSGI Stack:** Nginx (Edge Proxy & TLS) + Gunicorn 22+ (`gthread`) + Flask 3.x  
**Persistence:** Persistent Local POSIX Block Storage with SQLite 3 (WAL Mode)  

---

## 1. Architecture & Security Model

SevaPath operates as a lightweight, privacy-first civic preparation platform. It does not store citizen passwords or Aadhaar numbers; preparation sessions are identified by transient 256-bit anonymous cookie tokens (`sevapath_sid`) hashed with SHA-256.

```text
[ Citizen / Public Internet ]
           │
           ▼ (HTTPS / TLS 443)
┌───────────────────────────────────────────────┐
│ NGINX (Edge Reverse Proxy on Same Host)      │
│ - Terminates TLS (Certbot / Let's Encrypt)    │
│ - Sets X-Forwarded-For: $remote_addr          │
│ - Sets X-Forwarded-Proto: $scheme             │
│ - Enforces 1 MB Request Body Limit            │
│ - Offloads /static/ with Revalidation Caching │
└───────────────────────────────────────────────┘
           │
           ▼ (Loopback HTTP on 127.0.0.1:8000)
┌───────────────────────────────────────────────┐
│ GUNICORN WSGI APPLICATION SERVER              │
│ - Managed by systemd (sevapath.service)       │
│ - 2 Workers, 2 Threads (gthread)              │
│ - Runs as unprivileged user: 'sevapath'       │
│ - ProxyFix: trusts 1 hop ($remote_addr)       │
└───────────────────────────────────────────────┘
           │
           ▼ (Direct POSIX File I/O)
┌───────────────────────────────────────────────┐
│ PERSISTENT LOCAL STORAGE (/opt/sevapath/shared)│
│ - instance/sevapath.sqlite (Main DB)          │
│ - instance/sevapath.sqlite-wal (WAL Index)    │
│ - instance/sevapath.sqlite-shm (Shared Memory)│
│ - backups/pre_deploy_*.sqlite (Snapshots)     │
└───────────────────────────────────────────────┘
```

### Key Design Principles:
1. **Single-Host Local Storage**: SQLite requires POSIX shared-memory primitives (`mmap`). Network filesystems (NFS, SMB, CIFS) are forbidden. All database files and sidecars (`-wal`, `-shm`) reside on the same local block storage mount.
2. **Immutable Release Directories**: Application code is deployed into versioned release folders (`/opt/sevapath/releases/<RELEASE_ID>`), activated via an atomic symlink switch (`/opt/sevapath/current`).
3. **Decoupled Database Migrations**: Migrations are executed out-of-band *before* activating the new release. They are never run as a systemd `ExecStartPre` hook.
4. **Separation of Code Rollback vs. Database Disaster Recovery**: Application code rollback (`rollback.sh`) is code-only and never touches SQLite. Database recovery is an explicit manual runbook.

---

## 2. Directory Layout & File Permissions

```text
/opt/sevapath/
├── current -> /opt/sevapath/releases/20261123T041500Z_15c4b9c  # Active symlink
├── releases/
│   ├── 20261122T195929Z_3bdf179/
│   └── 20261123T041500Z_15c4b9c/     # Immutable release folders (chmod 755)
├── shared/
│   ├── instance/                      # Persistent database (chmod 700, sevapath:sevapath)
│   │   ├── sevapath.sqlite
│   │   ├── sevapath.sqlite-wal
│   │   └── sevapath.sqlite-shm
│   ├── backups/                       # Pre-deployment snapshots (chmod 700)
│   └── logs/                          # Persistent application logs (chmod 755)
└── venv/                              # Shared Python virtual environment

/etc/sevapath/
└── production.env                     # Production environment variables (chmod 600, sevapath:sevapath)
```

---

## 3. Server Prerequisites & Initial Provisioning

### 3.1 Base Operating System Packages (Debian / Ubuntu)
```bash
sudo apt update && sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    sqlite3 \
    nginx \
    certbot \
    python3-certbot-nginx \
    curl \
    git
```

### 3.2 Service Account & Directory Creation
```bash
# Create dedicated system user
sudo useradd --system --shell /usr/sbin/nologin --home-dir /opt/sevapath sevapath

# Create root directories
sudo mkdir -p /opt/sevapath/releases /opt/sevapath/shared/instance \
              /opt/sevapath/shared/backups /opt/sevapath/shared/logs \
              /etc/sevapath

# Set ownership and permissions
sudo chown -R sevapath:sevapath /opt/sevapath /etc/sevapath
sudo chmod 750 /opt/sevapath
sudo chmod 700 /opt/sevapath/shared/instance /opt/sevapath/shared/backups /etc/sevapath
```

### 3.3 Production Environment Configuration (`/etc/sevapath/production.env`)
Create `/etc/sevapath/production.env` with restricted permissions:
```bash
sudo -u sevapath tee /etc/sevapath/production.env > /dev/null << 'EOF'
SEVAPATH_ENV=production
SECRET_KEY=REPLACE_WITH_CRYPTOGRAPHICALLY_RANDOM_HEX_KEY_GENERATE_VIA_SECRETS_TOKEN_HEX
DATABASE_PATH=/opt/sevapath/shared/instance/sevapath.sqlite
GUNICORN_BIND=127.0.0.1:8000
WEB_CONCURRENCY=2
GUNICORN_THREADS=2
GUNICORN_TIMEOUT=30
LOG_LEVEL=info
PROXY_FIX_ENABLED=True
PROXY_FIX_HOPS=1
EOF

sudo chmod 600 /etc/sevapath/production.env
```

---

## 4. Service & Reverse Proxy Installation

### 4.1 systemd Service Unit
Install the service unit template:
```bash
sudo cp deployment/systemd/sevapath.service /etc/systemd/system/sevapath.service
sudo systemctl daemon-reload
sudo systemctl enable sevapath
```
Validate syntax:
```bash
systemd-analyze verify /etc/systemd/system/sevapath.service
```

### 4.2 Nginx Reverse Proxy & TLS Configuration
1. Copy Nginx configuration:
   ```bash
   sudo cp deployment/nginx/sevapath.conf /etc/nginx/sites-available/sevapath.conf
   ```
2. Replace placeholders in `/etc/nginx/sites-available/sevapath.conf`:
   * `__SEVAPATH_DOMAIN__` $\to$ your domain (e.g. `sevapath.tn.gov.in`)
   * `__SEVAPATH_STATIC_DIR__` $\to$ `/opt/sevapath/current/app/static`
   * `__SSL_CERT_PATH__` $\to$ `/etc/letsencrypt/live/<domain>/fullchain.pem`
   * `__SSL_KEY_PATH__` $\to$ `/etc/letsencrypt/live/<domain>/privkey.pem`
   * `__SSL_CHAIN_PATH__` $\to$ `/etc/letsencrypt/live/<domain>/chain.pem`
3. Obtain TLS certificate via Certbot:
   ```bash
   sudo certbot certonly --nginx -d <your-domain>
   ```
4. Enable site and test configuration:
   ```bash
   sudo ln -s /etc/nginx/sites-available/sevapath.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

---

## 5. Deployment Procedure (`release.sh`)

Every release is deployed deterministically using `deployment/scripts/release.sh`:

```bash
sudo /opt/sevapath/current/deployment/scripts/release.sh /opt/sevapath/releases/<NEW_RELEASE_ID>
```

### Automated Deployment Safeguards:
1. **Disk Capacity Check**: Verifies that $\ge 50\text{ MB}$ free space is available on `/opt/sevapath/shared`.
2. **Scratch Write Diagnostic**: Creates a unique temporary SQLite file in `instance/`, inserts a record, verifies read/write, and deletes the temporary file.
3. **Write-Lock Diagnostic**: Runs `BEGIN IMMEDIATE; ROLLBACK;` against the production database to verify write-lock acquisition without data mutation.
4. **Mandatory Snapshot**: Generates an exact pre-deployment backup using `VACUUM INTO` and verifies offline integrity (`PRAGMA integrity_check`).
5. **Out-of-Band Candidate Migration**: Runs `flask init-db` within the candidate release directory under isolated `PYTHONPATH`. If migrations fail, the script aborts immediately with zero downtime.
6. **Atomic Switch & Restart**: Swaps `/opt/sevapath/current` symlink and executes `systemctl restart sevapath`.
7. **Readiness Probe**: Queries `http://127.0.0.1:8000/health?check=ready`. If readiness fails within 15 seconds, automated code rollback is triggered.

---

## 6. Code Rollback Procedure (`rollback.sh`)

If an application defect is detected after activation:

```bash
sudo /opt/sevapath/current/deployment/scripts/rollback.sh
```

* **Responsibilities**:
  1. Reads `/opt/sevapath/.previous_release` to identify the previous known-good release.
  2. Atomically restores the `/opt/sevapath/current` symlink.
  3. Restarts Gunicorn (`systemctl restart sevapath`).
  4. Polls `/health?check=ready` until confirmed.
* **Strict Safety Guarantee**: Code rollback **never touches, overwrites, or modifies the production SQLite database**.

---

## 7. Manual Emergency Database Disaster Recovery Runbook

> [!CAUTION]
> This runbook is strictly for emergency disaster recovery (e.g. database corruption).  
> Never perform this procedure while application processes are running.

### Step 1: Terminate All Database-Accessing Processes
```bash
sudo systemctl stop sevapath
```
Verify zero processes retain open file descriptors to the database:
```bash
sudo fuser -v /opt/sevapath/shared/instance/sevapath.sqlite*
# Output must be completely empty before proceeding.
```

### Step 2: Forensically Preserve Current State & Sidecars
Archive the entire existing database triad (`.sqlite`, `.sqlite-wal`, `.sqlite-shm`) to an incident folder:
```bash
INCIDENT_DIR="/opt/sevapath/shared/backups/incident_$(date +%Y%m%d_%H%M%S)"
sudo mkdir -p "$INCIDENT_DIR"
sudo mv /opt/sevapath/shared/instance/sevapath.sqlite* "$INCIDENT_DIR/"
```

### Step 3: Restore Verified Snapshot
Copy the explicitly selected snapshot into place:
```bash
SNAPSHOT="/opt/sevapath/shared/backups/pre_deploy_<RELEASE_ID>_<TIMESTAMP>.sqlite"

sudo cp "$SNAPSHOT" /opt/sevapath/shared/instance/sevapath.sqlite
sudo chown sevapath:sevapath /opt/sevapath/shared/instance/sevapath.sqlite
sudo chmod 600 /opt/sevapath/shared/instance/sevapath.sqlite
```

### Step 4: Ensure Stale Sidecars are Absent
Confirm that no stale `-wal` or `-shm` sidecars exist in `instance/`:
```bash
test ! -f /opt/sevapath/shared/instance/sevapath.sqlite-wal && echo "WAL sidecar absent: OK"
test ! -f /opt/sevapath/shared/instance/sevapath.sqlite-shm && echo "SHM sidecar absent: OK"
```

### Step 5: Offline Pre-Boot Integrity Verification
Run offline integrity and foreign-key checks:
```bash
sqlite3 /opt/sevapath/shared/instance/sevapath.sqlite "PRAGMA integrity_check;"
# Must output: ok

sqlite3 /opt/sevapath/shared/instance/sevapath.sqlite "PRAGMA foreign_key_check;"
# Must output empty (zero violations)
```
If either check fails, **do not start the service**. Investigate the snapshot.

### Step 6: Resume Service & Verify Readiness
```bash
sudo systemctl start sevapath
curl -i http://127.0.0.1:8000/health?check=ready
# Must return: HTTP/1.1 200 OK
```

---

## 8. Concurrency & Performance Benchmarking

### 8.1 Restart Latency Benchmark Specification
Under single-node Gunicorn restart (`systemctl restart sevapath`), worker processes terminate and respawn within 400–600ms. Incoming requests queue inside the Linux socket listen backlog (`backlog=2048`).

To measure real-world performance under restart:
```bash
# In staging environment, simulate 20 concurrent clients querying service endpoints:
python3 -c '
import urllib.request, time, concurrent.futures

def fetch(i):
    t0 = time.time()
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health?check=ready", timeout=5) as r:
            return r.status, time.time() - t0
    except Exception as e:
        return str(e), time.time() - t0

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    futures = [ex.submit(fetch, i) for i in range(100)]
    results = [f.result() for f in futures]
    print(f"Completed: {len(results)}, Latencies: min={min(r[1] for r in results):.3f}s, max={max(r[1] for r in results):.3f}s")
'
```

### 8.2 SQLite WAL Durability Trade-offs
* **Durability Guarantee**: `PRAGMA synchronous = NORMAL;` in WAL mode guarantees that the database will not be corrupted by application or OS crashes.
* **Power-Loss Trade-off**: If the underlying physical host suffers an abrupt, ungraceful power loss, transactions committed since the last WAL checkpoint (typically $<1000$ pages or a few seconds) could be rolled back.
* **Single-Writer Constraint**: SQLite permits unlimited concurrent readers alongside one active writer. Multiple concurrent writes are safely queued by `PRAGMA busy_timeout = 5000;`.
