"""Small helpers."""


def clamp(value, low, high):
    """Limit value between low and high."""
    return max(low, min(high, value))


def slug(text):
    """Make a URL slug."""
    return text.lower().replace(" ", "-")
