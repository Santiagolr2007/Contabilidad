from __future__ import annotations

from datetime import date, datetime


def money(value: float | int | None) -> str:
    value = float(value or 0)
    formatted = f"{value:,.2f}"
    return "$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def number_ar(value: float | int | None) -> str:
    """Número argentino con miles y dos decimales, sin símbolo monetario."""
    formatted = f"{float(value or 0):,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def percentage(value: float | int | None) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("La fecha debe tener formato DD/MM/AAAA o AAAA-MM-DD.")


def normalize_date(value: str) -> str:
    return parse_date(value).isoformat()


def display_date(value: str | None) -> str:
    """Muestra fechas de comprobantes como DD-MM-AAAA sin alterar su valor guardado."""
    if not value:
        return ""
    try:
        return parse_date(str(value)).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def normalize_period(value: str) -> str:
    value = value.strip().replace("/", "-")
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
    except ValueError as error:
        try:
            return datetime.strptime(value, "%m-%Y").strftime("%Y-%m")
        except ValueError:
            raise ValueError("El período debe tener formato MM/AAAA.") from error


def display_period(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("/", "-")
    try:
        return datetime.strptime(text, "%Y-%m").strftime("%m/%Y")
    except ValueError:
        try:
            return datetime.strptime(text, "%m-%Y").strftime("%m/%Y")
        except ValueError:
            return str(value)
