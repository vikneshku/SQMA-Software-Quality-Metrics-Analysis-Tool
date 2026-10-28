"""
stats_engine/boxplot.py
Box Plot (distribution / outlier visualization).
Computes the five-number summary + IQR outlier fences, and the whisker ends
that the diagram needs.

Rules:
    Q1, Median, Q3      25th / 50th / 75th percentile (linear interpolation)
    IQR                 = Q3 - Q1
    Lower fence         = Q1 - 1.5 * IQR
    Upper fence         = Q3 + 1.5 * IQR
    Outlier             = any value outside [lower fence, upper fence]
    Whisker ends        = smallest / largest value that is NOT an outlier
"""


def _percentile(sorted_vals, p):
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = (n - 1) * p
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def build_boxplot(values: list) -> dict:
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"error": "No data available."}

    q1 = round(_percentile(values, 0.25), 3)
    q2 = round(_percentile(values, 0.50), 3)
    q3 = round(_percentile(values, 0.75), 3)
    iqr = round(q3 - q1, 3)
    lower_fence = round(q1 - 1.5 * iqr, 3)
    upper_fence = round(q3 + 1.5 * iqr, 3)

    outliers = [v for v in values if v < lower_fence or v > upper_fence]
    inliers = [v for v in values if lower_fence <= v <= upper_fence] or values
    lower_whisker, upper_whisker = inliers[0], inliers[-1]

    interpretation = (
        f"Median is {q2}, with the middle 50% of values (IQR) between {q1} and {q3}. "
        + (f"{len(outliers)} outlier(s) detected beyond the normal range." if outliers
           else "No outliers detected.")
    )

    return {
        "min": values[0], "max": values[-1],
        "q1": q1, "median": q2, "q3": q3, "iqr": iqr,
        "lower_fence": lower_fence, "upper_fence": upper_fence,
        "lower_whisker": lower_whisker, "upper_whisker": upper_whisker,
        "outliers": outliers, "values": values, "n": len(values),
        "interpretation": interpretation,
    }
