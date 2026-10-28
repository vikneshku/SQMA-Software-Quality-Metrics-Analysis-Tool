"""
stats_engine/correlation.py
Correlation Analysis. Pearson correlation coefficient r, plus the least-squares
trend line used by the scatter diagram.

    r = sum((x-mx)*(y-my)) / sqrt( sum((x-mx)^2) * sum((y-my)^2) )
    slope b = sum((x-mx)*(y-my)) / sum((x-mx)^2)      intercept a = my - b*mx
"""
import math


def _strength_label(r: float) -> str:
    ar = abs(r)
    if ar >= 0.7:
        return "Strong"
    if ar >= 0.4:
        return "Moderate"
    if ar >= 0.2:
        return "Weak"
    return "Very weak / negligible"


def pearson_correlation(x: list, y: list) -> dict:
    if len(x) != len(y) or len(x) < 2:
        return {"r": 0, "strength": "Insufficient data", "kind": "zero", "n": len(x),
                "interpretation": "Need at least 2 paired data points.", "trend": None}

    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    sxy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    sxx = sum((xi - mean_x) ** 2 for xi in x)
    syy = sum((yi - mean_y) ** 2 for yi in y)

    if sxx == 0 or syy == 0:
        return {"r": 0, "strength": "No variation", "kind": "zero", "n": n, "trend": None,
                "interpretation": "One of the two metrics has zero variance (every value is identical), so a correlation cannot be computed."}

    r = round(sxy / math.sqrt(sxx * syy), 3)
    strength = _strength_label(r)
    kind = "zero" if abs(r) < 0.2 else ("positive" if r > 0 else "negative")
    direction = {"positive": "positive", "negative": "negative", "zero": "no meaningful"}[kind]
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    x0, x1 = min(x), max(x)
    trend = [{"x": x0, "y": round(slope * x0 + intercept, 3)}, {"x": x1, "y": round(slope * x1 + intercept, 3)}]

    meaning = {
        "positive": "Larger functions also tend to be more complex: as one metric rises, the other rises too.",
        "negative": "As one metric rises the other tends to fall.",
        "zero": "The two metrics do not move together in any consistent way.",
    }[kind]
    interpretation = (f"Pearson r = {r}, indicating a {strength.lower()} {direction} correlation "
                      f"between the two metrics. {meaning}")
    return {"r": r, "strength": strength, "kind": kind, "n": n, "interpretation": interpretation,
            "trend": trend, "slope": round(slope, 4), "intercept": round(intercept, 4),
            "r_squared": round(r * r, 3)}
