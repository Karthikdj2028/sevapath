# SevaPath: Windows Development Environment Setup Guide

**Project:** SevaPath — Tamil Nadu Citizen Preparation Platform  
**Target Environment:** Windows 10 / Windows 11 (PowerShell & Command Prompt)  
**Repository:** `https://github.com/Karthikdj2028/sevapath.git`  
**Application Platform:** Python 3.11+ / Flask / SQLite / Bootstrap 5 / ReportLab

---

## 1. Prerequisites Installation

### A. Install Python
1. Download Python (version **3.11** or **3.12** recommended; minimum **3.10+**) from [python.org](https://www.python.org/downloads/windows/).
2. Run the installer executable.
3. **IMPORTANT:** Check the box labeled **"Add python.exe to PATH"** before clicking Install Now.
4. Verify the installation in a new PowerShell window:
   ```powershell
   py --version
   # Output should display: Python 3.11.x (or 3.12.x / 3.13.x)
   ```

### B. Install Git for Windows
1. Download Git from [git-scm.com](https://git-scm.com/download/win).
2. Install with default recommended settings.
3. Verify in PowerShell:
   ```powershell
   git --version
   ```

---

## 2. Cloning the Repository

Open Windows PowerShell and navigate to your preferred workspace directory (e.g., `C:\Projects` or `C:\Users\<YourUsername>\Projects`):

```powershell
mkdir -p C:\Projects
cd C:\Projects

# Clone the repository from GitHub
git clone https://github.com/Karthikdj2028/sevapath.git
cd sevapath
```

> **IMPORTANT:** Always clone a fresh repository copy on Windows. **Do not** copy over a virtual environment directory (`venv`, `.venv`, or `env`) created on macOS or Linux. Virtual environments contain platform-specific binaries, C-extensions, and activation scripts that will not function on Windows.

---

## 3. Creating and Activating the Python Virtual Environment

Use the Python launcher (`py`) to create an isolated virtual environment:

```powershell
# 1. Create a virtual environment named .venv
py -m venv .venv

# 2. Activate the virtual environment in PowerShell
.venv\Scripts\Activate.ps1
```

Once activated, your PowerShell prompt will show `(.venv)` at the beginning:
```powershell
(.venv) PS C:\Projects\sevapath>
```

*(If you encounter a script execution restriction, refer to the [Troubleshooting](#troubleshooting) section below.)*

---

## 4. Installing Dependencies

Upgrade `pip` and install project runtime and test dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verify the key packages are installed:
```powershell
pip list
# Verify Flask (>=3.0.0), reportlab (>=4.0.0), pytest (>=8.0.0), Werkzeug (>=3.0.0)
```

---

## 5. Development Configuration & Environment Variables

SevaPath uses environment variables to configure its operational environment, secret key, and database path.

### Development Environment Defaults
For local development, sensible defaults are automatically loaded:
* `FLASK_ENV`: Defaults to `development`
* `SECRET_KEY`: Uses the internal development fallback
* `DATABASE_PATH`: Defaults to `instance\sevapath.sqlite` (created automatically)

### Optional Custom Environment Variables in PowerShell
If you wish to set explicit variables for your session:

```powershell
# Set environment variables for the current PowerShell session
$env:FLASK_ENV = "development"
$env:SECRET_KEY = "sevapath-dev-insecure-secret-key-2026"
$env:PORT = "5000"
```

> **SECURITY NOTICE:**
> * Never copy production secrets, API credentials, or certificates into your local Windows development environment.
> * Local SQLite databases (`*.sqlite`) and local environment configuration files (`.env`) are listed in `.gitignore` and **must never be committed to Git**.

---

## 6. Running the Automated Test Suite

Before starting the server, verify the integrity of the application by running the full automated test suite:

```powershell
python -m pytest -v
```

Expected result:
```text
============================= 130 passed in 0.60s ==============================
```

All 130 tests use dynamic, isolated temporary databases allocated by `tests/conftest.py` that do not touch or modify your local development database.

---

## 7. Starting the Development Server

Start the application using the project runner:

```powershell
python run.py
```

Expected console output:
```text
Starting SevaPath server on http://127.0.0.1:5000 (Debug: True)...
 * Serving Flask app 'app'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
```

Open your browser and navigate to:
* **Citizen Dashboard:** `http://localhost:5000/`
* **Tamil Interface:** `http://localhost:5000/?lang=ta`
* **Income Certificate Preparation:** `http://localhost:5000/service/income-certificate`
* **Community Certificate Preparation:** `http://localhost:5000/service/community-certificate`
* **Nativity Certificate Preparation:** `http://localhost:5000/service/nativity-certificate`
* **System Health Check:** `http://localhost:5000/health`

Press `Ctrl + C` in PowerShell to stop the development server.

---

## 8. Deactivating and Managing the Environment

### Deactivating the Virtual Environment
When finished working on the project:
```powershell
deactivate
```

### Pulling Future Updates from GitHub
Before starting a new work session, pull the latest commits from the `main` branch:
```powershell
cd C:\Projects\sevapath
git pull origin main

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Update any new dependencies
pip install -r requirements.txt

# Run tests to confirm integrity
python -m pytest -v
```

---

## Troubleshooting

### 1. PowerShell Script Execution Policy Error
**Symptom:**
```text
.venv\Scripts\Activate.ps1 : File cannot be loaded because running scripts is disabled on this system.
```
**Cause:** Windows PowerShell restricts running external scripts by default.  
**Solution:** Enable script execution for your current PowerShell process (does not require administrator rights):
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
# or
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Then activate the environment again:
.venv\Scripts\Activate.ps1
```

Alternatively, use Windows Command Prompt (`cmd.exe`):
```cmd
.venv\Scripts\activate.bat
```

### 2. `'py'` or `'python'` is Not Recognized
**Symptom:**
```text
'py' is not recognized as an internal or external command...
```
**Cause:** Python was installed without checking "Add python.exe to PATH".  
**Solution:**
1. Re-run the Python Windows installer.
2. Select **Modify**.
3. Ensure **"Add Python to environment variables"** is checked and complete installation.
4. Restart PowerShell.

### 3. ReportLab or C-Extension Installation Issues
**Symptom:** Pip errors related to building wheels or missing compilers when installing ReportLab.  
**Solution:** Ensure pip is upgraded to the latest version before installing requirements:
```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```
Pre-compiled Windows wheels are provided automatically by ReportLab for Python 3.10–3.13.

### 4. SQLite Path or Permission Issues
**Symptom:** `sqlite3.OperationalError: unable to open database file`  
**Cause:** The `instance` directory does not exist or has restrictive folder permissions.  
**Solution:** The application automatically creates the `instance` folder via `os.makedirs()`. Ensure you have write permissions to your working directory, or manually create the folder:
```powershell
mkdir -Force instance
```

---

## Project Structure Quick Reference

```text
sevapath/
├── app/
│   ├── core/              # Security, DFA engine, PDF generator, regex validator
│   ├── data/              # Initial seed data for civic services (seeds.py)
│   ├── models/            # Database schema, migrations, queries (database.py)
│   ├── routes/            # Blueprints: main.py, api.py, reports.py
│   ├── static/            # CSS, Bootstrap, JavaScript assets
│   ├── templates/         # Jinja templates (index, service_detail, print, errors)
│   ├── translations.py    # Bilingual UI translation dictionaries (en, ta)
│   └── __init__.py        # Flask application factory (create_app)
├── config.py              # Development, testing, and production configurations
├── docs/                  # Architectural assessments and setup documentation
├── instance/              # Local SQLite database (sevapath.sqlite - git-ignored)
├── requirements.txt       # Project dependencies
├── run.py                 # Development application runner
└── tests/                 # Automated pytest test suites (130 tests)
```
