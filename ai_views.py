"""
ai_views.py
Blueprint "ai": AI Assistant chat page, "Ask AI" on a bug, bug comments and AI recommendations
(requirements 16-18). Every AI call is wrapped so a missing key, no internet, a rate limit or a
timeout shows a friendly message instead of an error page.
"""
import os
from flask import Blueprint, abort, g, jsonify, render_template, request

from config import BASE_DIR, GEMINI_DEFAULT_MODEL
from ai.context import build_project_context
from ai.provider import AIError, SETUP_STEPS, get_provider
from alerts_engine import recompute_bug_alerts
from metrics_summary import project_summary
from metrics.defect_metrics import is_open, is_closed
from models import db, Project, Bug, BugComment, ChatMessage, Alert, utcnow

bp = Blueprint("ai", __name__)
HISTORY_LIMIT = 12          # last messages sent to the AI with each question
MAX_QUESTION = 2000


def _project(pid):
    return db.get_or_404(Project, pid)


def _friendly(err):
    return {"ok": False, "kind": err.kind, "message": err.message}


def answer_project_question(project, question):
    """Local intelligent metrics assistant: answers project quality questions using real numbers."""
    q = question.lower()
    s = project_summary(project.id)
    a = s["analysis"]
    oc = s["open_closed"]
    mods = s["modules"]
    rels = s["release_rows"]

    # 1. Module risk queries: "which module is more risk", "riskiest module", "module risk"
    if any(w in q for w in ("module", "component")) or ("risk" in q and not any(w in q for w in ("file", "predict"))):
        if not mods:
            return (f"In project **{project.name}**, no bugs have been logged under specific modules yet. "
                    "Once you log bugs in **Bug Management** with their respective module names, "
                    "their defect risk scores will appear here.")
        sorted_mods = sorted(mods.items(), key=lambda item: item[1]["risk_score"], reverse=True)
        top_mod, top_data = sorted_mods[0]
        lines = [
            f"Based on the project metrics for **{project.name}**, the module with the highest risk is **{top_mod}**.\n",
            f"- **Risk Level**: **{top_data['risk_level']}** (Score: {top_data['risk_score']})",
            f"- **Defects**: {top_data['bug_count']} total ({top_data['open_count']} open, {top_data['critical']} Critical, {top_data['high']} High)",
            f"- **Average CVSS**: {top_data['avg_cvss'] if top_data['avg_cvss'] is not None else 'None'}",
            "",
            "**Module Risk Breakdown:**"
        ]
        for m_name, m_info in sorted_mods:
            lines.append(f"- **{m_name}**: Risk Score {m_info['risk_score']} ({m_info['risk_level']} risk) — {m_info['bug_count']} bugs ({m_info['open_count']} open)")
        lines.append(f"\n**Recommendation**: Prioritize resolving the {top_data['open_count']} open defect(s) in `{top_mod}` to reduce system risk.")
        return "\n".join(lines)

    # 2. Release readiness queries: "release", "ready", "shipping"
    if any(w in q for w in ("release", "ready", "ship")):
        if not rels:
            return (f"No releases have been configured for **{project.name}** yet. "
                    "You can create planned or released milestones on the **Releases** page.")
        latest = s["latest_release"]
        lines = [
            f"**Release Readiness Status for {project.name}:**\n",
            f"- **Latest Release**: **{latest['name']}**",
            f"- **Readiness Traffic Light**: **{latest['readiness']['color']}**",
            f"- **Bugs Assigned**: {latest['total']} ({latest['open']} open, {latest['closed']} closed)",
            f"- **Critical / High Defects**: {latest['critical_high']}",
            f"- **Escape Rate**: {latest['escape_rate']}% ({latest['escaped']} found in Production)",
            "",
            "**Readiness Reasons & Criteria:**"
        ]
        for r in latest["readiness"]["reasons"]:
            lines.append(f"- {r}")
        if latest["readiness"]["color"] != "Green":
            lines.append("\n**Action to reach Green**: Resolve all open Critical defects, keep open High defects under 3, and resolve any aging bugs older than 30 days.")
        else:
            lines.append("\n**Verdict**: Release criteria met! All quality gates are satisfied.")
        return "\n".join(lines)

    # 3. Recommendations / what to fix first
    if any(w in q for w in ("fix", "first", "recommend", "priority", "action")):
        actions = []
        open_bugs = [b for b in s["bugs"] if is_open(b)]
        crits = [b for b in open_bugs if b.severity == "Critical"]
        highs = [b for b in open_bugs if b.severity == "High"]
        sec_bugs = [b for b in open_bugs if b.owasp_category != "None" or (b.cvss_score or 0) >= 7.0]
        aging = [b for b in open_bugs if (utcnow() - b.created_at).days > 30]

        if crits:
            actions.append(f"**Resolve {len(crits)} Critical Bug(s)**: {', '.join(b.title for b in crits[:3])}. Critical defects block release readiness.")
        if sec_bugs:
            actions.append(f"**Remediate {len(sec_bugs)} Security Defect(s)**: {', '.join(b.title for b in sec_bugs[:3])} with CVSS or OWASP classifications.")
        if highs:
            actions.append(f"**Triage {len(highs)} High Severity Bug(s)** to prevent quality degradation.")
        if aging:
            actions.append(f"**Address {len(aging)} Aging Bug(s)** open for more than 30 days.")

        risky_files = [f for f in s["files"] if f.get("mi", 100) < 40 or f.get("avg_cc", 0) > 15]
        if risky_files:
            actions.append(f"**Refactor {len(risky_files)} High-Risk Code File(s)** with low Maintainability Index (MI < 40): {', '.join(f['path'] for f in risky_files[:3])}.")

        if not actions:
            actions.append("Maintain current test coverage and defect tracking; all monitored quality indicators are healthy.")

        return f"**Prioritized Recommendations for {project.name}:**\n\n" + "\n\n".join(f"{i+1}. {act}" for i, act in enumerate(actions))

    # 4. Defect density / bug backlog
    if any(w in q for w in ("defect", "bug", "density", "backlog")):
        return (f"**Defect Analysis for {project.name}:**\n\n"
                f"- **Total Defects**: {len(s['bugs'])} logged ({oc['open']} open, {oc['closed']} closed)\n"
                f"- **Defect Density**: {s['defect_density']} defects per KLOC (Target: < 5.0)\n"
                f"- **Open / Closed Ratio**: {oc['ratio_text']} ({oc['percent_open']}% open)\n"
                f"- **Escape Rate**: {s['escape_rate']}% ({s['escaped_count']} bugs found in Production)\n"
                f"- **Average Open Bug Age**: {s['avg_open_age_days']} days ({s['old_bug_count']} older than 30 days)")

    # 5. Maintainability / Code Quality / Complexity
    if any(w in q for w in ("quality", "maintainability", "complex", "code")):
        return (f"**Software Quality & Code Metrics for {project.name}:**\n\n"
                f"- **Overall Quality Score**: {s['quality']['quality_score']}% ({s['quality']['quality_level']})\n"
                f"- **Maintainability Index**: {s['maintainability']['mi_score']}% ({s['maintainability']['band']})\n"
                f"- **Average Cyclomatic Complexity**: {a['avg_complexity']} (Max: {a['max_complexity']})\n"
                f"- **Total Code Size**: {a['size']['total_loc']} LOC across {a['size']['num_files']} files ({a['size']['num_functions']} functions)\n"
                f"- **Security Findings (Code)**: {a['security_counts']['High']} High, {a['security_counts']['Medium']} Medium, {a['security_counts']['Low']} Low")

    # 6. Default executive overview
    return (f"**Project Summary for {project.name}:**\n\n"
            f"- **Quality Score**: {s['quality']['quality_score']}% ({s['quality']['quality_level']})\n"
            f"- **Predicted Defect Risk**: {s['risk']['predicted_risk']}\n"
            f"- **Bugs**: {len(s['bugs'])} total ({oc['open']} open, {oc['closed']} closed, density {s['defect_density']}/KLOC)\n"
            f"- **Latest Release**: {s['latest_release']['name'] if s['latest_release'] else 'None'} "
            f"({s['latest_release']['readiness']['color'] if s['latest_release'] else 'No release'})\n\n"
            "You can ask me specific questions such as:\n"
            "- *Which module has more risk?*\n"
            "- *Is the latest release ready to ship?*\n"
            "- *What should we fix first?*\n"
            "- *What is our defect density and code quality?*")


