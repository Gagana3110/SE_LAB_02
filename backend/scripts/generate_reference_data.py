"""Generates the synthetic reference data set described in the Test Plan.

50 products, 30 raw materials, 10 suppliers and 36 months of sales with a known trend,
seasonality and noise. A fixed seed makes every run produce identical files.

Usage: python scripts/generate_reference_data.py [output_dir]
"""

import csv
import math
import random
import sys
from pathlib import Path

SEED = 42
PRODUCTS = 50
MATERIALS = 30
SUPPLIERS = 10
MONTHS = 36
SHORT_HISTORY_MONTHS = 6
SHORT_HISTORY_PRODUCTS = 2  # the last products exercise the DFS-F-014 fallback
START_YEAR, START_MONTH = 2023, 11
CATEGORIES = ["Electronics", "Furniture", "Packaging", "Appliances"]
UNITS = ["kg", "litre", "piece", "metre"]


def month_label(offset: int) -> str:
    index = START_MONTH - 1 + offset
    return f"{START_YEAR + index // 12}-{index % 12 + 1:02d}-01"


def demand(base: float, trend: float, amplitude: float, phase: float, t: int, noise: float) -> int:
    seasonal = amplitude * math.sin(2 * math.pi * (t + phase) / 12)
    return max(0, round(base * (1 + trend * t) * (1 + seasonal) + noise))


def build(rng: random.Random) -> dict[str, tuple[list[str], list[list]]]:
    products = [[f"P{i:03d}", f"Product {i}", "piece", rng.choice(CATEGORIES)]
                for i in range(1, PRODUCTS + 1)]
    materials = [[f"M{i:03d}", f"Material {i}", rng.choice(UNITS)]
                 for i in range(1, MATERIALS + 1)]
    suppliers = [[f"S{i:02d}", f"Supplier {i}", rng.randint(3, 30), rng.choice([50, 100, 200, 500]),
                  round(rng.uniform(5, 120), 2), rng.randint(2000, 20000), rng.randint(75, 99)]
                 for i in range(1, SUPPLIERS + 1)]

    bom = []
    for product in products:
        for material in rng.sample(materials, rng.randint(2, 4)):
            bom.append([product[0], material[0], rng.randint(1, 8)])

    links = []
    for material in materials:
        chosen = rng.sample(suppliers, rng.randint(1, 3))
        for position, supplier in enumerate(chosen):
            links.append([material[0], supplier[0], "yes" if position == 0 else "no"])

    sales = []
    for number, product in enumerate(products, start=1):
        base = rng.randint(100, 1000)
        trend = rng.uniform(-0.005, 0.015)
        amplitude = rng.uniform(0.05, 0.35)
        phase = rng.uniform(0, 12)
        short = number > PRODUCTS - SHORT_HISTORY_PRODUCTS
        first = MONTHS - SHORT_HISTORY_MONTHS if short else 0
        for t in range(first, MONTHS):
            noise = rng.gauss(0, base * 0.05)
            sales.append([month_label(t), product[0], demand(base, trend, amplitude, phase, t, noise)])

    return {
        "products.csv": (["code", "name", "unit", "category"], products),
        "materials.csv": (["code", "name", "unit"], materials),
        "suppliers.csv": (["code", "name", "lead_time_days", "moq", "unit_price",
                           "monthly_capacity", "reliability_pct"], suppliers),
        "bom.csv": (["product_code", "material_code", "qty_per_unit"], bom),
        "material_suppliers.csv": (["material_code", "supplier_code", "preferred"], links),
        "sales.csv": (["date", "product_code", "quantity"], sales),
    }


def write(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, (header, rows) in build(random.Random(SEED)).items():  # nosec B311
        with open(output_dir / name, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    write(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../data/reference"))
