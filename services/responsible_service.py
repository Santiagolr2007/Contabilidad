from __future__ import annotations

import json
from calendar import monthrange
from datetime import date

from database import Database

from .administrative_service import AdministrativeService
from .config_service import ConfigService
from .ledger_service import LedgerService
from .responsible_profile import RESPONSIBLE_PROFILE_SECTIONS


class ResponsibleService:
    """Consultas consolidadas para la ficha individual de Responsable Inscripto."""

    PROFILE_SECTIONS = RESPONSIBLE_PROFILE_SECTIONS

    def __init__(self, database: Database) -> None:
        self.database = database
        self.config = ConfigService(database)

    def clients(self) -> list[dict]:
        rows = self.database.query(
            """SELECT DISTINCT c.id,c.legajo,c.nombre_razon_social,c.cuit_cuil,
                      COALESCE(NULLIF(c.estado_detalle,''),c.estado) estado,
                      COALESCE(NULLIF(c.actividad,''),c.rubro,'') actividad,
                      COALESCE(d.regimen_principal,'') regimen_principal,
                      COALESCE(d.condicion_iva,'') condicion_iva
               FROM clientes c
               LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
               LEFT JOIN cliente_obligaciones co ON co.cliente_id=c.id AND LOWER(co.estado)='activa'
               LEFT JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
               WHERE c.estado='activo' AND (
                   LOWER(COALESCE(d.regimen_principal,'')) LIKE '%responsable%inscript%'
                   OR LOWER(COALESCE(d.condicion_iva,'')) LIKE '%responsable%inscript%'
                   OR UPPER(COALESCE(o.codigo,''))='IVA'
                   OR LOWER(COALESCE(o.nombre,''))='iva'
                   OR EXISTS (
                       SELECT 1 FROM cliente_legajo_campos cp
                       WHERE cp.cliente_id=c.id
                         AND cp.seccion='responsable_inscripto'
                         AND cp.campo='ri_inscripto'
                         AND LOWER(cp.valor) IN ('sí','si','en trámite')
                   ))
               ORDER BY c.nombre_razon_social COLLATE NOCASE"""
        )
        return [dict(row) for row in rows]

    def profile(self, client_id: int) -> dict[str, str]:
        return {
            str(row["campo"]): str(row["valor"] or "")
            for row in self.database.query(
                """SELECT campo,valor FROM cliente_legajo_campos
                   WHERE cliente_id=? AND seccion='responsable_inscripto'""",
                (client_id,),
            )
        }

    def save_profile(self, client_id: int, values: dict[str, str]) -> None:
        valid = {
            key
            for _title, fields in self.PROFILE_SECTIONS
            for key, _label, _kind in fields
        }
        with self.database.connection() as connection:
            for key, value in values.items():
                if key not in valid:
                    continue
                connection.execute(
                    """INSERT INTO cliente_legajo_campos(cliente_id,seccion,campo,valor)
                       VALUES(?,'responsable_inscripto',?,?)
                       ON CONFLICT(cliente_id,seccion,campo) DO UPDATE SET
                       valor=excluded.valor,actualizado_en=CURRENT_TIMESTAMP""",
                    (client_id, key, str(value or "").strip()),
                )

    @staticmethod
    def _bounds(year: int, month: int) -> tuple[str, str, str]:
        end = date(year, month, monthrange(year, month)[1])
        index = year * 12 + month - 1 - 11
        start_year, start_zero_month = divmod(index, 12)
        start = date(start_year, start_zero_month + 1, 1)
        return f"{year:04d}-{month:02d}", start.isoformat(), end.isoformat()

    def _sum(self, sql: str, params: tuple) -> float:
        row = self.database.query_one(sql, params)
        return float(row["total"] or 0) if row else 0.0

    def _metric_for_period(self, client_id: int, period: str) -> dict:
        sales_arca = self._sum("SELECT SUM(importe_neto_fiscal) total FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=?", (client_id, period))
        purchases_arca = self._sum("SELECT SUM(importe_neto_fiscal) total FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal=?", (client_id, period))
        sales_ml = self._sum("SELECT SUM(importe_neto) total FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo=? AND LOWER(tipo_operacion) IN ('venta','nota de crédito','devolución','anulación')", (client_id, period))
        purchases_ml = self._sum("SELECT SUM(importe_neto) total FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo=? AND LOWER(tipo_operacion) LIKE 'compra%'", (client_id, period))
        sales = sales_arca + sales_ml; purchases = purchases_arca + purchases_ml
        return {
            "periodo": period, "ventas_arca": sales_arca, "ventas_mercado_libre": sales_ml,
            "ventas": sales, "compras_arca": purchases_arca,
            "compras_mercado_libre": purchases_ml, "compras": purchases,
            "iva_debito": sales * .21, "iva_credito": purchases * .21,
            "saldo_iva": sales * .21 - purchases * .21,
        }

    def dashboard(self, client_id: int, year: int, month: int) -> dict:
        client = next((row for row in self.clients() if int(row["id"]) == int(client_id)), None)
        if not client: raise ValueError("El cliente no es Responsable Inscripto o ya no está activo.")
        period, start_12, end = self._bounds(year, month)
        current = self._metric_for_period(client_id, period)
        sales_year = self._sum("SELECT SUM(importe_neto_fiscal) total FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal LIKE ?", (client_id, f"{year:04d}-%")) + self._sum("SELECT SUM(importe_neto) total FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo LIKE ? AND LOWER(tipo_operacion) IN ('venta','nota de crédito','devolución','anulación')", (client_id, f"{year:04d}-%"))
        purchases_year = self._sum("SELECT SUM(importe_neto_fiscal) total FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal LIKE ?", (client_id, f"{year:04d}-%")) + self._sum("SELECT SUM(importe_neto) total FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo LIKE ? AND LOWER(tipo_operacion) LIKE 'compra%'", (client_id, f"{year:04d}-%"))
        sales_12 = self._sum("SELECT SUM(importe_neto_fiscal) total FROM comprobantes_ventas WHERE cliente_id=? AND fecha BETWEEN ? AND ?", (client_id, start_12, end)) + self._sum("SELECT SUM(importe_neto) total FROM operaciones_mercado_libre WHERE cliente_id=? AND fecha BETWEEN ? AND ? AND LOWER(tipo_operacion) IN ('venta','nota de crédito','devolución','anulación')", (client_id, start_12, end))
        purchases_12 = self._sum("SELECT SUM(importe_neto_fiscal) total FROM comprobantes_compras WHERE cliente_id=? AND fecha BETWEEN ? AND ?", (client_id, start_12, end)) + self._sum("SELECT SUM(importe_neto) total FROM operaciones_mercado_libre WHERE cliente_id=? AND fecha BETWEEN ? AND ? AND LOWER(tipo_operacion) LIKE 'compra%'", (client_id, start_12, end))
        retentions = self._sum("SELECT SUM(retenciones) total FROM movimientos_mercado_pago WHERE cliente_id=? AND periodo=?", (client_id, period)) + self._sum("SELECT SUM(retenciones) total FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo=?", (client_id, period))
        perceptions = self._sum("SELECT SUM(percepciones) total FROM movimientos_mercado_pago WHERE cliente_id=? AND periodo=?", (client_id, period)) + self._sum("SELECT SUM(percepciones) total FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo=?", (client_id, period))
        iibb = self.database.query_one("SELECT impuesto_determinado,retenciones,percepciones FROM iibb_monotributo WHERE cliente_id=? AND periodo=?", (client_id, period))
        if iibb:
            iibb_estimated = float(iibb["impuesto_determinado"] or 0)
            retentions += float(iibb["retenciones"] or 0); perceptions += float(iibb["percepciones"] or 0)
        else:
            profile = self.database.query_one("SELECT alicuota FROM ingresos_brutos_cliente WHERE cliente_id=?", (client_id,))
            iibb_estimated = current["ventas"] * float(profile["alicuota"] or 0) if profile else 0.0
        threshold = self.config.get_client_float(client_id, "monto_comprobante_significativo", 500_000)
        significant = sum(int(row["n"] or 0) for row in (
            self.database.query_one("SELECT COUNT(*) n FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=? AND ABS(importe_pesos)>=?", (client_id, period, threshold)),
            self.database.query_one("SELECT COUNT(*) n FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal=? AND ABS(importe_pesos)>=?", (client_id, period, threshold)),
            self.database.query_one("SELECT COUNT(*) n FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo=? AND ABS(importe_neto)>=?", (client_id, period, threshold)),
            self.database.query_one("SELECT COUNT(*) n FROM movimientos_mercado_pago WHERE cliente_id=? AND periodo=? AND ABS(importe_neto)>=?", (client_id, period, threshold)),
        ))
        usd = sum(int(row["n"] or 0) for row in (
            self.database.query_one("SELECT COUNT(*) n FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=? AND UPPER(moneda) NOT IN ('ARS','$','PESOS')", (client_id, period)),
            self.database.query_one("SELECT COUNT(*) n FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal=? AND UPPER(moneda) NOT IN ('ARS','$','PESOS')", (client_id, period)),
            self.database.query_one("SELECT COUNT(*) n FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo=? AND UPPER(moneda) NOT IN ('ARS','$','PESOS')", (client_id, period)),
            self.database.query_one("SELECT COUNT(*) n FROM movimientos_mercado_pago WHERE cliente_id=? AND periodo=? AND UPPER(moneda) NOT IN ('ARS','$','PESOS')", (client_id, period)),
        ))
        ledger = LedgerService(self.database).summary(client_id)
        all_due = [row for row in AdministrativeService(self.database).list("vencimientos") if int(row.get("cliente_id") or 0) == client_id and str(row.get("estado", "")).casefold() not in ("pagado", "cumplido", "no corresponde")]
        due = [row for row in all_due if period <= str(row.get("fecha_vencimiento") or "")[:7] <= end[:7]]
        overdue_due = [row for row in all_due if str(row.get("fecha_vencimiento") or "") and str(row.get("fecha_vencimiento")) < date.today().isoformat()]
        active_alerts = self.database.query_one("SELECT COUNT(*) n FROM alertas_fiscales WHERE cliente_id=? AND estado IN ('activa','pendiente')", (client_id,))
        high_alerts = self.database.query_one("SELECT COUNT(*) n FROM alertas_fiscales WHERE cliente_id=? AND estado IN ('activa','pendiente') AND LOWER(gravedad) IN ('alta','urgente')", (client_id,))
        dedicated_docs = self.database.query_one("SELECT COUNT(*) n FROM documentacion WHERE cliente_id=? AND LOWER(estado) NOT IN ('recibida','recibido','aprobada','aprobado','no corresponde')", (client_id,))
        dedicated_fees = self.database.query_one("SELECT COUNT(*) n,COALESCE(SUM(saldo_pendiente),0) total FROM honorarios WHERE cliente_id=? AND saldo_pendiente>0 AND LOWER(estado) NOT IN ('cobrado','cobrado total','bonificado','anulado','no corresponde')", (client_id,))
        overdue_fees = self.database.query_one("SELECT COUNT(*) n FROM honorarios WHERE cliente_id=? AND saldo_pendiente>0 AND fecha_vencimiento<DATE('now') AND LOWER(estado) NOT IN ('cobrado','cobrado total','bonificado','anulado','no corresponde')", (client_id,))
        profile = self.profile(client_id)
        risk = profile.get("ctrl_riesgo") or ledger.get("riesgo_general") or "Bajo"
        if int(high_alerts["n"] or 0) and risk.casefold() not in ("alto", "urgente"): risk = "Revisar"
        fiscal_state = profile.get("ctrl_estado") or ("Con deuda" if ledger.get("pagos_vencidos") or int(overdue_fees["n"] or 0) else ("Con alertas" if int(active_alerts["n"] or 0) else str(client.get("estado") or "Activo").title()))
        return {
            "client": client, "period": period, **current,
            "ventas_anio": sales_year, "compras_anio": purchases_year,
            "ventas_12": sales_12, "compras_12": purchases_12,
            "retenciones": retentions, "percepciones": perceptions,
            "iibb_estimado": iibb_estimated, "significativos": significant,
            "usd": usd, "vencimientos_proximos": len(due), "vencimientos_vencidos": len(overdue_due),
            "documentacion_pendiente": ledger["documentacion_pendiente"] + int(dedicated_docs["n"] or 0),
            "tareas_pendientes": ledger["tareas_pendientes"], "tareas_vencidas": ledger["tareas_vencidas"],
            "pagos_pendientes": ledger["pagos_pendientes"] + int(dedicated_fees["n"] or 0),
            "honorarios_pendientes": round(float(ledger["total_pendiente"] or 0) + float(dedicated_fees["total"] or 0), 2),
            "honorarios_vencidos": bool(ledger["pagos_vencidos"] or int(overdue_fees["n"] or 0)),
            "alertas_activas": int(active_alerts["n"] or 0),
            "riesgo_fiscal": risk, "estado_fiscal": fiscal_state,
        }

    def sales_or_purchases(self, client_id: int, kind: str, year: int) -> list[dict]:
        table = "comprobantes_ventas" if kind == "ventas" else "comprobantes_compras"
        arca = [dict(row) for row in self.database.query(
            f"""SELECT fecha,periodo_fiscal periodo,tipo_comprobante,punto_venta,
                       numero_comprobante,contraparte_nombre contraparte,
                       contraparte_documento documento,moneda,importe_neto_fiscal importe,
                       estado,'ARCA' fuente FROM {table}
                WHERE cliente_id=? AND periodo_fiscal LIKE ? ORDER BY fecha DESC""",
            (client_id, f"{year:04d}-%"),
        )]
        operation = "venta" if kind == "ventas" else "compra"
        ml = [dict(row) for row in self.database.query(
            """SELECT fecha,periodo,tipo_comprobante,'' punto_venta,numero_comprobante,
                      contraparte,contraparte_documento documento,moneda,importe_neto importe,
                      estado,'Mercado Libre' fuente FROM operaciones_mercado_libre
               WHERE cliente_id=? AND periodo LIKE ? AND LOWER(tipo_operacion) LIKE ?
               ORDER BY fecha DESC""",
            (client_id, f"{year:04d}-%", f"{operation}%"),
        )]
        return sorted([*arca, *ml], key=lambda row: str(row.get("fecha") or ""), reverse=True)

    def iva_monthly(self, client_id: int, year: int, month: int) -> list[dict]:
        current = year * 12 + month - 1
        result = []
        for index in range(current - 11, current + 1):
            item_year, zero_month = divmod(index, 12)
            result.append(self._metric_for_period(client_id, f"{item_year:04d}-{zero_month + 1:02d}"))
        return result

    def obligations(self, client_id: int, term: str) -> list[dict]:
        return [dict(row) for row in self.database.query(
            """SELECT o.nombre obligación,o.codigo,o.periodicidad,co.estado,
                      co.fecha_desde,co.fecha_hasta,co.observaciones
               FROM cliente_obligaciones co JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
               WHERE co.cliente_id=? AND (LOWER(o.nombre) LIKE ? OR LOWER(o.codigo) LIKE ?)
               ORDER BY o.nombre""",
            (client_id, f"%{term.casefold()}%", f"%{term.casefold()}%"),
        )]

    def iibb_rows(self, client_id: int, monthly: bool = False) -> list[dict]:
        if monthly:
            return [dict(row) for row in self.database.query("SELECT periodo,base_imponible,alicuota,impuesto_determinado,retenciones,percepciones,saldo_favor_anterior,saldo_pagar,estado_presentacion,estado_pago,fecha_vencimiento,observaciones FROM iibb_monotributo WHERE cliente_id=? ORDER BY periodo DESC", (client_id,))]
        rows = [dict(row) for row in self.database.query("SELECT jurisdiccion,regimen,porcentaje,fecha_alta,estado,observaciones FROM iibb_jurisdicciones_cliente WHERE cliente_id=? ORDER BY jurisdiccion", (client_id,))]
        profile = self.database.query_one("SELECT jurisdiccion,regimen_principal regimen,actividad,alicuota,fecha_alta,fecha_baja,estado,observaciones FROM ingresos_brutos_cliente WHERE cliente_id=?", (client_id,))
        return ([dict(profile)] if profile else []) + rows

    def rankings(self, client_id: int, kind: str, year: int) -> list[dict]:
        key = "contraparte_nombre"; table = "comprobantes_ventas" if kind == "clientes" else "comprobantes_compras"
        arca = self.database.query(f"SELECT {key} nombre,COUNT(*) operaciones,SUM(importe_neto_fiscal) total FROM {table} WHERE cliente_id=? AND periodo_fiscal LIKE ? GROUP BY {key}", (client_id, f"{year:04d}-%"))
        operation = "venta" if kind == "clientes" else "compra"
        ml = self.database.query("SELECT contraparte nombre,COUNT(*) operaciones,SUM(importe_neto) total FROM operaciones_mercado_libre WHERE cliente_id=? AND periodo LIKE ? AND LOWER(tipo_operacion) LIKE ? GROUP BY contraparte", (client_id, f"{year:04d}-%", f"{operation}%"))
        grouped: dict[str, dict] = {}
        for row in (*arca, *ml):
            name = str(row["nombre"] or "Sin identificar")
            item = grouped.setdefault(name, {"nombre": name, "operaciones": 0, "total": 0.0})
            item["operaciones"] += int(row["operaciones"] or 0); item["total"] += float(row["total"] or 0)
        return sorted(grouped.values(), key=lambda item: item["total"], reverse=True)

    def vencimientos(self, client_id: int) -> list[dict]:
        hidden = {"cliente_id", "responsable", "actualizado_en", "_ledger_section"}
        return [{key: value for key, value in row.items() if key not in hidden} for row in AdministrativeService(self.database).list("vencimientos") if int(row.get("cliente_id") or 0) == client_id]

    def alerts(self, client_id: int) -> list[dict]:
        return [dict(row) for row in self.database.query("SELECT periodo,tipo_alerta,descripcion,importe_relacionado,gravedad,estado,fecha_creacion,observaciones FROM alertas_fiscales WHERE cliente_id=? ORDER BY fecha_creacion DESC", (client_id,))]

    def documents(self, client_id: int) -> list[dict]:
        rows = [dict(row) for row in self.database.query("SELECT periodo,tipo_documento documento,estado,fecha_solicitud,fecha_recepcion,observaciones FROM documentacion WHERE cliente_id=? ORDER BY id DESC", (client_id,))]
        for record in self.database.query("SELECT datos_json,estado FROM cliente_legajo_registros WHERE cliente_id=? AND seccion='documentacion' ORDER BY id DESC", (client_id,)):
            data = json.loads(record["datos_json"] or "{}")
            rows.append({"periodo": data.get("periodo", ""), "documento": data.get("documento", data.get("plataforma", "")), "estado": data.get("estado", record["estado"]), "fecha_solicitud": data.get("fecha_solicitud", ""), "fecha_recepcion": data.get("fecha_recepcion", ""), "observaciones": data.get("observaciones", "")})
        return rows
