"""
analyzers/file_analyzer.py
analyze_file(code_file) - the ONE entry point for per-file analysis (requirement 36).
Every page works from this result; the project result is an aggregation of file results.

Result keys
    language, basic (True for Java/JS/C/C++), parse_error
    size_result     dict in the shape metrics.size_metrics.aggregate_size() expects
    functions       [{name, line, size_lines, complexity, risk_level, params, nesting}]
    structure       {branches, loops, imports, max_nesting_depth}
    security_findings  [{issue_type, severity, line_number, description}]
    issues          [{line_number, issue_type, severity, description, fix_suggestion, category}]
    avg_complexity, max_complexity, avg_function_loc, mi (maintainability dict)
"""
import ast
import os

from config import SUPPORTED_EXTS
from analyzers.code_analyzer import analyze_source
from analyzers.complexity_analyzer import analyze_complexity
from analyzers.structure_analyzer import analyze_structure
from analyzers.security_analyzer import analyze_security
from analyzers.python_issues import python_issues, function_nesting
from analyzers.multi_lang import analyze_multi
from metrics.maintainability import maintainability_index

_CACHE = {}


def language_for(path):
    ext = os.path.splitext(path)[1].lower()
    lang = SUPPORTED_EXTS.get(ext)
    if ext == ".h" and lang == "C":
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                head = fh.read(20000)
            if any(k in head for k in ("class ", "namespace ", "template<", "template <", "::")):
                return "C++"
        except OSError:
            pass
    return lang


def _read(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def _python(path):
    size = analyze_source(path)
    comp = analyze_complexity(path)
    struct = analyze_structure(path)
    sec = analyze_security(path)
    sizes = {(f["name"], f["start_line"]): f for f in size.get("functions", [])}
    functions = []
    for u in comp.get("units", []):
        sf = sizes.get((u["name"], u["line"]), {})
        functions.append({"name": u["name"], "line": u["line"], "start_line": u["line"], "complexity": u["complexity"],
                          "risk_level": u["risk_level"], "size_lines": sf.get("size_lines", 0),
                          "params": sf.get("num_args", 0), "nesting": 0})
    issues = []
    if not size.get("parse_error"):
        try:
            tree = ast.parse(_read(path))
            issues = python_issues(tree, {(f["name"], f["line"]): f for f in functions})
            nest = {(n.name, n.lineno): function_nesting(n) for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for f in functions:
                f["nesting"] = nest.get((f["name"], f["line"]), 0)
        except SyntaxError:
            pass
    for s in sec:
        issues.append({"line_number": s["line_number"], "issue_type": s["issue_type"], "severity": s["severity"],
                       "description": s["description"], "category": "Security",
                       "fix_suggestion": "Review this line and apply the secure alternative for the flagged pattern."})
    structure = ({"branches": 0, "loops": 0, "imports": size.get("num_imports", 0), "max_nesting_depth": 0}
                 if struct.get("parse_error") else
                 {k: struct.get(k, 0) for k in ("branches", "loops", "imports", "max_nesting_depth")})
    size["num_functions"] = len(functions)
    return size, functions, structure, issues, size.get("parse_error")


def _other(path, lang):
    r = analyze_multi(_read(path), lang)
    size = {"parse_error": None, "total_lines": r["total_lines"], "blank_lines": r["blank_lines"],
            "comment_lines": r["comment_lines"], "logical_lines": r["logical_lines"], "functions": r["functions"],
            "classes": [], "num_functions": len(r["functions"]), "num_classes": r["num_classes"],
            "num_imports": r["num_imports"]}
    structure = {"branches": r["branches"], "loops": r["loops"], "imports": r["num_imports"],
                 "max_nesting_depth": r["max_nesting"]}
    return size, r["functions"], structure, r["issues"], None


def analyze_file(cf):
    """Analyse one CodeFile row. Returns None if the file is missing on disk."""
    path = cf.filepath
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_mtime_ns, st.st_size)
    if key in _CACHE:
        return _CACHE[key]
    lang = language_for(path) or "Python"
    try:
        size, functions, structure, issues, perr = _python(path) if lang == "Python" else _other(path, lang)
    except Exception as exc:                              # never let one odd file break a page
        size = {"parse_error": str(exc), "total_lines": 0, "blank_lines": 0, "comment_lines": 0, "logical_lines": 0,
                "functions": [], "classes": [], "num_functions": 0, "num_classes": 0, "num_imports": 0}
        functions, structure, issues, perr = [], {"branches": 0, "loops": 0, "imports": 0, "max_nesting_depth": 0}, [], str(exc)

    fn_sizes = [f["size_lines"] for f in functions if f["size_lines"]]
    avg_fn = sum(fn_sizes) / len(fn_sizes) if fn_sizes else max(size.get("logical_lines", 0), 1)
    cc_vals = [f["complexity"] for f in functions]
    avg_cc = round(sum(cc_vals) / len(cc_vals), 2) if cc_vals else 0
    size["avg_function_size"] = round(avg_fn if fn_sizes else 0, 2)
    for f in size.get("functions", []):                   # aggregate_size expects size_lines on each function
        f.setdefault("size_lines", 0)
    result = {
        "language": lang, "basic": lang != "Python", "parse_error": perr, "size_result": size,
        "functions": functions, "structure": structure, "issues": issues,
        "security_findings": [i for i in issues if i["category"] == "Security"],
        "avg_complexity": avg_cc, "max_complexity": max(cc_vals, default=0), "avg_function_loc": round(avg_fn, 2),
        "mi": maintainability_index(avg_fn, avg_cc or 1),
    }
    _CACHE[key] = result
    if len(_CACHE) > 3000:
        _CACHE.clear()
    return result
