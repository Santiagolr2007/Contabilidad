from __future__ import annotations

from datetime import date

from database import Database

from .monotributo_service import MonotributoService


class RecategorizationService:
    def __init__(self, database: Database, monotributo: MonotributoService) -> None:
        self.database = database
        self.monotributo = monotributo

    def calculate(self, client_id: int, values: dict | None = None) -> dict:
        values = values or {}
        dashboard = self.monotributo.dashboard(client_id)
        revenue = float(dashboard["sales"].get("ultimos_12", 0))
        current = dashboard["client"].get("categoria_actual", "")
        suggested = dashboard["suggested_category"]
        limit = float(dashboard["current_category_limit"] or 0)
        maximum_row = self.database.query_one(
            "SELECT MAX(tope_ingresos) limite FROM categorias_monotributo WHERE estado='Vigente'"
        )
        if not maximum_row or not maximum_row["limite"]:
            maximum_row = self.database.query_one("SELECT MAX(tope_ingresos) limite FROM categorias_monotributo")
        maximum = float(maximum_row["limite"] or 0) if maximum_row else 0.0
        category_row = self.database.query_one(
            """SELECT * FROM categorias_monotributo WHERE categoria=?
               ORDER BY CASE WHEN estado='Vigente' THEN 0 ELSE 1 END,
                        vigencia_desde DESC LIMIT 1""", (current,),
        )
        utilization = revenue / limit if limit else 0.0
        if maximum and revenue > maximum:
            status = "Excluido / supera categoría máxima"
        elif limit and revenue > limit:
            status = "Supera categoría actual"
        elif current and suggested != current:
            status = "Debe recategorizar"
        elif utilization >= .90:
            status = "Cerca del límite (90%)"
        elif utilization >= .80:
            status = "Cerca del límite (80%)"
        else:
            status = "OK"
        parameter_fields = {
            "alquileres": "tope_alquileres", "energia": "tope_energia",
            "superficie": "tope_superficie", "precio_unitario_maximo": "precio_unitario_maximo",
        }
        controls = {}
        for field, limit_field in parameter_fields.items():
            actual = float(values.get(field, 0) or 0)
            parameter_limit = float(category_row[limit_field] or 0) if category_row else 0.0
            controls[field] = {
                "actual": actual, "limite": parameter_limit,
                "diferencia": parameter_limit - actual if parameter_limit else 0.0,
                "estado": "Superado" if parameter_limit and actual > parameter_limit else "OK",
            }
            if controls[field]["estado"] == "Superado" and status == "OK":
                status = f"Supera {field.replace('_', ' ')}"
        end = date.today()
        start_month = end.year * 12 + end.month - 12
        start_year, month_zero = divmod(start_month, 12)
        return {
            "cliente": dashboard["client"]["nombre_razon_social"],
            "actividad_fiscal": dashboard["client"].get("actividad_fiscal", ""),
            "denominacion": dashboard["client"].get("denominacion", ""),
            "categoria_actual": current, "categoria_sugerida": suggested,
            "periodo_desde": f"{start_year}-{month_zero + 1:02d}",
            "periodo_hasta": end.strftime("%Y-%m"), "ventas": revenue,
            "limite_categoria": limit, "limite_maximo": maximum,
            "diferencia_tope": limit - revenue, "diferencia_maximo": maximum - revenue,
            "porcentaje_utilizado": utilization, "controles_parametros": controls,
            "estado": status,
        }

    def save(self, client_id: int, values: dict) -> int:
        calculation = self.calculate(client_id, values)
        return self.database.execute(
            """
            INSERT INTO recategorizaciones_monotributo(
                cliente_id, periodo_desde, periodo_hasta, ventas_ultimos_12_meses,
                categoria_actual, categoria_sugerida, diferencia_tope, diferencia_categoria,
                estado, alquileres, energia, superficie, precio_unitario_maximo, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id, calculation["periodo_desde"], calculation["periodo_hasta"],
                calculation["ventas"], calculation["categoria_actual"],
                calculation["categoria_sugerida"], calculation["diferencia_tope"],
                calculation["diferencia_maximo"], calculation["estado"],
                float(values.get("alquileres", 0)), float(values.get("energia", 0)),
                float(values.get("superficie", 0)), float(values.get("precio_unitario_maximo", 0)),
                values.get("observaciones", ""),
            ),
        )
