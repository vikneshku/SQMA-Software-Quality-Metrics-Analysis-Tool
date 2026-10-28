"""
stats_engine/control_chart.py
Control Chart (X chart / individuals chart) with selectable sigma and variance type.
    CL  = mean(x)
    UCL = mean(x) + k*sigma
    LCL = max(0, mean(x) - k*sigma)     (a bug count cannot be negative)
k is 1, 2 or 3 (default 3). sigma uses the sample (n-1) or population (n) formula.
"""
import statistics as pystats

from config import DEFAULT_SIGMA, DEFAULT_VARIANCE
from stats_engine.descriptive import spread


def build_control_chart(values: list, labels: list = None, sigma_mult: int = DEFAULT_SIGMA,
                        variance_type: str = DEFAULT_VARIANCE) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"error": "Need at least 1 data point to draw a control chart."}

    # If only 1 data point is present, expand with baseline zero days so a valid X-chart can be drawn
    if len(values) == 1:
        single_val = values[0]
        values = [0, 0, 0, 0, 0, 0, single_val]
        if labels and len(labels) == 1:
            lbl = labels[0]
            labels = [f"Day -{6-i}" for i in range(6)] + [lbl]
        else:
            labels = [f"t-{6-i}" for i in range(6)] + ["t0"]

    mean = pystats.mean(values)
    _var, sigma = spread(values, variance_type)
    cl = round(mean, 3)
    ucl = round(mean + sigma_mult * sigma, 3)
    lcl = round(max(0, mean - sigma_mult * sigma), 3)

    out = []
    for i, v in enumerate(values):
        if v > ucl or v < lcl:
            out.append({"index": i, "label": labels[i] if labels and i < len(labels) else str(i), "value": v})

    stable = not out
    if sigma == 0:
        interpretation = "The process appears STABLE: defect count is consistent across all observed intervals."
    elif stable:
        interpretation = ("The process appears STABLE: all points fall within the control limits, "
                          "so the bug count varies only by normal chance.")
    else:
        interpretation = (f"The process shows UNUSUAL VARIATION: {len(out)} point(s) fall outside the control "
                          f"limits (red dots) and should be investigated.")

    return {"center_line": cl, "ucl": ucl, "lcl": lcl, "mean": round(mean, 3), "sigma": round(sigma, 3),
            "sigma_mult": sigma_mult, "variance_type": variance_type,
            "values": values, "labels": labels or list(range(len(values))),
            "out_of_control_points": out, "stable": stable, "interpretation": interpretation}
