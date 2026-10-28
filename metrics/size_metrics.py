"""
metrics/size_metrics.py
Internal Product Measures / Software Size (Feature 9), aggregated across
all uploaded files of a project.
"""


def aggregate_size(file_analyses: list) -> dict:
    """file_analyses: list of dicts returned by code_analyzer.analyze_source,
    one per uploaded file."""
    total_loc = sum(f.get("total_lines", 0) for f in file_analyses)
    total_logical = sum(f.get("logical_lines", 0) for f in file_analyses)
    total_comments = sum(f.get("comment_lines", 0) for f in file_analyses)
    total_blank = sum(f.get("blank_lines", 0) for f in file_analyses)
    total_functions = sum(f.get("num_functions", 0) for f in file_analyses)
    total_classes = sum(f.get("num_classes", 0) for f in file_analyses)
    total_imports = sum(f.get("num_imports", 0) for f in file_analyses)

    all_func_sizes = []
    for f in file_analyses:
        for fn in f.get("functions", []):
            all_func_sizes.append(fn["size_lines"])

    avg_function_size = round(sum(all_func_sizes) / len(all_func_sizes), 2) if all_func_sizes else 0
    comment_ratio = round((total_comments / total_loc) * 100, 2) if total_loc else 0

    return {
        "num_files": len(file_analyses),
        "total_loc": total_loc,
        "logical_lines": total_logical,
        "comment_lines": total_comments,
        "blank_lines": total_blank,
        "comment_ratio_percent": comment_ratio,
        "num_functions": total_functions,
        "num_classes": total_classes,
        "num_imports": total_imports,
        "avg_function_size": avg_function_size,
    }
