from __future__ import annotations

import sqlite3
import unicodedata
from datetime import date

from database import Database
from models import Voucher
from utils.formatters import normalize_date, normalize_period
from utils.validators import required

from .config_service import ConfigService


TABLES = {
    "ventas": "comprobantes_ventas",
    "compras": "comprobantes_compras",
}


def _normalized_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def _rolling_start(reference: date) -> date:
    month_index = reference.year * 12 + reference.month - 12
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


class VoucherService:
    def __init__(self, database: Database, config: ConfigService) -> None:
        self.database = database
        self.config = config

    @staticmethod
    def _table(kind: str) -> str:
        try:
            return TABLES[kind]
        except KeyError as error:
            raise ValueError("El tipo debe ser 'ventas' o 'compras'.") from error

    @staticmethod
    def calculate(voucher: Voucher, configured_sign: int | None = None) -> tuple[float, int, float]:
        if voucher.importe_original <= 0:
            raise ValueError("El importe debe ser mayor que cero.")
        currency = voucher.moneda.upper().strip()
        if currency != "ARS" and voucher.tipo_cambio <= 0:
            raise ValueError("Para moneda extranjera el tipo de cambio debe ser mayor a cero.")

        amount_pesos = (
            voucher.importe_original * voucher.tipo_cambio
            if currency != "ARS"
            else voucher.importe_original
        )
        kind = _normalized_text(voucher.tipo_comprobante)
        sign = configured_sign if configured_sign in (-1, 1) else (-1 if "nota de credito" in kind else 1)
        net = 0.0 if voucher.estado == "anulado" else amount_pesos * sign
        return round(amount_pesos, 2), sign, round(net, 2)

    def create(self, kind: str, voucher: Voucher) -> int:
        table = self._table(kind)
        voucher.fecha = normalize_date(voucher.fecha)
        voucher.periodo_fiscal = normalize_period(voucher.periodo_fiscal)
        voucher.tipo_comprobante = required(
            voucher.tipo_comprobante, "Tipo de comprobante"
        )
        voucher.punto_venta = required(voucher.punto_venta, "Punto de venta")
        voucher.numero_comprobante = required(
            voucher.numero_comprobante, "Número de comprobante"
        )
        voucher.contraparte_nombre = required(
            voucher.contraparte_nombre, "Cliente/proveedor"
        )
        voucher.moneda = voucher.moneda.upper().strip()
        if not voucher.moneda:
            raise ValueError("La moneda es obligatoria.")
        if voucher.estado not in ("normal", "anulado", "observado"):
            raise ValueError("El estado del comprobante no es válido.")

        voucher.tipo_comprobante, configured_sign = self.resolve_type(voucher.tipo_comprobante)
        amount_pesos, sign, net = self.calculate(voucher, configured_sign)
        try:
            with self.database.connection() as connection:
                cursor = connection.execute(
                    f"""
                    INSERT INTO {table}(
                        cliente_id, fecha, periodo_fiscal, tipo_comprobante,
                        punto_venta, numero_comprobante, contraparte_nombre,
                        numero_hasta, codigo_autorizacion, tipo_doc_contraparte,
                        contraparte_documento, tipo_doc_receptor, nro_doc_receptor,
                        concepto, moneda, tipo_cambio, importe_original,
                        importe_pesos, signo_fiscal, importe_neto_fiscal, estado,
                        origen, observaciones, nombre_archivo_origen,
                        fecha_importacion, tipo_archivo, usuario_importacion, id_importacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        voucher.cliente_id,
                        voucher.fecha,
                        voucher.periodo_fiscal,
                        voucher.tipo_comprobante,
                        voucher.punto_venta,
                        voucher.numero_comprobante,
                        voucher.contraparte_nombre,
                        voucher.numero_hasta,
                        voucher.codigo_autorizacion,
                        voucher.tipo_doc_contraparte,
                        voucher.contraparte_documento.strip(),
                        voucher.tipo_doc_receptor,
                        voucher.nro_doc_receptor,
                        voucher.concepto,
                        voucher.moneda,
                        voucher.tipo_cambio,
                        voucher.importe_original,
                        amount_pesos,
                        sign,
                        net,
                        voucher.estado,
                        voucher.origen,
                        voucher.observaciones.strip(),
                        voucher.nombre_archivo_origen,
                        voucher.fecha_importacion or None,
                        voucher.tipo_archivo,
                        voucher.usuario_importacion,
                        voucher.id_importacion,
                    ),
                )
                voucher_id = int(cursor.lastrowid)
                self._create_alerts(
                    connection,
                    kind,
                    voucher,
                    amount_pesos,
                )
                return voucher_id
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "Ya existe un comprobante con el mismo tipo, punto de venta y número."
            ) from error

    def resolve_type(self, value: str) -> tuple[str, int]:
        text = str(value).strip()
        code_text = text.split("-", 1)[0].strip().replace(".0", "")
        if code_text.isdigit():
            row = self.database.query_one(
                "SELECT descripcion, signo_fiscal FROM tipos_comprobante WHERE codigo = ? AND activo = 1",
                (int(code_text),),
            )
            if row:
                return str(row["descripcion"]), int(row["signo_fiscal"])
        normalized = _normalized_text(text)
        if "nota de credito" in normalized:
            return text, -1
        return text, 1

    def _create_alerts(self, connection, kind: str, voucher: Voucher, amount: float) -> None:
        threshold = self.config.get_client_float(
            voucher.cliente_id, "monto_comprobante_significativo", 500_000
        )
        period = voucher.periodo_fiscal
        label = "venta" if kind == "ventas" else "compra"
        if voucher.moneda != "ARS":
            connection.execute(
                """
                INSERT INTO alertas_fiscales(
                    cliente_id, periodo, tipo_alerta, descripcion,
                    importe_relacionado, gravedad
                ) VALUES (?, ?, ?, ?, ?, 'media')
                """,
                (
                    voucher.cliente_id,
                    period,
                    f"{label}_usd",
                    f"Comprobante de {label} registrado en {voucher.moneda}.",
                    amount,
                ),
            )
        if abs(amount) >= threshold:
            is_credit = "nota de credito" in _normalized_text(voucher.tipo_comprobante)
            alert_type = "nota_credito_significativa" if is_credit else f"{label}_significativa"
            connection.execute(
                """
                INSERT INTO alertas_fiscales(
                    cliente_id, periodo, tipo_alerta, descripcion,
                    importe_relacionado, gravedad
                ) VALUES (?, ?, ?, ?, ?, 'alta')
                """,
                (
                    voucher.cliente_id,
                    period,
                    alert_type,
                    f"Comprobante de {label} supera el monto significativo configurado.",
                    amount,
                ),
            )

    def list(
        self,
        kind: str,
        client_id: int | None = None,
        period: str = "",
        search: str = "",
    ) -> list[dict]:
        table = self._table(kind)
        conditions: list[str] = []
        params: list[object] = []
        if client_id:
            conditions.append("v.cliente_id = ?")
            params.append(client_id)
        if period.strip():
            conditions.append("v.periodo_fiscal = ?")
            params.append(normalize_period(period))
        if search.strip():
            conditions.append(
                "(v.contraparte_nombre LIKE ? OR v.contraparte_documento LIKE ? "
                "OR v.numero_comprobante LIKE ?)"
            )
            term = f"%{search.strip()}%"
            params.extend((term, term, term))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return [
            dict(row)
            for row in self.database.query(
                f"""
                SELECT v.*, c.nombre_razon_social AS cliente_nombre
                FROM {table} v
                JOIN clientes c ON c.id = v.cliente_id
                {where}
                ORDER BY v.fecha DESC, v.id DESC
                """,
                params,
            )
        ]

    def stats(self, kind: str, client_id: int, reference: date | None = None) -> dict:
        table = self._table(kind)
        reference = reference or date.today()
        current_period = reference.strftime("%Y-%m")
        year_prefix = f"{reference.year}-%"
        rolling = _rolling_start(reference).isoformat()
        row = self.database.query_one(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN periodo_fiscal = ? THEN importe_neto_fiscal END), 0) AS mes,
                COALESCE(SUM(CASE WHEN periodo_fiscal LIKE ? THEN importe_neto_fiscal END), 0) AS anio,
                COALESCE(SUM(CASE WHEN fecha >= ? AND fecha <= ? THEN importe_neto_fiscal END), 0) AS ultimos_12,
                COALESCE(SUM(CASE WHEN periodo_fiscal = ? AND signo_fiscal = -1 THEN 1 ELSE 0 END), 0) AS notas_credito_mes,
                COUNT(*) AS cantidad_total
            FROM {table}
            WHERE cliente_id = ?
            """,
            (
                current_period,
                year_prefix,
                rolling,
                reference.isoformat(),
                current_period,
                client_id,
            ),
        )
        return dict(row) if row else {}

    def monthly_summary(self, kind: str, client_id: int, limit: int = 12) -> list[dict]:
        table = self._table(kind)
        return [
            dict(row)
            for row in self.database.query(
                f"""
                SELECT periodo_fiscal AS periodo,
                       SUM(CASE WHEN signo_fiscal = 1 AND tipo_comprobante NOT LIKE '%Débito%'
                                THEN importe_neto_fiscal ELSE 0 END) AS facturas,
                       SUM(CASE WHEN signo_fiscal = -1 THEN ABS(importe_neto_fiscal) ELSE 0 END) AS notas_credito,
                       SUM(CASE WHEN tipo_comprobante LIKE '%Débito%'
                                THEN importe_neto_fiscal ELSE 0 END) AS notas_debito,
                       SUM(CASE WHEN estado = 'anulado' THEN 1 ELSE 0 END) AS anulados,
                       SUM(importe_neto_fiscal) AS total_neto,
                       COUNT(*) AS cantidad
                FROM {table}
                WHERE cliente_id = ?
                GROUP BY periodo_fiscal
                ORDER BY periodo_fiscal DESC
                LIMIT ?
                """,
                (client_id, limit),
            )
        ]

    def ranking(self, kind: str, client_id: int, limit: int = 10, by: str = "total") -> list[dict]:
        table = self._table(kind)
        total_row = self.database.query_one(
            f"SELECT COALESCE(SUM(importe_neto_fiscal), 0) AS total FROM {table} WHERE cliente_id = ?",
            (client_id,),
        )
        total = float(total_row["total"] or 0) if total_row else 0
        rows = self.database.query(
            f"""
            SELECT contraparte_nombre, contraparte_documento,
                   COUNT(*) AS cantidad, SUM(importe_neto_fiscal) AS total
            FROM {table}
            WHERE cliente_id = ?
            GROUP BY contraparte_nombre, contraparte_documento
            ORDER BY {"cantidad" if by == "cantidad" else "total"} DESC
            LIMIT ?
            """,
            (client_id, limit),
        )
        result = []
        for position, row in enumerate(rows, start=1):
            item = dict(row)
            item["puesto"] = position
            item["porcentaje"] = float(item["total"] or 0) / total if total else 0
            result.append(item)
        return result

    def noteworthy(self, kind: str, client_id: int, foreign_only: bool = False) -> list[dict]:
        table = self._table(kind)
        threshold = self.config.get_client_float(
            client_id, "monto_comprobante_significativo", 500_000
        )
        condition = "moneda <> 'ARS'" if foreign_only else "(ABS(importe_pesos) >= ? OR moneda <> 'ARS')"
        params = (client_id,) if foreign_only else (client_id, threshold)
        rows = self.database.query(
            f"""
            SELECT *, CASE
                WHEN moneda <> 'ARS' THEN 'Moneda extranjera'
                WHEN signo_fiscal = -1 THEN 'Nota de crédito significativa'
                WHEN tipo_comprobante LIKE '%Débito%' THEN 'Nota de débito significativa'
                ELSE 'Factura significativa' END AS motivo_alerta
            FROM {table} WHERE cliente_id = ? AND {condition}
            ORDER BY fecha DESC, ABS(importe_pesos) DESC
            """,
            params,
        )
        return [dict(row) for row in rows]

    def significant_counts(self, client_id: int) -> dict:
        threshold = self.config.get_client_float(
            client_id, "monto_comprobante_significativo", 500_000
        )
        sales = self.database.query_one(
            """
            SELECT
                SUM(CASE WHEN ABS(importe_pesos) >= ? THEN 1 ELSE 0 END) AS significativos,
                SUM(CASE WHEN moneda = 'USD' THEN 1 ELSE 0 END) AS usd
            FROM comprobantes_ventas WHERE cliente_id = ?
            """,
            (threshold, client_id),
        )
        purchases = self.database.query_one(
            """
            SELECT
                SUM(CASE WHEN ABS(importe_pesos) >= ? THEN 1 ELSE 0 END) AS significativos,
                SUM(CASE WHEN moneda = 'USD' THEN 1 ELSE 0 END) AS usd
            FROM comprobantes_compras WHERE cliente_id = ?
            """,
            (threshold, client_id),
        )
        return {
            "significativos": int((sales["significativos"] or 0) + (purchases["significativos"] or 0)),
            "usd": int((sales["usd"] or 0) + (purchases["usd"] or 0)),
        }

    def delete_selected(self, kind: str, client_id: int, voucher_ids: list[int]) -> int:
        """Borra comprobantes concretos, siempre limitados al cliente seleccionado."""
        table = self._table(kind)
        unique_ids = sorted(set(int(value) for value in voucher_ids))
        if not unique_ids:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        with self.database.connection() as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE cliente_id = ? AND id IN ({placeholders})",
                (client_id, *unique_ids),
            )
            connection.execute(
                """
                DELETE FROM importaciones_archivos
                WHERE cliente_id = ? AND id NOT IN (
                    SELECT id_importacion FROM comprobantes_ventas
                    WHERE id_importacion IS NOT NULL
                    UNION
                    SELECT id_importacion FROM comprobantes_compras
                    WHERE id_importacion IS NOT NULL
                )
                """,
                (client_id,),
            )
            return int(cursor.rowcount)
