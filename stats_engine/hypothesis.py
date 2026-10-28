"""
stats_engine/hypothesis.py
Hypothesis tests built on scipy.stats (requirement 21).

    welch_resolution_time   Welch two-sample t-test (unequal variances)
    one_sample_complexity   One-sample t-test against a target value
    chi_square_independence Chi-square test of independence on a contingency table

Every function returns a dict with: title, h0, h1, table (headers + rows), statistic, df,
p_value, alpha, reject, conclusion, warnings. Too-small samples never raise - they return
`ok: False` with a warning message.
"""
import math
from collections import Counter

from scipy import stats

from config import ALPHA
from models import utcnow


def _base(title, h0, h1):
    return {"title": title, "h0": h0, "h1": h1, "table": {"headers": [], "rows": []},
            "statistic": None, "df": None, "p_value": None, "alpha": ALPHA,
            "reject": None, "conclusion": "", "warnings": [], "ok": False}


def _finish(res, stat, df, p, meaning_reject, meaning_keep):
    stat = float(stat)
    p = float(p)
    if math.isnan(stat) or math.isnan(p):
        res["warnings"].append("The test could not be calculated (no variation in the data).")
        res["conclusion"] = "No conclusion: the data has no variation."
        return res
    res.update(statistic=round(stat, 4), df=round(float(df), 2) if df is not None else None,
               p_value=round(p, 4), ok=True)
    res["reject"] = p < ALPHA
    res["conclusion"] = (f"p = {res['p_value']} is {'below' if res['reject'] else 'not below'} alpha = {ALPHA}: "
                         + ("reject H0 - " + meaning_reject if res["reject"] else "fail to reject H0 - " + meaning_keep))
    return res


def welch_resolution_time(bugs) -> dict:
    """Resolution time (hours) of High/Critical bugs vs Low/Medium bugs."""
    res = _base("Welch t-test: resolution time, High/Critical vs Low/Medium bugs",
                "Mean resolution time of High/Critical bugs = mean resolution time of Low/Medium bugs.",
                "The two mean resolution times differ.")
    hi, lo = [], []
    for b in bugs:
        if b.resolved_at and b.created_at:
            hours = (b.resolved_at - b.created_at).total_seconds() / 3600.0
            (hi if b.severity in ("High", "Critical") else lo).append(hours)

    def row(name, v):
        if not v:
            return [name, 0, "-", "-"]
        sd = stats.tstd(v) if len(v) > 1 else 0
        return [name, len(v), round(sum(v) / len(v), 2), round(sd, 2)]

    res["table"] = {"headers": ["Group", "n", "Mean (hours)", "Std dev"],
                    "rows": [row("High / Critical", hi), row("Low / Medium", lo)]}
    if len(hi) < 2 or len(lo) < 2:
        res["warnings"].append("Sample too small: each group needs at least 2 resolved bugs "
                               f"(High/Critical has {len(hi)}, Low/Medium has {len(lo)}).")
        res["conclusion"] = "Not enough data to run this test."
        return res
    t = stats.ttest_ind(hi, lo, equal_var=False)
    return _finish(res, t.statistic, t.df, t.pvalue,
                   "severe bugs take a significantly different time to resolve than minor bugs.",
                   "there is no significant difference in resolution time between severe and minor bugs.")


def one_sample_complexity(complexities, target) -> dict:
    """Average function complexity vs a target value."""
    res = _base(f"One-sample t-test: average function complexity vs target {target:g}",
                f"Mean function complexity = {target:g}.", f"Mean function complexity differs from {target:g}.")
    v = [float(x) for x in complexities]
    mean = sum(v) / len(v) if v else 0
    sd = stats.tstd(v) if len(v) > 1 else 0
    res["table"] = {"headers": ["n (functions)", "Mean", "Std dev", "Target"],
                    "rows": [[len(v), round(mean, 2), round(sd, 2), target]]}
    if len(v) < 2:
        res["warnings"].append("Sample too small: at least 2 functions are needed (upload source code first).")
        res["conclusion"] = "Not enough data to run this test."
        return res
    if sd == 0:
        res["warnings"].append("All functions have the same complexity, so the t-test cannot be calculated.")
        res["conclusion"] = "No variation in the data."
        return res
    t = stats.ttest_1samp(v, target)
    direction = "above" if mean > target else "below"
    return _finish(res, t.statistic, len(v) - 1, t.pvalue,
                   f"average complexity ({mean:.2f}) is significantly {direction} the target of {target:g}.",
                   f"average complexity ({mean:.2f}) is not significantly different from the target of {target:g}.")


def chi_square_independence(pairs, row_name, col_name, row_order=None, col_order=None) -> dict:
    """pairs: list of (row_value, col_value). Tests independence of the two variables."""
    res = _base(f"Chi-square test of independence: {row_name} vs {col_name}",
                f"{row_name} and {col_name} are independent.", f"{row_name} and {col_name} are associated.")
    counts = Counter(pairs)
    rows = [r for r in (row_order or sorted({p[0] for p in pairs})) if any(k[0] == r for k in counts)]
    cols = [c for c in (col_order or sorted({p[1] for p in pairs})) if any(k[1] == c for k in counts)]
    table = [[counts.get((r, c), 0) for c in cols] for r in rows]
    res["table"] = {"headers": [row_name + " \\ " + col_name] + cols + ["Total"],
                    "rows": [[r] + t + [sum(t)] for r, t in zip(rows, table)]}
    if len(rows) < 2 or len(cols) < 2:
        res["warnings"].append(f"Need at least 2 different {row_name} values and 2 different {col_name} values "
                               f"(found {len(rows)} and {len(cols)}).")
        res["conclusion"] = "Not enough data to run this test."
        return res
    chi2, p, dof, expected = stats.chi2_contingency(table)
    low = int((expected < 5).sum())
    if low:
        res["warnings"].append(f"{low} of {expected.size} cells have an expected count below 5, so the "
                               "chi-square approximation may be unreliable. Treat the result with caution.")
    return _finish(res, chi2, dof, p,
                   f"{row_name} and {col_name} are statistically associated.",
                   f"no significant association between {row_name} and {col_name} was found.")


def run_all(bugs, complexities, target, releases_by_id) -> list:
    sev_order = ["Low", "Medium", "High", "Critical"]
    tests = [welch_resolution_time(bugs), one_sample_complexity(complexities, target),
             chi_square_independence([(b.module or "General", b.severity) for b in bugs],
                                     "Module", "Severity", col_order=sev_order)]
    rel_pairs = [(releases_by_id[b.release_id].name, b.severity) for b in bugs if b.release_id in releases_by_id]
    tests.append(chi_square_independence(rel_pairs, "Release", "Severity", col_order=sev_order))
    return tests
