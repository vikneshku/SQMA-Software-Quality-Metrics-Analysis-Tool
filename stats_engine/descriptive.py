"""
stats_engine/descriptive.py
Descriptive statistics with a selectable variance type (requirement 24).

    sample      variance = sum((x - mean)^2) / (n - 1)   (data is a SAMPLE of a bigger process)
    population  variance = sum((x - mean)^2) / n          (you have EVERY value)
"""
import math
import statistics as pystats

from config import DEFAULT_VARIANCE


def spread(values, variance_type=DEFAULT_VARIANCE):
    """Return (variance, std_dev) using the chosen divisor."""
    n = len(values)
    if n < 2:
        return 0.0, 0.0
    if variance_type == "population":
        var = pystats.pvariance(values)
    else:
        var = pystats.variance(values)
    return var, math.sqrt(var)


def describe(values: list, variance_type: str = DEFAULT_VARIANCE) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"count": 0, "mean": 0, "median": 0, "std_dev": 0, "min": 0, "max": 0, "variance": 0,
                "variance_type": variance_type, "coefficient_of_variation_percent": 0,
                "interpretation": "No data available."}

    n = len(values)
    mean = round(pystats.mean(values), 3)
    median = round(pystats.median(values), 3)
    var, sd = spread(values, variance_type)
    variance, std_dev = round(var, 3), round(sd, 3)
    vmin, vmax = min(values), max(values)

    cv = round((std_dev / mean) * 100, 2) if mean else 0
    if cv == 0:
        spread_note = "no variation"
    elif cv < 15:
        spread_note = "low variation (consistent data)"
    elif cv < 35:
        spread_note = "moderate variation"
    else:
        spread_note = "high variation (inconsistent / unstable data)"

    interpretation = (f"The dataset has {n} points with a mean of {mean} and a {variance_type} standard "
                      f"deviation of {std_dev}, indicating {spread_note}.")
    return {"count": n, "mean": mean, "median": median, "std_dev": std_dev, "variance": variance,
            "variance_type": variance_type, "min": vmin, "max": vmax,
            "coefficient_of_variation_percent": cv, "interpretation": interpretation}
