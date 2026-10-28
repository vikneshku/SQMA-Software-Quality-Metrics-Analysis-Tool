"""
auth.py
Authentication, CSRF protection, roles, the Users page and the profile / API-token page.

* Passwords are hashed with werkzeug.security; the login lives in the Flask session.
* The FIRST registered user becomes Admin, later registrations become Developers.
* Every page except login / register / static requires a login (the REST API does its own
  401-JSON authentication in api.py).
* CSRF: a per-session token, checked on every POST (templates add it with csrf_token()).
"""
import hmac
import re
import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, session, url_for)

from config import ROLES, MIN_PASSWORD_LENGTH
from models import db, User, Bug
from config import OPEN_STATUSES

bp = Blueprint("auth", __name__)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")
PUBLIC_ENDPOINTS = {"auth.login", "auth.register", "static"}


# ---------------------------------------------------------------- CSRF
def csrf_token():
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok


def csrf_ok(supplied):
    expected = session.get("_csrf")
    return bool(expected and supplied and hmac.compare_digest(str(expected), str(supplied)))


# ---------------------------------------------------------------- decorators
def admin_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not g.user or not g.user.is_admin:
            abort(403)
        return view(*a, **kw)
    return wrapper


def safe_next(target):
    """Only allow redirects to a local path."""
    if not target:
        return None
    p = urlparse(target)
    if p.scheme or p.netloc or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    return target


# ---------------------------------------------------------------- app wiring
def init_app(app):
    app.register_blueprint(bp)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def load_user_and_guard():
        g.user = db.session.get(User, session["user_id"]) if session.get("user_id") else None
        ep = request.endpoint
        if ep is None or (ep and ep.startswith("api.")):
            return None                                   # API authenticates itself (401 JSON)
        if request.method == "POST" and ep != "static":
            if not csrf_ok(request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")):
                flash("Your session expired or the form was invalid. Please try again.", "danger")
                return redirect(request.referrer or url_for("auth.login")), 303
        if ep in PUBLIC_ENDPOINTS:
            return None
        if g.user is None:
            nxt = request.full_path if request.method == "GET" else None
            return redirect(url_for("auth.login", next=safe_next(nxt.rstrip("?")) if nxt else None))
        return None

    @app.context_processor
    def inject_user():
        return {"current_user": g.get("user")}


# ---------------------------------------------------------------- login / register / logout
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
        if user and user.check_password(request.form.get("password", "")):
            session.clear()
            session["user_id"] = user.id
            csrf_token()
            flash(f"Welcome back, {user.display_name}.", "success")
            return redirect(safe_next(request.args.get("next")) or url_for("index"))
        flash("Wrong username or password.", "danger")
    return render_template("login.html", has_users=User.query.count() > 0)


def _validate_user_fields(form, creating, existing=None):
    errors = {}
    username = form.get("username", "").strip()
    if creating:
        if not USERNAME_RE.match(username):
            errors["username"] = "Username must be 3-40 characters: letters, digits, dot, dash or underscore."
        elif User.query.filter(db.func.lower(User.username) == username.lower()).first():
            errors["username"] = "That username is already taken."
    email = form.get("email", "").strip()
    if email and (len(email) > 160 or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email)):
        errors["email"] = "Enter a valid e-mail address."
    full_name = form.get("full_name", "").strip()
    if len(full_name) > 120:
        errors["full_name"] = "Full name is too long."
    pw = form.get("password", "")
    if creating or pw:
        if len(pw) < MIN_PASSWORD_LENGTH:
            errors["password"] = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        elif pw != form.get("password2", pw):
            errors["password"] = "The two passwords do not match."
    return errors, username, email, full_name, pw


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("index"))
    first = User.query.count() == 0
    if request.method == "POST":
        errors, username, email, full_name, pw = _validate_user_fields(request.form, True)
        if errors:
            for msg in errors.values():
                flash(msg, "danger")
        else:
            u = User(username=username, email=email, full_name=full_name,
                     role="Admin" if first else "Developer")
            u.set_password(pw)
            u.regenerate_token()
            db.session.add(u)
            db.session.commit()
            session.clear()
            session["user_id"] = u.id
            csrf_token()
            flash("Account created" + (" - you are the Admin." if first else "."), "success")
            return redirect(url_for("index"))
    return render_template("register.html", first=first)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------- profile + token
