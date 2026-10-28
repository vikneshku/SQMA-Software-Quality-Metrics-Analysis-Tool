"""
analyzers/code_analyzer.py
Source Code Measurement (Feature 2) + Internal Product Measures (Feature 9).
Parses uploaded Python source files with the built-in `ast` module and
returns size/structure information. Documented scope: analyzes Python
(.py) source files. This is a project-defined analyzer, not a universal
multi-language parser.
"""
import ast


def analyze_source(file_path: str) -> dict:
    """Return size + structural facts for one Python source file."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()

    lines = source.splitlines()
    total_lines = len(lines)
    blank_lines = sum(1 for l in lines if l.strip() == "")
    comment_lines = sum(1 for l in lines if l.strip().startswith("#"))
    logical_lines = total_lines - blank_lines - comment_lines

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {
            "parse_error": str(e),
            "total_lines": total_lines,
            "blank_lines": blank_lines,
            "comment_lines": comment_lines,
            "logical_lines": logical_lines,
            "functions": [],
            "classes": [],
            "num_functions": 0,
            "num_classes": 0,
            "num_imports": 0,
        }

    functions = []
    classes = []
    imports = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_lines = _node_line_span(node)
            functions.append({
                "name": node.name,
                "start_line": node.lineno,
                "size_lines": func_lines,
                "num_args": len(node.args.args),
            })
        elif isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "start_line": node.lineno,
                "num_methods": sum(
                    1 for b in node.body if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
                ),
            })
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports += 1

    avg_func_size = (
        round(sum(f["size_lines"] for f in functions) / len(functions), 2)
        if functions else 0
    )

    return {
        "parse_error": None,
        "total_lines": total_lines,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "logical_lines": logical_lines,
        "functions": functions,
        "classes": classes,
        "num_functions": len(functions),
        "num_classes": len(classes),
        "num_imports": imports,
        "avg_function_size": avg_func_size,
    }


def _node_line_span(node) -> int:
    """Approximate number of lines a function/class body spans."""
    max_line = node.lineno
    for child in ast.walk(node):
        if hasattr(child, "lineno"):
            max_line = max(max_line, child.lineno)
    return max_line - node.lineno + 1
