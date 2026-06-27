from __future__ import annotations

from datetime import date

from database import Database

from .monotributo_service import MonotributoService


class RecategorizationService:
    def __init__(self, database: Database, monotributo: MonotributoService) -> None:
        self.database = database
        self.monotributo = monotributo

    def calculate(self, client_id: int) -> dict:
        dashboard = self.monotributo.dashboard(client_id)
        revenue = float(dashboard["sales"].get("ultimos_12", 0))
        current = dashboard["client"].get("categoria_actual", "")
        suggested = dashboard["suggested_category"]
        limit = float(dashboard["category_limit"] or 0)
        status = "OK"
        if dashboard["category_status"] == "excedido":
            status = "excedido"
        elif current and suggested != current:
            status = "debe recategorizar"
        elif limit and revenue >= limit * 0.9:
            status = "riesgo de exclusión"
        end = date.today()
        start_month = end.year * 12 + end.month - 12
        start_year, month_zero = divmod(start_month, 12)
        return {
            "cliente": dashboard["client"]["nombre_razon_social"],
            "actividad_fiscal": dashboard["client"].get("actividad_fiscal", ""),
            "denominacion": dashboard["client"].get("denominacion", ""),
            "categoria_actual": current,
            "categoria_sugerida": suggested,
            "periodo_desde": f"{start_year}-{month_zero + 1:02d}",
            "periodo_hasta": end.strftime("%Y-%m"),
            "ventas": revenue,
            "diferencia_tope": limit - revenue,
            "estado": status,
        }

    def save(self, client_id: int, values: dict) -> int:
        calculation = self.calculate(client_id)
        return self.database.execute(
            """
            INSERT INTO recategorizaciones_monotributo(
                cliente_id, periodo_desde, periodo_hasta, ventas_ultimos_12_meses,
                categoria_actual, categoria_sugerida, diferencia_tope, estado,
                alquileres, energia, superficie, precio_unitario_maximo, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id, calculation["periodo_desde"], calculation["periodo_hasta"],
                calculation["ventas"], calculation["categoria_actual"],
                calculation["categoria_sugerida"], calculation["diferencia_tope"],
                calculation["estado"], float(values.get("alquileres", 0)),
                float(values.get("energia", 0)), float(values.get("superficie", 0)),
                float(values.get("precio_unitario_maximo", 0)),
                values.get("observaciones", ""),
            ),
        )
