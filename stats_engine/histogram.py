"""
stats_engine/histogram.py
Histogram (Statistical Analysis section).

A histogram groups values into equal-width class intervals ("bins") and counts
how many values fall into each one.

Rules used (documented so they can be explained in a viva):
    k      = ceil(1 + log2(n))                 Sturges' rule: number of bins
    width  = ceil((max - min + 1) / k)         whole-number class width
    bin i  = [min + i*width , min + (i+1)*width - 1]
Every value is placed in exactly one bin, so the bar heights add up to n.
"""
import math


def build_histogram(values: list) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"error": "No data available.", "labels": [], "counts": []}

    n = len(values)
    vmin, vmax = int(math.floor(min(values))), int(math.floor(max(values)))
    k = max(1, math.ceil(1 + math.log2(n)))
    span = vmax - vmin + 1
    k = min(k, span)                      # never more bins than distinct whole numbers
    width = max(1, math.ceil(span / k))
    k = math.ceil(span / width)           # recompute so the last bin reaches the maximum

    counts = [0] * k
    for v in values:
        idx = min(int((int(math.floor(v)) - vmin) // width), k - 1)
        counts[idx] += 1

    labels = []
    for i in range(k):
        lo = vmin + i * width
        hi = lo + width - 1
        labels.append(str(lo) if width == 1 else f"{lo}-{hi}")

    tallest = max(range(k), key=lambda i: counts[i])
    interpretation = (
        f"{n} values were grouped into {k} class interval(s) of width {width}. "
        f"The most common range is {labels[tallest]} with {counts[tallest]} value(s) "
        f"({round(counts[tallest] / n * 100, 1)}% of the data)."
    )
    return {
        "labels": labels, "counts": counts, "n": n, "bins": k, "width": width,
        "min": vmin, "max": vmax, "interpretation": interpretation,
    }
