"""
analyzers/structure_analyzer.py
Structural Metrics (Feature 10): branches, loops, nesting depth, imports.
"""
import ast


class _NestingVisitor(ast.NodeVisitor):
    NESTING_NODES = (ast.If, ast.For, ast.While, ast.Try, ast.With,
                      ast.AsyncFor, ast.AsyncWith)

    def __init__(self):
        self.current_depth = 0
        self.max_depth = 0
        self.branches = 0
        self.loops = 0

    def generic_visit(self, node):
        is_nesting = isinstance(node, self.NESTING_NODES)
        if isinstance(node, ast.If):
            self.branches += 1
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
            self.loops += 1

        if is_nesting:
            self.current_depth += 1
            self.max_depth = max(self.max_depth, self.current_depth)

        super().generic_visit(node)

        if is_nesting:
            self.current_depth -= 1


def analyze_structure(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"parse_error": str(e)}

    visitor = _NestingVisitor()
    visitor.visit(tree)

    imports = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)))
    functions = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))

    return {
        "parse_error": None,
        "branches": visitor.branches,
        "loops": visitor.loops,
        "max_nesting_depth": visitor.max_depth,
        "imports": imports,
        "functions": functions,
        "classes": classes,
    }
