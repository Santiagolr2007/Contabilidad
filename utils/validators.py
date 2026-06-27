from __future__ import annotations

import re


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def validate_cuit(value: str) -> str:
    normalized = digits(value)
    if len(normalized) != 11:
        raise ValueError("El CUIT/CUIL debe contener exactamente 11 dígitos.")
    return normalized


def validate_email(value: str) -> str:
    value = value.strip()
    if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("El correo electrónico no tiene un formato válido.")
    return value


def required(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"El campo '{label}' es obligatorio.")
    return value


def positive_number(value: str | float, label: str, allow_zero: bool = False) -> float:
    text = str(value).strip().replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        number = float(text)
    except ValueError as error:
        raise ValueError(f"'{label}' debe ser un número válido.") from error
    if number < 0 or (number == 0 and not allow_zero):
        qualifier = "mayor o igual a cero" if allow_zero else "mayor que cero"
        raise ValueError(f"'{label}' debe ser {qualifier}.")
    return number
