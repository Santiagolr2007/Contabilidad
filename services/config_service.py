from __future__ import annotations

from database import Database


class ConfigService:
    CLIENT_ALERT_KEYS = (
        "monotributo_alerta_porcentaje",
        "monto_comprobante_significativo",
        "concentracion_porcentaje",
        "compras_ventas_alerta",
        "muchas_facturas_dia",
        "muchas_facturas_cliente",
    )

    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, key: str, default: str = "") -> str:
        row = self.database.query_one(
            "SELECT valor FROM configuracion WHERE clave = ?", (key,)
        )
        return str(row["valor"]) if row else default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key, str(default)))
        except ValueError:
            return default

    def get_client_float(
        self, client_id: int, key: str, default: float = 0.0
    ) -> float:
        row = self.database.query_one(
            """
            SELECT valor FROM configuracion_alertas_cliente
            WHERE cliente_id = ? AND clave = ?
            """,
            (client_id, key),
        )
        if row:
            try:
                return float(row["valor"])
            except (TypeError, ValueError):
                pass
        return self.get_float(key, default)

    def get_client_alerts(self, client_id: int) -> dict[str, float]:
        defaults = {
            "monotributo_alerta_porcentaje": 0.80,
            "monto_comprobante_significativo": 500_000,
            "concentracion_porcentaje": 0.30,
            "compras_ventas_alerta": 0.80,
            "muchas_facturas_dia": 10,
            "muchas_facturas_cliente": 10,
        }
        return {
            key: self.get_client_float(client_id, key, defaults[key])
            for key in self.CLIENT_ALERT_KEYS
        }

    def save_client_alerts(self, client_id: int, values: dict[str, float]) -> None:
        unknown = set(values) - set(self.CLIENT_ALERT_KEYS)
        if unknown:
            raise ValueError("La configuración de alertas contiene opciones desconocidas.")
        percentages = {
            "monotributo_alerta_porcentaje",
            "concentracion_porcentaje",
            "compras_ventas_alerta",
        }
        counts = {"muchas_facturas_dia", "muchas_facturas_cliente"}
        normalized: list[tuple[int, str, str]] = []
        for key in self.CLIENT_ALERT_KEYS:
            if key not in values:
                continue
            value = float(values[key])
            if value < 0:
                raise ValueError("Los valores de alerta no pueden ser negativos.")
            if key in percentages and value > 1:
                raise ValueError("Los porcentajes de alerta deben estar entre 0 y 100 %.")
            if key in counts and (value < 1 or not value.is_integer()):
                raise ValueError("Las cantidades de comprobantes deben ser números enteros positivos.")
            normalized.append((client_id, key, str(value)))
        with self.database.connection() as connection:
            connection.executemany(
                """
                INSERT INTO configuracion_alertas_cliente(cliente_id, clave, valor)
                VALUES (?, ?, ?)
                ON CONFLICT(cliente_id, clave) DO UPDATE SET
                    valor = excluded.valor,
                    actualizado_en = CURRENT_TIMESTAMP
                """,
                normalized,
            )

    def list_all(self) -> list[dict]:
        return [
            dict(row)
            for row in self.database.query(
                "SELECT clave, valor, tipo, descripcion FROM configuracion ORDER BY clave"
            )
        ]

    def update(self, key: str, value: str) -> None:
        if not value.strip():
            raise ValueError("El valor de configuración no puede quedar vacío.")
        existing = self.database.query_one(
            "SELECT tipo FROM configuracion WHERE clave = ?", (key,)
        )
        if not existing:
            raise ValueError("La opción de configuración no existe.")
        if existing["tipo"] in ("numero", "decimal"):
            numeric = float(value.replace(",", "."))
            if numeric < 0:
                raise ValueError("El valor no puede ser negativo.")
            value = str(numeric)
        self.database.execute(
            """
            UPDATE configuracion
            SET valor = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE clave = ?
            """,
            (value, key),
        )

    def list_categories(self) -> list[dict]:
        return [
            dict(row)
            for row in self.database.query(
                """
                SELECT id, categoria, tope_ingresos, vigencia_desde,
                       COALESCE(vigencia_hasta, '') AS vigencia_hasta, observaciones
                FROM categorias_monotributo
                ORDER BY vigencia_desde DESC, tope_ingresos
                """
            )
        ]

    def update_category_limit(self, category_id: int, value: str) -> None:
        try:
            limit = float(value.replace(".", "").replace(",", "."))
        except ValueError as error:
            raise ValueError("El tope de ingresos debe ser numérico.") from error
        if limit <= 0:
            raise ValueError("El tope de ingresos debe ser mayor que cero.")
        self.database.execute(
            "UPDATE categorias_monotributo SET tope_ingresos = ? WHERE id = ?",
            (limit, category_id),
        )
