"""
analyzers/python_issues.py
Rule-based code issues for Python, found with the ast module (requirement 30):
function too complex / too long, too many parameters, deep nesting, missing docstring,
bare except, unused import.
"""
import ast

from config import ISSUE_LIMITS


def _iss(line, typ, sev, desc, fix, cat):
    return {"line_number": line, "issue_type": typ, "severity": sev, "description": desc,
            "fix_suggestion": fix, "category": cat}


class _Depth(ast.NodeVisitor):
    NEST = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith)

    def __init__(self):
        self.cur = self.max = 0

    def generic_visit(self, node):
        nest = isinstance(node, self.NEST)
        if nest:
            self.cur += 1
            self.max = max(self.max, self.cur)
        super().generic_visit(node)
        if nest:
            self.cur -= 1


def function_nesting(node):
    d = _Depth()
    for child in node.body:
        d.visit(child)
    return d.max


def python_issues(tree, functions_by_key):
    """functions_by_key: {(name, line): {"complexity":.., "size_lines":..}} computed by the caller."""
    L = ISSUE_LIMITS
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info = functions_by_key.get((node.name, node.lineno), {})
            cc, size = info.get("complexity", 1), info.get("size_lines", 1)
            where = f"Function {node.name}"
            if cc > L["complex"]:
                out.append(_iss(node.lineno, "Function too complex", "High" if cc > L["very_complex"] else "Medium",
                                f"{where} has cyclomatic complexity {cc} (limit {L['complex']}).",
                                "Split it into smaller functions and simplify conditions.", "Complexity"))
            if size > L["long_function"]:
                out.append(_iss(node.lineno, "Function too long", "Medium" if size > L["very_long_function"] else "Low",
                                f"{where} is {size} lines long (limit {L['long_function']}).",
                                "Extract parts of it into helper functions.", "Maintainability"))
            a = node.args
            n_params = len(a.args) + len(a.kwonlyargs) + len(getattr(a, "posonlyargs", []))
            if n_params and a.args and a.args[0].arg in ("self", "cls"):
                n_params -= 1
            if n_params > L["max_params"]:
                out.append(_iss(node.lineno, "Too many parameters", "Low",
                                f"{where} takes {n_params} parameters (limit {L['max_params']}).",
                                "Group related parameters into an object or dataclass.", "Maintainability"))
            depth = function_nesting(node)
            if depth > L["max_nesting"]:
                out.append(_iss(node.lineno, "Deep nesting", "Medium",
                                f"{where} nests blocks {depth} levels deep (limit {L['max_nesting']}).",
                                "Use early returns / guard clauses or extract inner blocks.", "Complexity"))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_") and ast.get_docstring(node) is None:
                kind = "Class" if isinstance(node, ast.ClassDef) else "Function"
                out.append(_iss(node.lineno, "Missing docstring", "Low", f"{kind} {node.name} has no docstring.",
                                "Add a short docstring explaining what it does.", "Style"))
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            out.append(_iss(node.lineno, "Bare except", "Medium", "A bare 'except:' also catches KeyboardInterrupt and hides bugs.",
                            "Catch specific exceptions, e.g. 'except ValueError:'.", "Maintainability"))

    # unused imports
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for al in node.names:
                imported[(al.asname or al.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for al in node.names:
                if al.name != "*":
                    imported[al.asname or al.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    exported = set()
    for node in ast.walk(tree):                      # names listed in __all__ count as used
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            exported |= {e.value for e in ast.walk(node.value) if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    for name, line in imported.items():
        if name not in used and name not in exported and name != "annotations":
            out.append(_iss(line, "Unused import", "Low", f"'{name}' is imported but never used.",
                            "Remove the import.", "Style"))
    return out
