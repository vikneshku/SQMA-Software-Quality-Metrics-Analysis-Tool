"""
sample_1_clean.py
A small, well-structured utility module: simple functions, low complexity,
clear naming, and no risky patterns. Expect this file to score HIGH on
Quality, LOW on Risk, and show no Security findings.
"""


def add(a, b):
    """Return the sum of two numbers."""
    return a + b


def subtract(a, b):
    """Return the difference of two numbers."""
    return a - b


def average(numbers):
    """Return the average of a list of numbers, or 0 for an empty list."""
    if not numbers:
        return 0
    return sum(numbers) / len(numbers)


def is_even(n):
    """Return True if n is even."""
    return n % 2 == 0


class TemperatureConverter:
    """Converts between Celsius and Fahrenheit."""

    def celsius_to_fahrenheit(self, celsius):
        return (celsius * 9 / 5) + 32

    def fahrenheit_to_celsius(self, fahrenheit):
        return (fahrenheit - 32) * 5 / 9


class ShoppingCart:
    """A simple shopping cart that tracks items and totals."""

    def __init__(self):
        self.items = []

    def add_item(self, name, price):
        self.items.append({"name": name, "price": price})

    def total(self):
        return sum(item["price"] for item in self.items)

    def item_count(self):
        return len(self.items)
