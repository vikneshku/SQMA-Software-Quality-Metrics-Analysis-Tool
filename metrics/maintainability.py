"""
metrics/maintainability.py
Maintainability Index, calculated PER FILE and combined per project (requirement 19).

    avgFnLOC = average function size of the file (lines)
    HV       = avgFnLOC x log2(12)            (documented Halstead Volume approximation)
    CC       = average cyclomatic complexity of the file's functions
    MI_raw   = 171 - 5.2 ln(HV) - 0.23 CC - 16.2 ln(avgFnLOC)
    MI       = max(0, min(100, MI_raw x 100 / 171))

    Project MI = LOC-weighted average of the file MIs.

Bands (project-defined, calibrated on sample values):
    55 - 100  Highly maintainable
    40 - 54.9 Moderately maintainable
    below 40  Difficult to maintain
Sample check: avg function 20 lines & CC 4 -> 58;  50 lines & CC 25 -> 44;  100 lines & CC 30 -> 34.
"""
import math

from config import MI_BANDS

VOCAB_FACTOR = math.log2(12)


def mi_band(score: float) -> str:
    if score >= MI_BANDS["high"]:
        return "Highly maintainable"
    if score >= MI_BANDS["moderate"]:
        return "Moderately maintainable"
    return "Difficult to maintain"


def maintainability_index(avg_function_loc: float, avg_complexity: float) -> dict:
    """MI of one file (or one function)."""
    fn_loc = max(float(avg_function_loc or 0), 1.0)
    cc = max(float(avg_complexity or 0), 1.0)
    hv = fn_loc * VOCAB_FACTOR
    raw = 171 - 5.2 * math.log(hv) - 0.23 * cc - 16.2 * math.log(fn_loc)
    score = round(max(0.0, min(100.0, raw * 100 / 171)), 2)
    return {"mi_score": score, "band": mi_band(score), "halstead_volume": round(hv, 2),
            "raw": round(raw, 2), "avg_function_loc": round(fn_loc, 2), "cc": round(cc, 2)}


def project_maintainability(file_rows) -> dict:
    """file_rows: list of dicts with keys loc and mi_score. LOC-weighted average."""
    total = sum(r["loc"] for r in file_rows)
    if not file_rows or total <= 0:
        return {"mi_score": 100.0, "band": "Highly maintainable", "halstead_volume": 0,
                "weighted": [], "total_loc": 0}
    score = sum(r["mi_score"] * r["loc"] for r in file_rows) / total
    score = round(score, 2)
    return {"mi_score": score, "band": mi_band(score),
            "halstead_volume": round(sum(r.get("halstead_volume", 0) for r in file_rows), 2),
            "weighted": file_rows, "total_loc": total}