@bp.route("/project/<int:project_id>/ai")
def chat_page(project_id):
    project = _project(project_id)
    history = (ChatMessage.query.filter_by(project_id=project_id, user_id=g.user.id)
               .order_by(ChatMessage.id).limit(200).all())
    prov = get_provider()
    return render_template("ai_chat.html", project=project, history=history, configured=prov.configured,
                           model=prov.model, setup=SETUP_STEPS, active="ai")


@bp.route("/project/<int:project_id>/ai/chat", methods=["POST"])
def chat_send(project_id):
    project = _project(project_id)
    data = request.get_json(silent=True) or {}
    question = str(data.get("message", "")).strip()
    if not question:
        return jsonify({"ok": False, "kind": "empty", "message": "Type a question first."}), 400
    if len(question) > MAX_QUESTION:
        return jsonify({"ok": False, "kind": "long", "message": f"Please keep the question under {MAX_QUESTION} characters."}), 400
    
    prior = (ChatMessage.query.filter_by(project_id=project_id, user_id=g.user.id)
             .order_by(ChatMessage.id.desc()).limit(HISTORY_LIMIT).all())[::-1]
    messages = [{"role": m.role, "content": m.content} for m in prior] + [{"role": "user", "content": question}]
    
    prov = get_provider()
    try:
        answer = prov.generate(build_project_context(project), messages)
    except AIError as e:
        return jsonify(_friendly(e)), 200

    db.session.add(ChatMessage(project_id=project_id, user_id=g.user.id, role="user", content=question))
    db.session.add(ChatMessage(project_id=project_id, user_id=g.user.id, role="model", content=answer))
    db.session.commit()
    return jsonify({"ok": True, "answer": answer})


