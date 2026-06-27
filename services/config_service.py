from __future__ import annotations

from database import Database


class ConfigService:
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
