from __future__ import annotations

from datetime import date, datetime


def money(value: float | int | None) -> str:
    value = float(value or 0)
    formatted = f"{value:,.2f}"
    return "$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def percentage(value: float | int | None) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("La fecha debe tener formato DD/MM/AAAA o AAAA-MM-DD.")


def normalize_date(value: str) -> str:
    return parse_date(value).isoformat()


def normalize_period(value: str) -> str:
    value = value.strip().replace("/", "-")
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
    except ValueError as error:
        raise ValueError("El período debe tener formato AAAA-MM.") from error
