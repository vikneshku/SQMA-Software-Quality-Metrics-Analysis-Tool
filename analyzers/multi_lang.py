"""
analyzers/multi_lang.py
BASIC metrics for Java, JavaScript, C and C++ (requirement 34).

Steps
  1. A small tokenizer strips comments and string literals (keeping line numbers).
  2. Per file: total / blank / comment / code lines, functions, classes, imports,
     cyclomatic complexity per function (1 + if, else if, for, while, case, catch, &&, ||, ?),
     max nesting depth (brace depth), average and max complexity.
  3. Regex rules produce issues (security + complexity + maintainability + style).

Documented limitation: this is regex/brace based, not a real parser. JavaScript regex literals,
macros and unusual formatting can confuse it; Python keeps its full AST analysis.
Result shape matches analyzers/file_analyzer.analyze_file() so every page works unchanged.
"""
import re

from config import ISSUE_LIMITS

KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "else", "do", "try", "finally", "new",
            "throw", "sizeof", "synchronized", "function", "typeof", "delete", "case", "default"}


# ------------------------------------------------------------------ 1. tokenizer
def strip_code(source, lang):
    """Return (stripped_text, comment_line_numbers). Comments and string contents become spaces."""
    out, comment_lines = [], set()
    i, n, line = 0, len(source), 1
    java_blocks = lang == "Java"
    while i < n:
        ch, nxt = source[i], source[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                comment_lines.add(line); out.append(" "); i += 1
        elif ch == "/" and nxt == "*":
            out.append("  "); i += 2; comment_lines.add(line)
            while i < n and not (source[i] == "*" and i + 1 < n and source[i + 1] == "/"):
                if source[i] == "\n":
                    out.append("\n"); line += 1
                else:
                    out.append(" ")
                comment_lines.add(line); i += 1
            out.append("  "); i += 2
        elif java_blocks and source.startswith('"""', i):
            out.append('"""'); i += 3
            while i < n and not source.startswith('"""', i):
                if source[i] == "\n":
                    out.append("\n"); line += 1
                else:
                    out.append(" ")
                i += 1
            out.append('"""'); i += 3
        elif ch in "\"'" or (ch == "`" and lang == "JavaScript"):
            quote = ch
            out.append(quote); i += 1
            while i < n and source[i] != quote:
                if source[i] == "\\" and i + 1 < n:
                    out.append("  "); i += 2; continue
                if source[i] == "\n":
                    if quote != "`":
                        break                     # unterminated normal string: stop at end of line
                    out.append("\n"); line += 1
                else:
                    out.append(" ")
                i += 1
            if i < n and source[i] == quote:
                out.append(quote); i += 1
        else:
            if ch == "\n":
                line += 1
            out.append(ch); i += 1
    return "".join(out), comment_lines


# ------------------------------------------------------------------ 2. structure
_JAVA_METHOD = re.compile(r"\b([A-Za-z_][\w<>\[\],.?]*)\s+([A-Za-z_]\w*)\s*\(([^()]*)\)\s*(?:throws\s+[\w.,\s]+)?\{")
_JAVA_CTOR = re.compile(r"\b(?:public|private|protected)\s+([A-Z]\w*)\s*\(([^()]*)\)\s*(?:throws\s+[\w.,\s]+)?\{")
_JS_PATTERNS = [
    re.compile(r"\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(([^()]*)\)\s*\{"),
    re.compile(r"([A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s*)?function\s*\*?\s*\(([^()]*)\)\s*\{"),
    re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^()]*)\)\s*=>\s*\{"),
    re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?([A-Za-z_$][\w$]*)\s*=>\s*\{"),
    re.compile(r"^[ \t]*(?:static\s+)?(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(([^()]*)\)\s*\{", re.M),
]
_C_FUNC = re.compile(r"(?:^|[;}\n])[ \t]*(?:[\w:<>*&~,]+[ \t*&]+)+?([A-Za-z_~][\w:]*)\s*\(([^;{}()]*)\)\s*(?:const\s*)?(?:noexcept\s*)?(?:override\s*)?\{", re.M)

_CLASS = {"Java": r"\b(?:class|interface|enum)\s+\w+", "JavaScript": r"\bclass\s+\w+",
          "C++": r"\b(?:class|struct)\s+\w+\s*(?::[^{;]+)?\{", "C": r"(?!x)x"}
_IMPORT = {"Java": r"^\s*import\s", "JavaScript": r"^\s*import\s|\brequire\s*\(", "C": r"^\s*#\s*include",
           "C++": r"^\s*#\s*include"}
_DECISION = re.compile(r"\bif\b|\bfor\b|\bwhile\b|\bcase\b|\bcatch\b|&&|\|\||\?(?![.?])(?<!\?\?)")


def _match_brace(code, open_pos):
    depth = 0
    for j in range(open_pos, len(code)):
        c = code[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(code) - 1


def _classify(score):
    if score <= 5:
        return "Low"
    if score <= 10:
        return "Moderate"
    if score <= 20:
        return "High"
    return "Very High"


def _find_functions(code, lang):
    found = {}
    regs = []
    if lang == "Java":
        regs = [(_JAVA_METHOD, 2, 3, 1), (_JAVA_CTOR, 1, 2, None)]
    elif lang == "JavaScript":
        regs = [(p, 1, 2, None) for p in _JS_PATTERNS]
    else:
        regs = [(_C_FUNC, 1, 2, None)]
    for rx, gname, gparams, gtype in regs:
        for m in rx.finditer(code):
            name = m.group(gname).split("::")[-1]
            if name in KEYWORDS:
                continue
            if gtype and m.group(gtype) in KEYWORDS:
                continue
            open_pos = m.end() - 1
            start_line = code.count("\n", 0, m.start(gname)) + 1
            key = open_pos
            if key in found:
                continue
            params = m.group(gparams).strip()
            n_params = 0 if not params or params == "void" else params.count(",") + 1
            found[key] = (name, start_line, open_pos, n_params)
    return sorted(found.values(), key=lambda t: t[2])


def analyze_multi(source, lang, path_label=""):
    """Return the common analysis dict (see file_analyzer.analyze_file)."""
    code, comment_set = strip_code(source, lang)
    raw_lines = source.splitlines()
    code_lines = code.splitlines()
    total = len(raw_lines)
    blank = sum(1 for l in raw_lines if not l.strip())
    comment = sum(1 for i, l in enumerate(raw_lines, 1) if l.strip() and i in comment_set
                  and not code_lines[i - 1].strip()) if code_lines else 0
    logical = max(0, total - blank - comment)

    functions = []
    for name, start_line, open_pos, n_params in _find_functions(code, lang):
        close = _match_brace(code, open_pos)
        end_line = code.count("\n", 0, close) + 1
        body = code[open_pos:close + 1]
        cc = 1 + len(_DECISION.findall(body))
        depth = maxd = 0
        for c in body:
            if c == "{":
                depth += 1; maxd = max(maxd, depth)
            elif c == "}":
                depth -= 1
        functions.append({"name": name, "line": start_line, "start_line": start_line,
                          "size_lines": max(1, end_line - start_line + 1), "complexity": cc,
                          "risk_level": _classify(cc), "params": n_params, "nesting": max(0, maxd - 1)})

    classes = len(re.findall(_CLASS[lang], code))
    imports = len(re.findall(_IMPORT[lang], code, re.M))
    branches = len(re.findall(r"\bif\b|\bcase\b", code))
    loops = len(re.findall(r"\bfor\b|\bwhile\b", code))
    max_nest = max((f["nesting"] for f in functions), default=0)

    issues = _issues(source, code, raw_lines, code_lines, comment_set, functions, lang)
    return {
        "total_lines": total, "blank_lines": blank, "comment_lines": comment, "logical_lines": logical,
        "functions": functions, "num_classes": classes, "num_imports": imports,
        "branches": branches, "loops": loops, "max_nesting": max_nest, "issues": issues, "parse_error": None,
    }


# ------------------------------------------------------------------ 3. issues
def _iss(line, typ, sev, desc, fix, cat):
    return {"line_number": line, "issue_type": typ, "severity": sev, "description": desc,
            "fix_suggestion": fix, "category": cat}


_SECRET = re.compile(r"(password|passwd|secret|api_?key|token)\s*[:=]\s*[\"'][^\"']{3,}[\"']", re.I)
_SQL_CONCAT = re.compile(r"[\"']\s*(SELECT|INSERT|UPDATE|DELETE)\b[^\"']*[\"']\s*\+", re.I)
_LANG_RULES = {
    "JavaScript": [
        (re.compile(r"\beval\s*\("), "Use of eval()", "High", "eval() runs arbitrary strings as code (code injection).",
         "Avoid eval; parse data with JSON.parse or use a safe lookup."),
        (re.compile(r"\.innerHTML\s*="), "Use of innerHTML", "Medium", "Assigning to innerHTML can allow cross-site scripting (XSS).",
         "Use textContent or sanitise the HTML first."),
        (re.compile(r"document\.write\s*\("), "Use of document.write", "Medium", "document.write can inject unsafe markup (XSS).",
         "Create elements with the DOM API instead."),
    ],
    "C": [
        (re.compile(r"\bgets\s*\("), "Use of gets()", "High", "gets() cannot limit input length: guaranteed buffer overflow risk.", "Use fgets(buf, size, stdin)."),
        (re.compile(r"\bstrcpy\s*\("), "Use of strcpy()", "Medium", "strcpy does not check the destination size (buffer overflow).", "Use strncpy or snprintf with a size."),
        (re.compile(r"\bsprintf\s*\("), "Use of sprintf()", "Medium", "sprintf can overflow the output buffer.", "Use snprintf with the buffer size."),
        (re.compile(r"\bsystem\s*\("), "Use of system()", "Medium", "system() can allow command injection.", "Avoid the shell; call the program directly with validated arguments."),
    ],
    "Java": [
        (re.compile(r"Runtime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\("), "Use of Runtime.exec", "High",
         "Runtime.exec can allow command injection when input is not validated.", "Use ProcessBuilder with a fixed argument list and validate input."),
    ],
}
_LANG_RULES["C++"] = _LANG_RULES["C"]


def _issues(source, code, raw_lines, code_lines, comment_set, functions, lang):
    L = ISSUE_LIMITS
    out = []
    # --- security rules on stripped code (no false hits inside comments/strings)
    for rx, typ, sev, desc, fix in _LANG_RULES.get(lang, []):
        for m in rx.finditer(code):
            out.append(_iss(code.count("\n", 0, m.start()) + 1, typ, sev, desc, fix, "Security"))
    # --- hard-coded secrets / SQL concatenation on original lines (strings are needed here)
    for i, line in enumerate(raw_lines, 1):
        if i in comment_set and not (code_lines[i - 1].strip() if i - 1 < len(code_lines) else ""):
            continue
        if _SECRET.search(line):
            out.append(_iss(i, "Hardcoded password/secret", "Medium", "Credentials embedded in source code.",
                            "Move secrets to environment variables or a secrets manager.", "Security"))
        if _SQL_CONCAT.search(line):
            out.append(_iss(i, "SQL string concatenation", "High", "SQL built by string concatenation risks SQL injection.",
                            "Use parameterised queries / prepared statements.", "Security"))
    # --- empty catch
    if lang in ("Java", "JavaScript", "C++"):
        for m in re.finditer(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", code):
            out.append(_iss(code.count("\n", 0, m.start()) + 1, "Empty catch block", "Medium",
                            "Errors are silently swallowed.", "Log or handle the exception.", "Maintainability"))
    # --- function rules
    for f in functions:
        where = f"Function {f['name']}"
        if f["complexity"] > L["complex"]:
            out.append(_iss(f["line"], "Function too complex", "High" if f["complexity"] > L["very_complex"] else "Medium",
                            f"{where} has cyclomatic complexity {f['complexity']} (limit {L['complex']}).",
                            "Split it into smaller functions and simplify conditions.", "Complexity"))
        if f["size_lines"] > L["long_function"]:
            out.append(_iss(f["line"], "Function too long", "Medium" if f["size_lines"] > L["very_long_function"] else "Low",
                            f"{where} is {f['size_lines']} lines long (limit {L['long_function']}).",
                            "Extract parts of it into helper functions.", "Maintainability"))
        if f["params"] > L["max_params"]:
            out.append(_iss(f["line"], "Too many parameters", "Low", f"{where} takes {f['params']} parameters (limit {L['max_params']}).",
                            "Group related parameters into an object/struct.", "Maintainability"))
        if f["nesting"] > L["max_nesting"]:
            out.append(_iss(f["line"], "Deep nesting", "Medium", f"{where} nests blocks {f['nesting']} levels deep (limit {L['max_nesting']}).",
                            "Use early returns or extract inner blocks.", "Complexity"))
        prev = f["line"] - 2
        while prev >= 0 and not raw_lines[prev].strip():
            prev -= 1
        if prev < 0 or (prev + 1) not in comment_set:
            out.append(_iss(f["line"], "Missing comment", "Low", f"{where} has no comment above it.",
                            "Add a short comment/doc-comment describing what it does.", "Style"))
    return out
