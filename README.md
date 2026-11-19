# SevaPath (சேவாபாத்)

> **An Offline-First, Bilingual Public Service Readiness and Document Validation System Using Finite State Automata.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)](https://palletsprojects.com/p/flask/)
[![Database](https://img.shields.io/badge/Database-SQLite3-lightgrey.svg)](https://sqlite.org/)
[![Region](https://img.shields.io/badge/Region-Tamil%20Nadu%2C%20India-orange.svg)](https://www.tnesevai.tn.gov.in)
[![License](https://img.shields.io/badge/License-Open%20Source-purple.svg)](LICENSE)

---

## 1. Project Overview

**SevaPath** is an open-source civic assistance web application developed for citizens in **Tamil Nadu, India**. It helps citizens understand official public service requirements, prepare required documents, identify missing proofs, and build readiness checklists before visiting government offices or e-Sevai centres.

### Initial Services Supported:
1. **Income Certificate (வருமானச் சான்றிதழ்)** – Revenue Administration Department, TN
2. **Community Certificate (சாதிச் சான்றிதழ்)** – Revenue & BC/MBC Welfare Department, TN
3. **Nativity Certificate (இருப்பிடச் சான்றிதழ்)** – Revenue Administration Department, TN

---

## 2. Architecture & Design Principles

SevaPath is designed strictly following the lightweight, academic, and privacy-first technology stack:

- **Frontend**: HTML5, CSS3, Bootstrap 5.3 (vendored locally for offline support), Vanilla JavaScript.
- **Backend**: Python 3, Flask Application Factory pattern.
- **Database**: SQLite with strict `PRAGMA foreign_keys = ON;` enforcement and normalized tables.
- **Bilingual System**: Reusable English & Tamil (`ta`) translation dictionary and contextual templates (no duplicated HTML pages).
- **Academic DFA Engine**: Mathematically genuine Deterministic Finite Automaton $M = (Q, \Sigma, \delta, q_0, F)$ tracking document readiness with bitmask states, absorbing sink state $q_{sink}$, order-independence, and live SVG state visualization.
- **Privacy & Security**: Zero Aadhaar numbers collected, no citizen file uploads stored, parameterized SQL queries against SQL injection.

```
sevapath/
├── config.py              # Configuration classes (Dev, Testing, Prod)
├── run.py                 # Flask server runner & CLI entry point
├── requirements.txt       # Project dependencies
├── .gitignore             # Git exclusions (database, cache, secrets)
├── app/
│   ├── __init__.py        # Application factory (create_app)
│   ├── translations.py    # English & Tamil UI translation system
│   ├── core/              # Core algorithmic logic
│   │   └── dfa_engine.py  # Deterministic Finite Automaton (DFA) engine
│   ├── models/
│   │   └── database.py    # SQLite schema, connections, and query helpers
│   ├── data/
│   │   └── seeds.py       # Seed data for verified Tamil Nadu services
│   ├── routes/
│   │   └── main.py        # Routes (Home, Directory, Service Details, Health)
│   ├── static/
│   │   ├── css/
│   │   │   ├── bootstrap.min.css # Vendored Bootstrap 5.3
│   │   │   └── custom.css        # Civic tech styles & Tamil typography
│   │   └── js/
│   │       ├── bootstrap.bundle.min.js
│   │       └── app.js            # Client-side live search & UX helpers
│   └── templates/
│       ├── base.html             # Base layout with navbar & language switcher
│       ├── index.html            # Responsive homepage & searchable catalog
│       ├── service_detail.html   # Service document requirement breakdown
│       └── errors/
│           ├── 404.html          # Custom 404 page
│           └── 500.html          # Custom 500 error page
└── tests/
    ├── conftest.py               # Pytest fixtures and test database setup
    ├── test_app.py               # Application factory & endpoint tests
    ├── test_database.py          # SQLite schema & query tests
    └── test_translations.py      # Bilingual translation & switcher tests
```

---

## 3. Database Schema

The database is normalized into 7 tables with strict foreign keys and cascade delete rules:

- `services`: Master record with unique slug and issuing department.
- `service_translations`: Bilingual names, descriptions, expected processing timelines, and official statutory fees.
- `official_sources`: Official government portal URLs (e.g., TNeGA), verification dates, and jurisdiction.
- `requirements`: Specific document items (is_mandatory flag, document type, order).
- `requirement_translations`: English and Tamil title, detailed descriptions, and citizen upload help text.
- `preparation_sessions`: Anonymous citizen checklist sessions.
- `session_items`: Per-document checklist state transitions.

---

## 4. Quick Start & Installation

### Step 1: Clone or Navigate to the Project
```bash
cd ~/Downloads/sevapath
```

### Step 2: Set up a Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Initialize the SQLite Database
```bash
FLASK_APP=run.py python3 -m flask init-db
```
*This creates the database at `instance/sevapath.sqlite` and loads the verified Tamil Nadu service seeds.*

### Step 5: Start the Application
```bash
python3 run.py
```
Open your browser and navigate to: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 5. Running Automated Tests

Run the complete test suite using `pytest`:

```bash
python3 -m pytest -v
```

All 13 tests verify:
- Flask application initialization & health-check endpoint.
- Homepage 200 OK rendering with brand assets.
- SQLite foreign key constraint enforcement and cascade deletion.
- Retrieval of services in English and Tamil.
- Reusable translation dictionary symmetry and language toggle redirect.

---

## 6. Language Support (English & தமிழ்)

You can toggle between English and Tamil at any time using the navigation bar switch or URL parameters:
- **English**: `http://127.0.0.1:5000/?lang=en`
- **Tamil**: `http://127.0.0.1:5000/?lang=ta`

Preferences are remembered automatically via cookies and session storage.

---

## 7. Civic Responsibility & Privacy Notice

- **No Personal Data Collection**: SevaPath does **not** collect Aadhaar numbers, PAN numbers, or store uploaded personal certificates.
- **Independent Tool**: SevaPath is an educational, open-source civic readiness assistant. It is **not** an official government portal.
- **No Approval Guarantee**: The application prepares citizens with correct document checklists, but final approval is determined strictly by authorized Government of Tamil Nadu officials under the Tamil Nadu Revenue Administration rules.
