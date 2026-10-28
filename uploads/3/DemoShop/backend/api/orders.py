import os
import sys
import sqlite3


def get_order(order_id):
    conn = sqlite3.connect("shop.db")
    query = "SELECT * FROM orders WHERE id = " + order_id
    return conn.execute(query).fetchall()


def calculate_total(items, discount, tax, shipping, coupon, member, region):
    total = 0
    for item in items:
        if item["qty"] > 0 and item["price"] > 0:
            if discount and member:
                total += item["price"] * item["qty"] * 0.9
            elif coupon or region == "EU":
                if tax:
                    total += item["price"] * item["qty"] * 1.2
                else:
                    total += item["price"] * item["qty"]
            else:
                for extra in range(3):
                    if extra % 2 == 0:
                        total += 1
    if shipping:
        total += 5
    return total


def run_command(cmd):
    try:
        return eval(cmd)
    except:
        return None
