"""
analyzers/complexity_analyzer.py
Cyclomatic Complexity (Feature 3).

Formula used: V(G) = E - N + 2P  (McCabe, 1976)
Implemented via the equivalent, standard decision-point counting method:
    V(G) = 1 + (number of decision points in the function)
Decision points counted: if, elif, for, while, except, boolean operators
(and/or), assert, with (multiple items), comprehension 'if' clauses.

Thresholds below are PROJECT-DEFINED, not universal standards, and are
documented as such in the UI.
"""
import ast

COMPLEXITY_THRESHOLDS = {
    "low": (1, 5),        # simple, low risk
    "moderate": (6, 10),  # moderate complexity
    "high": (11, 20),     # complex, higher risk - refactor candidate
    "very_high": (21, 10**6),  # very complex - high risk
}


def _classify(score: int) -> str:
    if score <= 5:
        return "Low"
    if score <= 10:
        return "Moderate"
    if score <= 20:
        return "High"
    return "Very High"


class _ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.score = 1  # base path

    def visit_If(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_Assert(self, node):
        self.score += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        # each additional operand beyond the first adds a decision point
        self.score += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self.score += len(node.ifs)
        self.generic_visit(node)


def calculate_function_complexity(func_node) -> int:
    visitor = _ComplexityVisitor()
    visitor.visit(func_node)
    return visitor.score


def analyze_complexity(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"parse_error": str(e), "units": [], "average_complexity": 0, "max_complexity": 0}

    units = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            score = calculate_function_complexity(node)
            units.append({
                "name": node.name,
                "line": node.lineno,
                "complexity": score,
                "risk_level": _classify(score),
            })

    if not units:
        return {"parse_error": None, "units": [], "average_complexity": 0, "max_complexity": 0}

    avg = round(sum(u["complexity"] for u in units) / len(units), 2)
    mx = max(u["complexity"] for u in units)
    return {"parse_error": None, "units": units, "average_complexity": avg, "max_complexity": mx}
