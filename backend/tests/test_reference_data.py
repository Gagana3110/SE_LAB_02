import csv
import importlib.util
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "generate_reference_data.py"
spec = importlib.util.spec_from_file_location("generate_reference_data", SCRIPT)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def read(directory: Path, name: str) -> list[dict]:
    with open(directory / name, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_sizes_match_the_test_plan(tmp_path):
    generator.write(tmp_path)
    assert len(read(tmp_path, "products.csv")) == 50
    assert len(read(tmp_path, "materials.csv")) == 30
    assert len(read(tmp_path, "suppliers.csv")) == 10


def test_history_lengths(tmp_path):
    generator.write(tmp_path)
    months = Counter(row["product_code"] for row in read(tmp_path, "sales.csv"))
    assert months["P001"] == 36
    assert months["P048"] == 36
    assert months["P049"] == 6
    assert months["P050"] == 6


def test_data_is_valid_and_linked(tmp_path):
    generator.write(tmp_path)
    assert all(int(row["quantity"]) >= 0 for row in read(tmp_path, "sales.csv"))
    products = {row["code"] for row in read(tmp_path, "products.csv")}
    assert {row["product_code"] for row in read(tmp_path, "bom.csv")} == products
    links = read(tmp_path, "material_suppliers.csv")
    preferred = Counter(row["material_code"] for row in links if row["preferred"] == "yes")
    assert len(preferred) == 30 and set(preferred.values()) == {1}


def test_output_is_reproducible(tmp_path):
    generator.write(tmp_path / "a")
    generator.write(tmp_path / "b")
    for name in ("sales.csv", "bom.csv", "suppliers.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