@bp.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "token":
            g.user.regenerate_token()
            db.session.commit()
            flash("New API token generated. The old token no longer works.", "success")
        elif action == "password":
            if not g.user.check_password(request.form.get("current", "")):
                flash("Current password is wrong.", "danger")
            else:
                errors, *_ = _validate_user_fields(
                    {"password": request.form.get("password", ""), "password2": request.form.get("password2", "")},
                    creating=False)
                if not request.form.get("password"):
                    errors["password"] = "Enter a new password."
                if errors:
                    for msg in errors.values():
                        flash(msg, "danger")
                else:
                    g.user.set_password(request.form["password"])
                    db.session.commit()
                    flash("Password changed.", "success")
        return redirect(url_for("auth.profile"))
    if not g.user.api_token:
        g.user.regenerate_token()
        db.session.commit()
    return render_template("profile.html")


# ---------------------------------------------------------------- users page (Admin manages)
def _open_bug_counts():
    rows = (db.session.query(Bug.assignee_id, db.func.count(Bug.id))
            .filter(Bug.assignee_id.isnot(None), Bug.status.in_(OPEN_STATUSES))
            .group_by(Bug.assignee_id).all())
    return dict(rows)


def _ctx_project():
    """Optional ?project=<id> keeps the project sidebar visible on the Users pages."""
    from models import Project
    pid = request.args.get("project", type=int)
    return db.session.get(Project, pid) if pid else None


@bp.route("/users")
def users():
    counts = _open_bug_counts()
    return render_template("users.html", users=User.query.order_by(User.username).all(),
                           counts=counts, roles=ROLES, project=_ctx_project(), active="users")


@bp.route("/users/new", methods=["POST"])
@admin_required
def user_new():
    errors, username, email, full_name, pw = _validate_user_fields(request.form, True)
    role = request.form.get("role", "Developer")
    if role not in ROLES:
        errors["role"] = "Unknown role."
    if errors:
        for msg in errors.values():
            flash(msg, "danger")
    else:
        u = User(username=username, email=email, full_name=full_name, role=role)
        u.set_password(pw)
        u.regenerate_token()
        db.session.add(u)
        db.session.commit()
        flash(f"User {username} added.", "success")
    return redirect(url_for("auth.users"))


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    u = db.get_or_404(User, user_id)
    if request.method == "POST":
        errors, _un, email, full_name, pw = _validate_user_fields(request.form, False)
        role = request.form.get("role", u.role)
        if role not in ROLES:
            errors["role"] = "Unknown role."
        if u.role == "Admin" and role != "Admin" and User.query.filter_by(role="Admin").count() <= 1:
            errors["role"] = "You cannot remove the last Admin."
        if errors:
            for msg in errors.values():
                flash(msg, "danger")
        else:
            u.email, u.full_name, u.role = email, full_name, role
            if pw:
                u.set_password(pw)
            db.session.commit()
            flash("User updated.", "success")
            return redirect(url_for("auth.users"))
    return render_template("user_edit.html", u=u, roles=ROLES, project=_ctx_project(), active="users")


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def user_delete(user_id):
    u = db.get_or_404(User, user_id)
    if u.id == g.user.id:
        flash("You cannot delete your own account.", "danger")
    elif u.role == "Admin" and User.query.filter_by(role="Admin").count() <= 1:
        flash("You cannot delete the last Admin.", "danger")
    else:
        Bug.query.filter_by(assignee_id=u.id).update({"assignee_id": None})
        db.session.delete(u)
        db.session.commit()
        flash("User deleted; their bugs are now unassigned.", "info")
    return redirect(url_for("auth.users"))


# ---------------------------------------------------------------- friendly error pages
def register_error_pages(app):
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, title="Not allowed",
                               message="Only an Admin can do that."), 403

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            from flask import jsonify
            return jsonify({"data": None, "error": "Not found."}), 404
        return render_template("error.html", code=404, title="Page not found",
                               message="That page or record does not exist."), 404