@bp.route("/project/<int:project_id>/ai/local-answer", methods=["POST"])
def chat_local_answer(project_id):
    """Direct query to the built-in project metrics intelligence engine."""
    project = _project(project_id)
    data = request.get_json(silent=True) or {}
    question = str(data.get("message", "")).strip()
    if not question:
        return jsonify({"ok": False, "message": "Type a question first."}), 400
    answer = answer_project_question(project, question)
    db.session.add(ChatMessage(project_id=project_id, user_id=g.user.id, role="user", content=question))
    db.session.add(ChatMessage(project_id=project_id, user_id=g.user.id, role="model", content=answer))
    db.session.commit()
    return jsonify({"ok": True, "answer": answer})


@bp.route("/project/<int:project_id>/ai/save-key", methods=["POST"])
def save_ai_key(project_id):
    """Save Google Gemini API key and model to .env file and environment."""
    data = request.get_json(silent=True) or {}
    api_key = str(data.get("api_key", "")).strip()
    model = str(data.get("model", "")).strip() or GEMINI_DEFAULT_MODEL
    if not api_key:
        return jsonify({"ok": False, "message": "API key cannot be empty."}), 400

    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    found_key, found_model = False, False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("GEMINI_API_KEY="):
                    lines.append(f"GEMINI_API_KEY={api_key}\n")
                    found_key = True
                elif stripped.startswith("GEMINI_MODEL="):
                    lines.append(f"GEMINI_MODEL={model}\n")
                    found_model = True
                else:
                    lines.append(line)
    if not found_key:
        lines.append(f"GEMINI_API_KEY={api_key}\n")
    if not found_model:
        lines.append(f"GEMINI_MODEL={model}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["GEMINI_MODEL"] = model
    return jsonify({"ok": True, "message": "Gemini API key saved successfully."})


@bp.route("/project/<int:project_id>/ai/clear", methods=["POST"])
def chat_clear(project_id):
    _project(project_id)
    ChatMessage.query.filter_by(project_id=project_id, user_id=g.user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------------ Ask AI on a bug (17)
ASK_BUG_PROMPT = (
    "You are a senior software engineer helping to triage a bug. Reply with exactly these four short sections, each starting "
    "with its heading in bold: **Likely root cause**, **Suggested fix**, **How to test the fix**, **How to prevent it**. "
    "Be specific and concise (2-4 sentences or bullets each). If information is missing, say what you assume.")


def _bug(project_id, bug_id):
    b = db.get_or_404(Bug, bug_id)
    if b.project_id != project_id:
        abort(404)
    return b


@bp.route("/project/<int:project_id>/bugs/<int:bug_id>/ask-ai", methods=["POST"])
def ask_ai_bug(project_id, bug_id):
    b = _bug(project_id, bug_id)
    where = ""
    if b.code_file:
        where = f"\nFile: {b.code_file.relpath or b.code_file.filename}"
    text = (f"Bug title: {b.title}\nDescription: {b.description or '(none)'}\nModule: {b.module}\n"
            f"Severity: {b.severity}\nOWASP category: {b.owasp_category}\nCVSS: {b.cvss_score if b.cvss_score is not None else 'n/a'}"
            f"{where}\nStatus: {b.status}")
    try:
        answer = get_provider().generate(ASK_BUG_PROMPT, [{"role": "user", "content": text}], max_tokens=900)
    except AIError as e:
        return jsonify(_friendly(e))
    return jsonify({"ok": True, "answer": answer})


@bp.route("/project/<int:project_id>/bugs/<int:bug_id>/comments", methods=["POST"])
def add_comment(project_id, bug_id):
    b = _bug(project_id, bug_id)
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "message": "Comment is empty."}), 400
    source = "ai" if data.get("source") == "ai" else "user"
    c = BugComment(bug_id=b.id, user_id=g.user.id, text=text[:8000], source=source)
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "id": c.id})


# ------------------------------------------------------------------ AI recommendations (18)
RECO_PROMPT = (
    "You are a software quality coach. Using the project data, give a PRIORITISED action list (most important first, at most 8 "
    "items). For each action write: the action, why it matters (quote the numbers), and the expected effect. Plain English, "
    "short. Start with the single most urgent action.")


@bp.route("/project/<int:project_id>/ai/recommend", methods=["POST"])
def recommend(project_id):
    project = _project(project_id)
    try:
        answer = get_provider().generate(build_project_context(project) + "\n\n" + RECO_PROMPT,
                                         [{"role": "user", "content": "Give me prioritised recommendations for this project now."}],
                                         max_tokens=1400)
    except AIError as e:
        d = _friendly(e)
        d["fallback_note"] = "AI unavailable - showing rule-based tips."
        return jsonify(d)
    return jsonify({"ok": True, "answer": answer})
