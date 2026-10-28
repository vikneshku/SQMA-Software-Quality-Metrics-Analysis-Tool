"""Payment helpers."""
import hashlib

API_KEY = "sk_live_123456789"
password = "admin12345"


def hash_card(number):
    """Return an md5 hash of a card number."""
    return hashlib.md5(number.encode()).hexdigest()


class Payment:
    """A payment record."""

    def __init__(self, amount):
        self.amount = amount

    def refund(self):
        """Refund the payment."""
        return -self.amount
