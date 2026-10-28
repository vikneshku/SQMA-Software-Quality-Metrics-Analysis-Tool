"""
analyzers/security_analyzer.py
Security Analysis (Feature 12).

IMPORTANT (documented honestly, as required by the project plan):
This is a LIGHTWEIGHT, RULE-BASED, EXPLAINABLE project scanner built for
this course project. It is NOT a replacement for professional SAST/DAST
tools (e.g. Semgrep, Bandit, SonarQube Security). Each finding maps to one
explicit, readable rule so results can be defended in a viva.
"""
import ast
import re

# Each rule: (issue_type, severity, description, matcher)
RULES = [
    ("Use of eval()", "High", "eval() executes arbitrary strings as code and can lead to code injection."),
    ("Use of exec()", "High", "exec() executes arbitrary code and can lead to code injection."),
    ("os.system call", "Medium", "os.system() can allow shell/command injection if input is not sanitized."),
    ("subprocess with shell=True", "High", "shell=True enables shell injection if inputs are not sanitized."),
    ("pickle.loads usage", "High", "Unpickling untrusted data can lead to arbitrary code execution."),
    ("Hardcoded password/secret", "Medium", "Credentials embedded in source code should be moved to environment variables."),
    ("SQL string concatenation", "High", "Building SQL via string concatenation/format risks SQL injection; use parameterized queries."),
    ("Use of assert for security check", "Low", "assert statements are stripped when Python runs with -O; do not rely on them for security logic."),
]

_HARDCODED_SECRET_RE = re.compile(
    r"(password|passwd|secret|api_key|apikey|token)\s*=\s*[\"'][^\"']{3,}[\"']",
    re.IGNORECASE,
)
_SQL_CONCAT_RE = re.compile(
    r"(SELECT|INSERT|UPDATE|DELETE)\b.{0,80}(\+|%s|\.format\(|f[\"'])",
    re.IGNORECASE,
)


def analyze_security(file_path: str) -> list:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()
    lines = source.splitlines()

    findings = []

    # AST-based checks (accurate line numbers, catches real calls)
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = _call_name(node)
                if func_name == "eval":
                    findings.append(_mk("Use of eval()", "High", node.lineno,
                                         "eval() executes arbitrary strings as code and can lead to code injection."))
                elif func_name == "exec":
                    findings.append(_mk("Use of exec()", "High", node.lineno,
                                         "exec() executes arbitrary code and can lead to code injection."))
                elif func_name in ("os.system", "system"):
                    findings.append(_mk("os.system call", "Medium", node.lineno,
                                         "os.system() can allow shell/command injection if input is not sanitized."))
                elif func_name in ("pickle.loads", "loads"):
                    findings.append(_mk("pickle.loads usage", "High", node.lineno,
                                         "Unpickling untrusted data can lead to arbitrary code execution."))
                elif func_name in ("subprocess.run", "subprocess.call", "subprocess.Popen"):
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            findings.append(_mk("subprocess with shell=True", "High", node.lineno,
                                                 "shell=True enables shell injection if inputs are not sanitized."))
    except SyntaxError:
        pass

    # Regex-based checks (line-level pattern matching, simple & explainable)
    for i, line in enumerate(lines, start=1):
        if _HARDCODED_SECRET_RE.search(line):
            findings.append(_mk("Hardcoded password/secret", "Medium", i,
                                 "Credentials embedded in source code should be moved to environment variables."))
        if _SQL_CONCAT_RE.search(line):
            findings.append(_mk("SQL string concatenation", "High", i,
                                 "Building SQL via string concatenation/format risks SQL injection; use parameterized queries."))

    return findings


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name):
            return f"{node.func.value.id}.{node.func.attr}"
        return node.func.attr
    return ""


def _mk(issue_type, severity, line, desc):
    return {"issue_type": issue_type, "severity": severity, "line_number": line, "description": desc}
