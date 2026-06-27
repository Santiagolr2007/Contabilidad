from __future__ import annotations

from datetime import date, timedelta

from database import Database


class DashboardService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def general_metrics(self) -> dict:
        period = date.today().strftime("%Y-%m")
        week_end = (date.today() + timedelta(days=7)).isoformat()
        row = self.database.query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM clientes WHERE estado = 'activo') AS clientes_activos,
                (SELECT COUNT(*) FROM monotributo_cliente m JOIN clientes c ON c.id = m.cliente_id
                 WHERE c.estado = 'activo' AND m.estado = 'activo') AS monotributistas,
                (SELECT COALESCE(SUM(importe_neto_fiscal), 0) FROM comprobantes_ventas
                 WHERE periodo_fiscal = ?) AS ventas_mes,
                (SELECT COALESCE(SUM(importe_neto_fiscal), 0) FROM comprobantes_compras
                 WHERE periodo_fiscal = ?) AS compras_mes,
                (SELECT COUNT(*) FROM alertas_fiscales WHERE estado IN ('activa','pendiente')) AS alertas_activas,
                (SELECT COUNT(*) FROM vencimientos WHERE estado = 'pendiente'
                 AND fecha_vencimiento <= ?) AS vencimientos_semana
            """,
            (period, period, week_end),
        )
        return dict(row) if row else {}

    def recent_alerts(self, limit: int = 8) -> list[dict]:
        return [
            dict(row)
            for row in self.database.query(
                """
                SELECT a.*, c.nombre_razon_social AS cliente_nombre
                FROM alertas_fiscales a
                JOIN clientes c ON c.id = a.cliente_id
                WHERE a.estado IN ('activa','pendiente')
                ORDER BY CASE a.gravedad WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END,
                         a.fecha_creacion DESC
                LIMIT ?
                """,
                (limit,),
            )
        ]
