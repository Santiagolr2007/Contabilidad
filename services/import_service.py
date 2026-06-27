from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from database import Database
from models import Voucher

from .voucher_service import VoucherService


def _key(value: object) -> str:
    text = "".join(
        character
        for character in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


ALIASES = {
    "fecha": ("fecha", "fecha de emision"),
    "tipo_comprobante": ("tipo", "tipo de comprobante"),
    "punto_venta": ("punto de venta",),
    "numero_desde": ("numero desde", "numero", "numero de comprobante"),
    "numero_hasta": ("numero hasta",),
    "codigo_autorizacion": ("cod autorizacion", "codigo autorizacion"),
    "tipo_doc_receptor": ("tipo doc receptor",),
    "nro_doc_receptor": ("nro doc receptor", "numero doc receptor"),
    "denominacion_receptor": ("denominacion receptor", "cliente receptor"),
    "tipo_doc_emisor": ("tipo doc emisor",),
    "nro_doc_emisor": ("nro doc emisor", "numero doc emisor"),
    "denominacion_emisor": ("denominacion emisor", "proveedor"),
    "tipo_cambio": ("tipo cambio", "tipo de cambio"),
    "moneda": ("moneda",),
    "importe_total": ("imp total", "importe total", "total"),
}


@dataclass(slots=True)
class ImportPreview:
    path: Path
    kind: str
    dataframe: pd.DataFrame
    mapping: dict[str, str]
    missing: list[str]


class ImportService:
    def __init__(self, database: Database, vouchers: VoucherService) -> None:
        self.database = database
        self.vouchers = vouchers

    @staticmethod
    def _header_row(preview: pd.DataFrame) -> int:
        for index, row in preview.iterrows():
            cells = {_key(value) for value in row.dropna()}
            has_date = "fecha" in cells or "fecha de emision" in cells
            if has_date and "imp total" in cells:
                return int(index)
        raise ValueError(
            "No se detectó la fila de encabezados. Debe contener Fecha e Imp. Total."
        )

    def read(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            preview = pd.read_excel(path, header=None, nrows=20)
            header = self._header_row(preview)
            dataframe = pd.read_excel(path, header=header, dtype=object)
        elif suffix == ".csv":
            text = None
            encoding_found = ""
            for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    text = path.read_text(encoding=encoding)
                    encoding_found = encoding
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                raise ValueError("No se pudo determinar la codificación del CSV.")
            lines = text.splitlines()
            header = next(
                (
                    index
                    for index, line in enumerate(lines[:30])
                    if "fecha" in _key(line) and "imp total" in _key(line)
                ),
                None,
            )
            if header is None:
                raise ValueError("No se encontró el encabezado Fecha / Imp. Total en el CSV.")
            separators = (";", ",", "\t", "|")
            separator = max(separators, key=lines[header].count)
            dataframe = pd.read_csv(
                path,
                header=header,
                sep=separator,
                encoding=encoding_found,
                dtype=object,
            )
        else:
            raise ValueError("El archivo debe ser XLSX o CSV.")
        dataframe.columns = [str(column).strip() for column in dataframe.columns]
        return dataframe.dropna(how="all")

    @staticmethod
    def suggest_mapping(dataframe: pd.DataFrame, kind: str) -> tuple[dict[str, str], list[str]]:
        normalized = {_key(column): str(column) for column in dataframe.columns}
        mapping: dict[str, str] = {}
        for field, aliases in ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    mapping[field] = normalized[alias]
                    break
        counterpart_fields = (
            ("denominacion_receptor", "nro_doc_receptor")
            if kind == "ventas"
            else ("denominacion_emisor", "nro_doc_emisor")
        )
        required = [
            "fecha",
            "tipo_comprobante",
            "punto_venta",
            "numero_desde",
            counterpart_fields[0],
            "moneda",
            "importe_total",
        ]
        missing = [field for field in required if field not in mapping]
        return mapping, missing

    def preview(self, path: Path, kind: str) -> ImportPreview:
        dataframe = self.read(path)
        mapping, missing = self.suggest_mapping(dataframe, kind)
        return ImportPreview(path, kind, dataframe, mapping, missing)

    @staticmethod
    def _value(row: pd.Series, mapping: dict[str, str], field: str, default=""):
        column = mapping.get(field)
        if not column:
            return default
        value = row.get(column, default)
        if pd.isna(value):
            return default
        return value

    @staticmethod
    def _amount(value: object, default: float = 0.0) -> float:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = re.sub(r"[^0-9,\.\-()]", "", str(value).strip())
        negative = text.startswith("(") and text.endswith(")")
        text = text.strip("()")
        if "," in text and "." in text:
            text = (
                text.replace(".", "").replace(",", ".")
                if text.rfind(",") > text.rfind(".")
                else text.replace(",", "")
            )
        elif "," in text:
            text = text.replace(",", ".")
        elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
        result = float(text or 0)
        return -abs(result) if negative else result

    @staticmethod
    def _date(value: object) -> str:
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.date().isoformat()
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text[:19], fmt).date().isoformat()
            except ValueError:
                continue
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"Fecha inválida: {text}")
        return parsed.date().isoformat()

    @staticmethod
    def _identifier(value: object) -> str:
        if value is None or pd.isna(value):
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    def import_rows(
        self,
        preview: ImportPreview,
        client_id: int,
        mapping: dict[str, str] | None = None,
    ) -> dict:
        mapping = mapping or preview.mapping
        _, missing = self.suggest_mapping(preview.dataframe, preview.kind)
        missing = [field for field in missing if field not in mapping]
        if missing:
            raise ValueError(f"Falta mapear: {', '.join(missing)}")

        imported_at = datetime.now().isoformat(timespec="seconds")
        import_id = self.database.execute(
            """
            INSERT INTO importaciones_archivos(
                cliente_id, tipo, archivo, formato, filas_leidas
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                client_id,
                preview.kind,
                preview.path.name,
                preview.path.suffix.lower(),
                len(preview.dataframe),
            ),
        )
        imported = duplicates = errors = 0
        messages: list[str] = []
        for index, row in preview.dataframe.iterrows():
            try:
                date_value = self._value(row, mapping, "fecha")
                if not date_value:
                    continue
                amount = abs(self._amount(self._value(row, mapping, "importe_total")))
                voucher_date = self._date(date_value)
                currency_raw = _key(self._value(row, mapping, "moneda", "ARS"))
                if currency_raw in ("", "ars", "peso", "pesos", "$"):
                    currency = "ARS"
                elif currency_raw in ("usd", "u s", "u s d", "dolar"):
                    currency = "USD"
                else:
                    currency = str(self._value(row, mapping, "moneda")).strip().upper()
                exchange_rate = self._amount(
                    self._value(row, mapping, "tipo_cambio", 1), 1
                ) or 1
                if preview.kind == "ventas":
                    counterpart_name = self._value(row, mapping, "denominacion_receptor")
                    counterpart_document = self._value(row, mapping, "nro_doc_receptor")
                    counterpart_type = self._value(row, mapping, "tipo_doc_receptor")
                else:
                    counterpart_name = self._value(row, mapping, "denominacion_emisor")
                    counterpart_document = self._value(row, mapping, "nro_doc_emisor")
                    counterpart_type = self._value(row, mapping, "tipo_doc_emisor")
                point = self._identifier(self._value(row, mapping, "punto_venta")) or "0"
                number = self._identifier(self._value(row, mapping, "numero_desde")) or f"PENDIENTE-{index + 2}"
                observed = not counterpart_name or point == "0" or number.startswith("PENDIENTE-")
                voucher = Voucher(
                    cliente_id=client_id,
                    fecha=voucher_date,
                    periodo_fiscal=voucher_date[:7],
                    tipo_comprobante=str(self._value(row, mapping, "tipo_comprobante")),
                    punto_venta=point,
                    numero_comprobante=number,
                    numero_hasta=self._identifier(self._value(row, mapping, "numero_hasta")),
                    codigo_autorizacion=self._identifier(self._value(row, mapping, "codigo_autorizacion")),
                    contraparte_nombre=str(counterpart_name or "Sin denominación"),
                    tipo_doc_contraparte=self._identifier(counterpart_type),
                    contraparte_documento=self._identifier(counterpart_document),
                    tipo_doc_receptor=self._identifier(self._value(row, mapping, "tipo_doc_receptor")),
                    nro_doc_receptor=self._identifier(self._value(row, mapping, "nro_doc_receptor")),
                    moneda=currency,
                    tipo_cambio=exchange_rate,
                    importe_original=amount,
                    estado="observado" if observed else "normal",
                    origen=preview.path.suffix.lower().lstrip("."),
                    nombre_archivo_origen=preview.path.name,
                    fecha_importacion=imported_at,
                    tipo_archivo=preview.path.suffix.lower().lstrip("."),
                    usuario_importacion="local",
                    id_importacion=import_id,
                )
                self.vouchers.create(preview.kind, voucher)
                imported += 1
            except ValueError as error:
                if "Ya existe un comprobante" in str(error):
                    duplicates += 1
                else:
                    errors += 1
                    if len(messages) < 5:
                        messages.append(f"Fila {index + 2}: {error}")
            except Exception as error:
                errors += 1
                if len(messages) < 5:
                    messages.append(f"Fila {index + 2}: {error}")

        self.database.execute(
            """
            UPDATE importaciones_archivos SET
                filas_importadas = ?, filas_duplicadas = ?, filas_error = ?,
                observaciones = ? WHERE id = ?
            """,
            (
                imported,
                duplicates,
                errors,
                "\n".join(messages),
                import_id,
            ),
        )
        return {
            "read": len(preview.dataframe),
            "imported": imported,
            "duplicates": duplicates,
            "errors": errors,
            "messages": messages,
            "import_id": import_id,
        }

    def list_batches(self, client_id: int, kind: str | None = None) -> list[dict]:
        condition = " AND tipo = ?" if kind else ""
        params = (client_id, kind) if kind else (client_id,)
        return [
            dict(row)
            for row in self.database.query(
                """
                SELECT * FROM importaciones_archivos
                WHERE cliente_id = ?""" + condition + " ORDER BY fecha_importacion DESC, id DESC",
                params,
            )
        ]

    def delete_imported_kind(self, client_id: int, kind: str) -> int:
        table = "comprobantes_ventas" if kind == "ventas" else "comprobantes_compras"
        with self.database.connection() as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE cliente_id = ? AND (id_importacion IS NOT NULL OR origen IN ('csv','xlsx','excel','arca'))",
                (client_id,),
            )
            connection.execute(
                "DELETE FROM importaciones_archivos WHERE cliente_id = ? AND tipo = ?",
                (client_id, kind),
            )
            return int(cursor.rowcount)

    def delete_period(self, client_id: int, period: str) -> int:
        deleted = 0
        with self.database.connection() as connection:
            for table in ("comprobantes_ventas", "comprobantes_compras"):
                cursor = connection.execute(
                    f"DELETE FROM {table} WHERE cliente_id = ? AND periodo_fiscal = ? AND (id_importacion IS NOT NULL OR origen IN ('csv','xlsx','excel','arca'))",
                    (client_id, period),
                )
                deleted += int(cursor.rowcount)
            connection.execute(
                """
                DELETE FROM importaciones_archivos WHERE cliente_id = ?
                AND id NOT IN (
                    SELECT id_importacion FROM comprobantes_ventas WHERE id_importacion IS NOT NULL
                    UNION SELECT id_importacion FROM comprobantes_compras WHERE id_importacion IS NOT NULL
                )
                """,
                (client_id,),
            )
        return deleted

    def delete_batch(self, client_id: int, import_id: int) -> int:
        deleted = 0
        with self.database.connection() as connection:
            for table in ("comprobantes_ventas", "comprobantes_compras"):
                cursor = connection.execute(
                    f"DELETE FROM {table} WHERE cliente_id = ? AND id_importacion = ?",
                    (client_id, import_id),
                )
                deleted += int(cursor.rowcount)
            connection.execute(
                "DELETE FROM importaciones_archivos WHERE cliente_id = ? AND id = ?",
                (client_id, import_id),
            )
        return deleted

    def delete_all_vouchers(self, client_id: int) -> int:
        deleted = 0
        with self.database.connection() as connection:
            for table in ("comprobantes_ventas", "comprobantes_compras"):
                cursor = connection.execute(
                    f"DELETE FROM {table} WHERE cliente_id = ?", (client_id,)
                )
                deleted += int(cursor.rowcount)
            connection.execute(
                "DELETE FROM importaciones_archivos WHERE cliente_id = ?", (client_id,)
            )
            connection.execute(
                "DELETE FROM alertas_fiscales WHERE cliente_id = ?", (client_id,)
            )
            connection.execute(
                "DELETE FROM iibb_monotributo WHERE cliente_id = ?", (client_id,)
            )
            connection.execute(
                "DELETE FROM recategorizaciones_monotributo WHERE cliente_id = ?",
                (client_id,),
            )
        return deleted
