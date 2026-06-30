from __future__ import annotations

from datetime import date, timedelta

from database import Database
from .ledger_service import LedgerService


class DashboardService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def general_metrics(self) -> dict:
        period = date.today().strftime("%Y-%m")
        week_end = (date.today() + timedelta(days=7)).isoformat()
        row = self.database.query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM clientes) AS total_clientes,
                (SELECT COUNT(*) FROM clientes WHERE estado = 'activo') AS clientes_activos,
                (SELECT COUNT(DISTINCT c.id) FROM clientes c
                 LEFT JOIN monotributo_cliente m ON c.id = m.cliente_id
                 LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
                 WHERE c.estado = 'activo' AND (m.estado = 'activo' OR LOWER(COALESCE(d.regimen_principal,'')) LIKE '%mono%')) AS monotributistas,
                (SELECT COUNT(DISTINCT c.id) FROM clientes c
                 LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
                 LEFT JOIN cliente_obligaciones co ON co.cliente_id=c.id
                 LEFT JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
                 WHERE c.estado='activo' AND (
                    LOWER(COALESCE(d.regimen_principal,'')) LIKE '%responsable%inscript%'
                    OR LOWER(COALESCE(d.condicion_iva,'')) LIKE '%responsable%inscript%'
                    OR UPPER(COALESCE(o.codigo,''))='IVA')) AS responsables_inscriptos,
                (SELECT COUNT(*) FROM clientes WHERE estado='activo' AND tipo_persona='sociedad') AS sociedades,
                (SELECT COUNT(DISTINCT c.id) FROM clientes c LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
                 LEFT JOIN cliente_obligaciones co ON co.cliente_id=c.id LEFT JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
                 WHERE c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%bienes%' OR UPPER(COALESCE(o.codigo,''))='BIENES')) AS bienes_personales,
                (SELECT COUNT(DISTINCT c.id) FROM clientes c LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
                 LEFT JOIN cliente_obligaciones co ON co.cliente_id=c.id LEFT JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
                 WHERE c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%ganancia%' OR UPPER(COALESCE(o.codigo,''))='GANANCIAS')) AS ganancias,
                (SELECT COUNT(DISTINCT c.id) FROM clientes c LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
                 LEFT JOIN cliente_obligaciones co ON co.cliente_id=c.id LEFT JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
                 WHERE c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%casa%particular%' OR LOWER(COALESCE(o.nombre,'')) LIKE '%casa%particular%')) AS casas_particulares,
                (SELECT COALESCE(SUM(importe_neto_fiscal), 0) FROM comprobantes_ventas
                 WHERE periodo_fiscal = ?) AS ventas_mes,
                (SELECT COALESCE(SUM(importe_neto_fiscal), 0) FROM comprobantes_compras
                 WHERE periodo_fiscal = ?) AS compras_mes,
                (SELECT COUNT(*) FROM alertas_fiscales WHERE estado IN ('activa','pendiente')) AS alertas_activas,
                (SELECT COUNT(*) FROM vencimientos WHERE estado = 'pendiente'
                 AND fecha_vencimiento BETWEEN DATE('now') AND ?) AS vencimientos_semana
            """,
            (period, period, week_end),
        )
        return dict(row) if row else {}

    def clients_by_category(self, category: str) -> list[dict]:
        conditions = {
            "activos": "c.estado='activo'",
            "monotributistas": "c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%mono%' OR m.cliente_id IS NOT NULL)",
            "responsables": "c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%responsable%inscript%' OR LOWER(COALESCE(d.condicion_iva,'')) LIKE '%responsable%inscript%' OR UPPER(COALESCE(o.codigo,''))='IVA')",
            "bienes": "c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%bienes%' OR UPPER(COALESCE(o.codigo,''))='BIENES')",
            "ganancias": "c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%ganancia%' OR UPPER(COALESCE(o.codigo,''))='GANANCIAS')",
            "casas": "c.estado='activo' AND (LOWER(COALESCE(d.regimen_principal,'')) LIKE '%casa%particular%' OR LOWER(COALESCE(o.nombre,'')) LIKE '%casa%particular%')",
        }
        where = conditions.get(category, "c.estado='activo'")
        rows = self.database.query(
            f"""SELECT c.id AS cliente_id,c.nombre_razon_social,c.cuit_cuil,c.tipo_persona,
                    COALESCE(d.regimen_principal,'sin_definir') condicion_fiscal,
                    c.estado,GROUP_CONCAT(DISTINCT o.nombre) impuestos,
                    COALESCE(c.actividad,'') actividad
                FROM clientes c
                LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
                LEFT JOIN monotributo_cliente m ON m.cliente_id=c.id AND m.estado='activo'
                LEFT JOIN cliente_obligaciones co ON co.cliente_id=c.id AND co.estado='activa'
                LEFT JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
                WHERE {where}
                GROUP BY c.id ORDER BY c.nombre_razon_social COLLATE NOCASE"""
        )
        ledger = LedgerService(self.database)
        result = []
        for source in rows:
            item = dict(source)
            summary = ledger.summary(int(item["cliente_id"]))
            item.update({
                "tipo_cliente": summary["tipo_cliente"],
                "servicio_contratado": summary["servicio_contratado"],
                "responsable_interno": summary["responsable_interno"],
                "riesgo_general": summary["riesgo_general"],
                "proximo_vencimiento": summary["proximo_vencimiento"],
            })
            result.append(item)
        return result

    def upcoming(self, days: int = 30, overdue: bool = False) -> list[dict]:
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=days)).isoformat()
        comparator = "v.fecha_vencimiento < ?" if overdue else "v.fecha_vencimiento BETWEEN ? AND ?"
        params = (today,) if overdue else (today, end)
        rows = self.database.query(
            f"""SELECT v.id,c.id cliente_id,c.nombre_razon_social cliente,c.cuit_cuil,
                    v.impuesto,v.organismo,v.periodo,v.fecha_vencimiento,
                    v.tipo_vencimiento,v.estado,v.responsable,v.observaciones
                FROM vencimientos v JOIN clientes c ON c.id=v.cliente_id
                WHERE v.estado NOT IN ('pagado','presentado') AND {comparator}
                ORDER BY v.fecha_vencimiento,c.nombre_razon_social""",
            params,
        )
        return [dict(row) for row in rows]

    def active_alerts_summary(self) -> list[dict]:
        today = date.today().isoformat()
        in_30 = (date.today() + timedelta(days=30)).isoformat()
        queries = (
            ("documentacion_pendiente", "Documentación pendiente", "Media", "SELECT COUNT(DISTINCT cliente_id) n FROM cliente_legajo_registros WHERE seccion='documentacion' AND LOWER(estado) NOT IN ('recibido','aprobado','no corresponde')"),
            ("pagos_vencidos", "Pagos vencidos", "Urgente", f"SELECT COUNT(DISTINCT cliente_id) n FROM (SELECT cliente_id FROM cliente_legajo_registros WHERE seccion='pagos' AND saldo>0 AND vencimiento<'{today}' UNION SELECT cliente_id FROM honorarios WHERE saldo_pendiente>0 AND fecha_vencimiento<'{today}' AND LOWER(estado) NOT IN ('cobrado','bonificado','anulado','no corresponde'))"),
            ("pagos_pendientes", "Pagos pendientes", "Media", "SELECT COUNT(DISTINCT cliente_id) n FROM (SELECT cliente_id FROM cliente_legajo_registros WHERE seccion='pagos' AND saldo>0 UNION SELECT cliente_id FROM honorarios WHERE saldo_pendiente>0 AND LOWER(estado) NOT IN ('cobrado','bonificado','anulado','no corresponde'))"),
            ("vencimientos_vencidos", "Vencimientos vencidos", "Urgente", f"SELECT COUNT(DISTINCT cliente_id) n FROM vencimientos WHERE estado NOT IN ('pagado','presentado') AND fecha_vencimiento<'{today}'"),
            ("vencimientos_proximos", "Vencimientos próximos", "Alta", f"SELECT COUNT(DISTINCT cliente_id) n FROM vencimientos WHERE estado NOT IN ('pagado','presentado') AND fecha_vencimiento BETWEEN '{today}' AND '{in_30}'"),
            ("riesgo_alto", "Riesgo alto", "Alta", "SELECT COUNT(DISTINCT cliente_id) n FROM cliente_legajo_registros WHERE seccion='riesgos' AND datos_json LIKE '%\"Alto\"%'"),
            ("riesgo_urgente", "Riesgo urgente", "Urgente", "SELECT COUNT(DISTINCT cliente_id) n FROM cliente_legajo_registros WHERE seccion='riesgos' AND datos_json LIKE '%\"Urgente\"%'"),
            ("accesos_pendientes", "Accesos pendientes o bloqueados", "Alta", "SELECT COUNT(DISTINCT cliente_id) n FROM cliente_legajo_registros WHERE seccion='documentacion' AND datos_json LIKE '%\"tipo_registro\": \"Acceso\"%' AND (datos_json LIKE '%Pendiente%' OR datos_json LIKE '%Bloqueado%')"),
            ("tareas_pendientes", "Tareas pendientes", "Media", "SELECT COUNT(DISTINCT cliente_id) n FROM tareas WHERE cliente_id IS NOT NULL AND LOWER(estado) NOT IN ('finalizado','archivado','cobrado','cumplimentada','cancelada','no corresponde')"),
            ("tareas_vencidas", "Tareas vencidas", "Urgente", f"SELECT COUNT(DISTINCT cliente_id) n FROM tareas WHERE cliente_id IS NOT NULL AND LOWER(estado) NOT IN ('finalizado','archivado','cobrado','cumplimentada','cancelada','no corresponde') AND fecha_vencimiento<'{today}'"),
            ("obligaciones_pendientes", "Obligaciones mensuales pendientes", "Alta", "SELECT COUNT(DISTINCT cliente_id) n FROM cliente_legajo_registros WHERE seccion='obligaciones' AND LOWER(estado) NOT IN ('pagado','no corresponde','bonificado')"),
            ("obligaciones_vencidas", "Obligaciones mensuales vencidas", "Urgente", f"SELECT COUNT(DISTINCT cliente_id) n FROM cliente_legajo_registros WHERE seccion='obligaciones' AND LOWER(estado) NOT IN ('pagado','no corresponde','bonificado') AND vencimiento<'{today}'"),
            ("regularizacion", "Clientes en regularización", "Alta", "SELECT COUNT(DISTINCT cliente_id) n FROM cliente_legajo_registros WHERE seccion='datos_complementarios' AND datos_json LIKE '%En regularización%'"),
            ("legajo_incompleto", "Legajos incompletos", "Media", "SELECT COUNT(*) n FROM clientes c WHERE c.estado='activo' AND (COALESCE(c.cuit_cuil,'')='' OR COALESCE(c.actividad,'')='' OR NOT EXISTS (SELECT 1 FROM datos_fiscales_cliente d WHERE d.cliente_id=c.id))"),
        )
        result = []
        for key, label, priority, sql in queries:
            row = self.database.query_one(sql)
            count = int(row["n"] or 0)
            if count:
                result.append({"clave": key, "tipo_alerta": label, "cantidad": count, "prioridad": priority})
        return result

    def alert_clients(self, key: str) -> list[dict]:
        if key == "vencimientos_vencidos":
            ids = {row["cliente_id"] for row in self.upcoming(overdue=True)}
        elif key == "vencimientos_proximos":
            ids = {row["cliente_id"] for row in self.upcoming(30)}
        else:
            clauses = {
                "documentacion_pendiente": "r.seccion='documentacion' AND LOWER(r.estado) NOT IN ('recibido','aprobado','no corresponde')",
                "pagos_vencidos": "r.seccion='pagos' AND r.saldo>0 AND r.vencimiento<DATE('now')",
                "pagos_pendientes": "r.seccion='pagos' AND r.saldo>0",
                "riesgo_alto": "r.seccion='riesgos' AND r.datos_json LIKE '%\"Alto\"%'",
                "riesgo_urgente": "r.seccion='riesgos' AND r.datos_json LIKE '%\"Urgente\"%'",
                "accesos_pendientes": "r.seccion='documentacion' AND r.datos_json LIKE '%\"tipo_registro\": \"Acceso\"%' AND (r.datos_json LIKE '%Pendiente%' OR r.datos_json LIKE '%Bloqueado%')",
                "obligaciones_pendientes": "r.seccion='obligaciones' AND LOWER(r.estado) NOT IN ('pagado','no corresponde','bonificado')",
                "obligaciones_vencidas": "r.seccion='obligaciones' AND LOWER(r.estado) NOT IN ('pagado','no corresponde','bonificado') AND r.vencimiento<DATE('now')",
                "regularizacion": "r.seccion='datos_complementarios' AND r.datos_json LIKE '%En regularización%'",
            }
            if key in ("tareas_pendientes", "tareas_vencidas"):
                date_clause = " AND fecha_vencimiento<DATE('now')" if key == "tareas_vencidas" else ""
                rows = self.database.query("SELECT DISTINCT cliente_id FROM tareas WHERE cliente_id IS NOT NULL AND LOWER(estado) NOT IN ('finalizado','archivado','cobrado','cumplimentada','cancelada','no corresponde')" + date_clause)
                ids = {row["cliente_id"] for row in rows}
            elif key == "legajo_incompleto":
                ids = {row["id"] for row in self.database.query("SELECT id FROM clientes WHERE estado='activo'")}
            else:
                clause = clauses.get(key, "1=0")
                ids = {row["cliente_id"] for row in self.database.query(f"SELECT DISTINCT r.cliente_id FROM cliente_legajo_registros r WHERE {clause}")}
        return [row for row in self.clients_by_category("activos") if row["cliente_id"] in ids]

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
