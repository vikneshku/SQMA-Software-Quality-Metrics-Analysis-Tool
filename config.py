"""
config.py
Single place for constants and thresholds used across the tool.
Change a value here and every page, the REST API and the Report page follow.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "sqma.db")

# Automatically load environment variables from .env if present
def _load_dotenv():
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.isfile(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

_load_dotenv()

# ---------------- Bugs ----------------
SEVERITIES = ["Low", "Medium", "High", "Critical"]
PRIORITIES = ["Low", "Medium", "High"]
STATUSES = ["Open", "In Progress", "Resolved", "Reopened", "Closed"]
OPEN_STATUSES = ("Open", "In Progress", "Reopened")
CLOSED_STATUSES = ("Resolved", "Closed")
FOUND_IN = ["Testing", "Production"]

# One list used by forms, filters, API and validation (requirement 5)
OWASP_NONE = "None"
OWASP_CATEGORIES = [
    "None",
    "SQL Injection",
    "Cross-Site Scripting (XSS)",
    "Broken Authentication",
    "Broken Access Control",
    "Sensitive Data Exposure",
    "Security Misconfiguration",
    "Insecure Deserialization",
    "Using Components with Known Vulnerabilities",
    "Insufficient Logging and Monitoring",
    "Server-Side Request Forgery (SSRF)",
    "Cross-Site Request Forgery (CSRF)",
    "Other",
]

# ---------------- Users ----------------
ROLES = ["Admin", "Developer", "Tester"]
ASSIGNABLE_ROLES = ("Developer", "Tester")
MIN_PASSWORD_LENGTH = 8

# ---------------- Releases ----------------
RELEASE_STATUSES = ["Planned", "Released"]

# ---------------- Alerts ----------------
AGING_BUG_DAYS = 30            # a bug open longer than this raises an aging alert
CRITICAL_CVSS = 7.0            # CVSS >= 7.0 counts as High-or-above security bug

# ---------------- Release readiness (requirement 15) ----------------
READINESS = {
    "red_open_critical": 1,          # >= 1 open Critical bug -> Red
    "red_open_high": 3,              # >= 3 open High bugs -> Red
    "red_security_cvss": 9.0,        # any open security bug with CVSS >= 9 -> Red
    "yellow_open_high": 1,           # >= 1 open High bug -> Yellow
    "yellow_old_bug_days": AGING_BUG_DAYS,   # any open bug older than this -> Yellow
    # Yellow also when open bugs > closed bugs.
}

# ---------------- Maintainability bands (requirement 19) ----------------
MI_BANDS = {"high": 55.0, "moderate": 40.0}   # >=55 Highly, >=40 Moderately, else Difficult
MI_LOW_THRESHOLD = MI_BANDS["moderate"]       # "low maintainability" evidence / alert level

# ---------------- Statistics options (requirement 24) ----------------
VARIANCE_TYPES = ["sample", "population"]
SIGMA_CHOICES = [1, 2, 3]
DEFAULT_VARIANCE = "sample"
DEFAULT_SIGMA = 3
ALPHA = 0.05
DEFAULT_COMPLEXITY_TARGET = 10.0

# ---------------- Upload limits (requirements 27, 28, 33) - ONE config block ----------------
MAX_UPLOAD_BYTES = 100 * 1024 * 1024      # total request size
MAX_FILES = 50                            # counted AFTER junk is skipped
MAX_FILE_BYTES = 2 * 1024 * 1024          # a single file over this is skipped
SKIP_DIRS = {"venv", ".venv", "env", "node_modules", ".git", "__pycache__", "build", "dist",
             ".idea", ".vscode", "site-packages", "target", "bin", "obj"}
SUPPORTED_EXTS = {".py": "Python", ".java": "Java", ".js": "JavaScript", ".c": "C", ".h": "C",
                  ".cpp": "C++", ".cc": "C++", ".hpp": "C++"}
BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".pdf", ".zip", ".gz", ".tar", ".7z",
               ".rar", ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".pyc", ".pyo", ".o", ".obj", ".a",
               ".lib", ".bin", ".dat", ".db", ".sqlite", ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ttf",
               ".woff", ".woff2", ".eot", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}

# ---------------- Code issue rules (requirement 30) ----------------
ISSUE_LIMITS = {"complex": 10, "very_complex": 20, "long_function": 50, "very_long_function": 100,
                "max_params": 5, "max_nesting": 4}
ISSUE_CATEGORIES = ["Security", "Complexity", "Maintainability", "Style"]

# issue type keyword -> OWASP category used by "Log as bug" (requirement 32)
OWASP_BY_KEYWORD = [
    ("sql", "SQL Injection"), ("pickle", "Insecure Deserialization"), ("innerhtml", "Cross-Site Scripting (XSS)"),
    ("document.write", "Cross-Site Scripting (XSS)"), ("hardcoded", "Sensitive Data Exposure"),
    ("password", "Sensitive Data Exposure"), ("eval", "Other"), ("exec", "Other"), ("system", "Other"),
    ("shell", "Other"), ("gets", "Other"), ("strcpy", "Other"), ("sprintf", "Other"), ("assert", "Security Misconfiguration"),
]

# ---------------- AI (Phase 3) ----------------
GEMINI_DEFAULT_MODEL = "gemini-1.5-flash"
AI_TIMEOUT_SECONDS = 40
