#!/usr/bin/env python3
import sys

sys.path.insert(0, ".")

import asyncio

from app.data_loader import load_products
from app.matcher import async_match_positions


async def test_matcher():
    print("=== Loading products ===")
    products = load_products()
    print(f"Loaded {len(products)} products")

    # Show first product structure
    if products:
        sample = products[0]
        print(f"Sample product type: {type(sample)}")
        if hasattr(sample, "model_dump"):
            print(f"Sample product data: {sample.model_dump()}")
        else:
            print(f"Sample product data: {sample}")

    print("\n=== Creating test items ===")
    test_items = [
        {"name": "carrot", "qty": 1.065, "unit": "kg", "price": 22000.0},
        {"name": "mozzarela", "qty": 1.0, "unit": "kg", "price": 244000.0},
        {"name": "mayo", "qty": 2.0, "unit": "kg", "price": 160000.0},
    ]

    print("\n=== Running matcher ===")
    results = await async_match_positions(test_items, products, threshold=0.7)

    print(f"\n=== Results ({len(results)} items) ===")
    for i, result in enumerate(results):
        print(f"Result {i+1}:")
        print(f"  Keys: {list(result.keys())}")
        print(f"  Name: {result.get('name', 'NO NAME')}")
        print(f"  ID: {result.get('id', 'NO ID!')}")
        print(f"  Status: {result.get('status', 'NO STATUS')}")
        print(f"  Score: {result.get('score', 'NO SCORE')}")
        print()


if __name__ == "__main__":
    asyncio.run(test_matcher())
