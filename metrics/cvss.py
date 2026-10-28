"""
metrics/cvss.py
CVSS v3 style severity bands, kept in ONE place (requirement 6).
Used by Python code, Jinja templates (filter `cvss_band`) and the REST API.

    0.0        None
    0.1 - 3.9  Low
    4.0 - 6.9  Medium
    7.0 - 8.9  High
    9.0 - 10.0 Critical
"""


def cvss_band(score):
    """Return the band name for a score (None when no score is set)."""
    if score is None or score == "":
        return None
    s = float(score)
    if s <= 0:
        return "None"
    if s < 4.0:
        return "Low"
    if s < 7.0:
        return "Medium"
    if s < 9.0:
        return "High"
    return "Critical"


def parse_cvss(raw):
    """Validate user input. Returns (value_or_None, error_message_or_None)."""
    if raw is None or str(raw).strip() == "":
        return None, None
    try:
        v = float(str(raw).strip())
    except ValueError:
        return None, "CVSS score must be a number between 0.0 and 10.0."
    if v != v or v < 0.0 or v > 10.0:          # v != v catches NaN
        return None, "CVSS score must be between 0.0 and 10.0."
    return round(v, 1), None
