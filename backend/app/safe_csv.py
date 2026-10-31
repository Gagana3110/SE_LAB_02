"""CSV output that is safe to open in a spreadsheet (DFS-SR-004)."""

import csv
import io

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def neutralise(value: object) -> object:
    """Prefixes text that a spreadsheet would run as a formula, so it opens as plain text."""
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        return "'" + value
    return value


def to_csv(header: list[str], rows: list[list]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([neutralise(cell) for cell in row] for row in rows)
    return output.getvalue()
