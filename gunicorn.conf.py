"""
Gunicorn production server configuration for SevaPath.

Network Binding & Security Boundaries:
- Default: 127.0.0.1:8000 (loopback). In a traditional VPS deployment, Nginx runs on
  the same host and is the sole public HTTP entry point. Gunicorn must remain on loopback
  so external clients cannot bypass Nginx or forge forwarded proxy headers.
- Container / Cloud: Set GUNICORN_BIND via environment variable (e.g. '0.0.0.0:8000').
  Binding to 0.0.0.0 inside a container is safe only when the container platform enforces
  private service networking, ensuring the application port is inaccessible to untrusted
  public clients and reached only via the platform's trusted ingress proxy.
- ProxyFix is an application-level header adapter, NOT a firewall or peer-authentication
  mechanism. Network boundaries must enforce that only the trusted reverse proxy can reach Gunicorn.

Concurrency & Performance:
- Gunicorn's two-worker, two-thread configuration is a conservative initial concurrency setting. SQLite serializes writes, so this configuration does not eliminate database lock contention. Production suitability must be evaluated through realistic concurrent-write testing and operational monitoring.
"""

import os

# Network binding: default to loopback (127.0.0.1:8000) for VPS / host security
bind = os.environ.get("GUNICORN_BIND", f"127.0.0.1:{os.environ.get('PORT', '8000')}")

# Initial conservative concurrency settings for SQLite
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
worker_class = "gthread"

# Request timeouts
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
graceful_timeout = 30
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# Process naming
proc_name = "sevapath"
