"""
models.py
All database models for the Software Quality and Metrics Analysis Tool.
Single SQLite database shared by every module.
"""
import secrets
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def utcnow():
    """Naive UTC 'now' (datetime.utcnow() is deprecated on Python 3.12+)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    full_name = db.Column(db.String(120), default="")
    email = db.Column(db.String(160), default="")
    password_hash = db.Column(db.String(300), nullable=False)
    role = db.Column(db.String(20), default="Developer")          # Admin / Developer / Tester
    api_token = db.Column(db.String(80), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def regenerate_token(self):
        self.api_token = secrets.token_urlsafe(32)
        return self.api_token

    @property
    def display_name(self):
        return self.full_name or self.username

    @property
    def is_admin(self):
        return self.role == "Admin"


class Project(db.Model):
    __tablename__ = "project"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    bugs = db.relationship("Bug", backref="project", cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="project", cascade="all, delete-orphan")
    releases = db.relationship("Release", backref="project", cascade="all, delete-orphan")
    code_files = db.relationship("CodeFile", backref="project", cascade="all, delete-orphan")
    analysis_runs = db.relationship("AnalysisRun", backref="project", cascade="all, delete-orphan")
    predictions = db.relationship("Prediction", backref="project", cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="project", cascade="all, delete-orphan")


class Release(db.Model):
    __tablename__ = "release"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    name = db.Column(db.String(60), nullable=False)                # e.g. v1.0
    release_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="Planned")           # Planned / Released

    bugs = db.relationship("Bug", backref="release", foreign_keys="Bug.release_id")


class Bug(db.Model):
    __tablename__ = "bug"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    title = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text, default="")
    module = db.Column(db.String(120), default="General")
    severity = db.Column(db.String(20), default="Medium")          # Low / Medium / High / Critical
    priority = db.Column(db.String(20), default="Medium")          # Low / Medium / High
    status = db.Column(db.String(20), default="Open")              # Open / In Progress / Resolved / Reopened / Closed
    reopened_count = db.Column(db.Integer, default=0)
    found_in = db.Column(db.String(20), default="Testing")         # Testing / Production
    owasp_category = db.Column(db.String(80), default="None")
    cvss_score = db.Column(db.Float, nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    release_id = db.Column(db.Integer, db.ForeignKey("release.id"), nullable=True)
    code_file_id = db.Column(db.Integer, db.ForeignKey("code_file.id"), nullable=True)   # used from Phase 2
    source_issue_id = db.Column(db.Integer, nullable=True)                               # used from Phase 2
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    assignee = db.relationship("User", backref="assigned_bugs", foreign_keys=[assignee_id])
    code_file = db.relationship("CodeFile", foreign_keys=[code_file_id])
    comments = db.relationship("BugComment", backref="bug", cascade="all, delete-orphan",
                               order_by="BugComment.created_at")


class CodeFile(db.Model):
    __tablename__ = "code_file"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    filename = db.Column(db.String(250), nullable=False)
    filepath = db.Column(db.String(400), nullable=False)
    loc = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=utcnow)
    # ---- cached per-file numbers (filled at upload / re-analyse so lists are fast) ----
    relpath = db.Column(db.String(400), default="")            # path inside the project, e.g. src/app/main.py
    language = db.Column(db.String(20), default="Python")
    basic_metrics = db.Column(db.Boolean, default=False)       # True for Java/JS/C/C++ (basic metrics only)
    size_bytes = db.Column(db.Integer, default=0)
    comment_lines = db.Column(db.Integer, default=0)
    num_functions = db.Column(db.Integer, default=0)
    num_classes = db.Column(db.Integer, default=0)
    num_imports = db.Column(db.Integer, default=0)
    avg_cc = db.Column(db.Float, default=0)
    max_cc = db.Column(db.Integer, default=0)
    max_nesting = db.Column(db.Integer, default=0)
    mi_score = db.Column(db.Float, default=100)
    mi_band = db.Column(db.String(40), default="")
    issue_count = db.Column(db.Integer, default=0)
    high_issue_count = db.Column(db.Integer, default=0)
    security_count = db.Column(db.Integer, default=0)
    parse_error = db.Column(db.Text, default="")

    metrics = db.relationship("CodeMetric", backref="code_file", cascade="all, delete-orphan")
    issues = db.relationship("Issue", backref="code_file", cascade="all, delete-orphan")

    @property
    def folder(self):
        p = (self.relpath or self.filename).replace("\\", "/")
        return p.rsplit("/", 1)[0] if "/" in p else ""


class CodeMetric(db.Model):
    __tablename__ = "code_metric"
    id = db.Column(db.Integer, primary_key=True)
    code_file_id = db.Column(db.Integer, db.ForeignKey("code_file.id"), nullable=False)
    metric_name = db.Column(db.String(100), nullable=False)
    metric_value = db.Column(db.Float, default=0)
    unit_name = db.Column(db.String(150), default="")


class AnalysisRun(db.Model):
    __tablename__ = "analysis_run"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    run_type = db.Column(db.String(50), nullable=False)
    result_json = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=utcnow)


class Prediction(db.Model):
    __tablename__ = "prediction"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    model_type = db.Column(db.String(50), nullable=False)
    result_json = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=utcnow)


class StatisticalResult(db.Model):
    __tablename__ = "statistical_result"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    analysis_type = db.Column(db.String(50), nullable=False)
    result_json = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=utcnow)


class SecurityIssue(db.Model):
    __tablename__ = "security_issue"
    id = db.Column(db.Integer, primary_key=True)
    code_file_id = db.Column(db.Integer, db.ForeignKey("code_file.id"), nullable=False)
    issue_type = db.Column(db.String(150), nullable=False)
    severity = db.Column(db.String(20), default="Medium")
    line_number = db.Column(db.Integer, default=0)
    description = db.Column(db.Text, default="")

    code_file = db.relationship("CodeFile", backref="security_issues")


class Alert(db.Model):
    __tablename__ = "alert"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20), default="Info")               # Info / Warning / Critical
    source = db.Column(db.String(10), default="manual")            # bug / code / manual
    created_at = db.Column(db.DateTime, default=utcnow)


class Issue(db.Model):
    """A code issue found by the analyzers (requirement 30)."""
    __tablename__ = "issue"
    id = db.Column(db.Integer, primary_key=True)
    code_file_id = db.Column(db.Integer, db.ForeignKey("code_file.id"), nullable=False)
    line_number = db.Column(db.Integer, default=0)
    issue_type = db.Column(db.String(150), nullable=False)
    severity = db.Column(db.String(20), default="Medium")          # Low / Medium / High
    description = db.Column(db.Text, default="")
    fix_suggestion = db.Column(db.Text, default="")
    category = db.Column(db.String(30), default="Style")           # Security / Complexity / Maintainability / Style
    logged_bug_id = db.Column(db.Integer, nullable=True)           # Bug created from this issue (no FK: survives bug delete check)


class BugComment(db.Model):
    """Comment on a bug (used by 'Save AI answer as comment')."""
    __tablename__ = "bug_comment"
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.Integer, db.ForeignKey("bug.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    text = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(10), default="user")              # user / ai
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User")


class ChatMessage(db.Model):
    """AI Assistant chat history, per project and user."""
    __tablename__ = "chat_message"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(10), nullable=False)                # user / model
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
