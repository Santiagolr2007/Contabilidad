from __future__ import annotations

from datetime import date

from database import Database
from .config_service import ConfigService
from .monotributo_service import MonotributoService
from .voucher_service import VoucherService


class AlertService:
    AUTO_TYPES = (
        "concentracion_ventas", "concentracion_compras", "compras_altas",
        "limite_categoria", "limite_maximo", "recategorizacion",
        "muchas_facturas_dia", "muchas_facturas_cliente", "falta_iibb",
        "falta_recategorizacion", "falta_pago_monotributo", "venta_usd",
        "compra_usd", "venta_significativa", "compra_significativa",
        "nota_credito_significativa",
    )

    def __init__(self, database: Database, config: ConfigService, vouchers: VoucherService, mono: MonotributoService) -> None:
        self.database=database; self.config=config; self.vouchers=vouchers; self.mono=mono

    def refresh(self, client_id: int) -> int:
        period=date.today().strftime("%Y-%m"); placeholders=",".join("?" for _ in self.AUTO_TYPES)
        self.database.execute(f"DELETE FROM alertas_fiscales WHERE cliente_id=? AND tipo_alerta IN ({placeholders})",(client_id,*self.AUTO_TYPES))
        alerts=[]; concentration=self.config.get_float("concentracion_porcentaje",.30)
        for kind,alert_type in (("ventas","concentracion_ventas"),("compras","concentracion_compras")):
            ranking=self.vouchers.ranking(kind,client_id,1)
            if ranking and ranking[0]["porcentaje"]>concentration:
                alerts.append((alert_type,f"{ranking[0]['contraparte_nombre']} concentra {ranking[0]['porcentaje']*100:.1f}% de {kind}.",ranking[0]["total"],"media"))
        sales=self.vouchers.stats("ventas",client_id); purchases=self.vouchers.stats("compras",client_id)
        if sales.get("mes",0)>0 and purchases.get("mes",0)/sales["mes"]>=self.config.get_float("compras_ventas_alerta",.8):alerts.append(("compras_altas","Las compras del mes son altas respecto de las ventas.",purchases["mes"],"media"))
        mono_profile = self.database.query_one(
            "SELECT id FROM monotributo_cliente WHERE cliente_id = ?", (client_id,)
        )
        dashboard = self.mono.dashboard(client_id) if mono_profile else None
        revenue=sales.get("ultimos_12",0)
        if dashboard:
            limit=dashboard["category_limit"]
            if limit and revenue>=limit*self.config.get_float("monotributo_alerta_porcentaje",.8):alerts.append(("limite_categoria","Ventas cercanas al límite de categoría.",revenue,"alta"))
            if dashboard["suggested_category"]!=dashboard["client"].get("categoria_actual"):alerts.append(("recategorizacion","La categoría sugerida difiere de la actual.",revenue,"alta"))
            maximum=self.database.query_one("SELECT MAX(tope_ingresos) tope FROM categorias_monotributo")
            if maximum and revenue>=float(maximum["tope"] or 0)*.9:alerts.append(("limite_maximo","Ventas cercanas al límite máximo del monotributo.",revenue,"alta"))
        day=self.database.query_one("SELECT fecha,COUNT(*) cantidad FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=? GROUP BY fecha ORDER BY cantidad DESC LIMIT 1",(client_id,period))
        if day and day["cantidad"]>=self.config.get_float("muchas_facturas_dia",10):alerts.append(("muchas_facturas_dia",f"Se emitieron {day['cantidad']} comprobantes el {day['fecha']}.",0,"media"))
        counter=self.database.query_one("SELECT contraparte_nombre,COUNT(*) cantidad FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=? GROUP BY contraparte_nombre ORDER BY cantidad DESC LIMIT 1",(client_id,period))
        if counter and counter["cantidad"]>=self.config.get_float("muchas_facturas_cliente",10):alerts.append(("muchas_facturas_cliente",f"Muchas facturas a {counter['contraparte_nombre']} ({counter['cantidad']}).",0,"media"))
        if not self.database.query_one("SELECT id FROM iibb_monotributo WHERE cliente_id=? AND periodo=?",(client_id,period)):alerts.append(("falta_iibb","Falta cálculo de Ingresos Brutos del período.",0,"media"))
        if dashboard and not self.database.query_one("SELECT id FROM recategorizaciones_monotributo WHERE cliente_id=? ORDER BY creado_en DESC LIMIT 1",(client_id,)):alerts.append(("falta_recategorizacion","Falta registrar análisis de recategorización.",0,"media"))
        if dashboard and dashboard["client"].get("estado_pago_mensual") not in ("pagado","al día"):alerts.append(("falta_pago_monotributo","Falta confirmar pago mensual de monotributo.",0,"media"))
        threshold = self.config.get_float("monto_comprobante_significativo", 500_000)
        for kind, table, label in (
            ("venta", "comprobantes_ventas", "venta"),
            ("compra", "comprobantes_compras", "compra"),
        ):
            rows = self.database.query(
                f"""
                SELECT tipo_comprobante, moneda, importe_pesos, periodo_fiscal
                FROM {table} WHERE cliente_id = ?
                AND (moneda <> 'ARS' OR ABS(importe_pesos) >= ?)
                """,
                (client_id, threshold),
            )
            for voucher in rows:
                if voucher["moneda"] != "ARS":
                    alerts.append((
                        f"{kind}_usd",
                        f"Comprobante de {label} en {voucher['moneda']}.",
                        voucher["importe_pesos"],
                        "media",
                    ))
                if abs(float(voucher["importe_pesos"] or 0)) >= threshold:
                    credit = "crédito" in voucher["tipo_comprobante"].casefold()
                    alerts.append((
                        "nota_credito_significativa" if credit else f"{kind}_significativa",
                        f"Comprobante de {label} supera el monto significativo.",
                        voucher["importe_pesos"],
                        "alta",
                    ))
        with self.database.connection() as connection:
            connection.executemany("INSERT INTO alertas_fiscales(cliente_id,periodo,tipo_alerta,descripcion,importe_relacionado,gravedad,estado) VALUES (?,?,?,?,?,?,'pendiente')",[(client_id,period,*row) for row in alerts])
        return len(alerts)
