from __future__ import annotations

from datetime import date

from database import Database

from .config_service import ConfigService
from .voucher_service import VoucherService


class MonotributoService:
    def __init__(
        self,
        database: Database,
        vouchers: VoucherService,
        config: ConfigService,
    ) -> None:
        self.database = database
        self.vouchers = vouchers
        self.config = config

    def list_clients(self) -> list[dict]:
        return [
            dict(row)
            for row in self.database.query(
                """
                SELECT c.id, c.nombre_razon_social, c.cuit_cuil, c.actividad,
                       m.categoria_actual, m.actividad_fiscal, m.denominacion,
                       COALESCE(i.regimen_principal, '') AS regimen_iibb
                FROM clientes c
                JOIN datos_fiscales_cliente df ON df.cliente_id = c.id
                JOIN monotributo_cliente m ON m.cliente_id = c.id
                LEFT JOIN ingresos_brutos_cliente i ON i.cliente_id = c.id
                WHERE c.estado = 'activo' AND df.regimen_principal = 'monotributista'
                ORDER BY c.nombre_razon_social COLLATE NOCASE
                """
            )
        ]

    def suggested_category(self, revenue_12_months: float) -> tuple[str, float, str]:
        today = date.today().isoformat()
        categories = self.database.query(
            """
            SELECT categoria, tope_ingresos FROM categorias_monotributo
            WHERE vigencia_desde <= ? AND (vigencia_hasta IS NULL OR vigencia_hasta >= ?)
            ORDER BY tope_ingresos
            """,
            (today, today),
        )
        if not categories:
            return "Sin tabla", 0, "sin_configuracion"
        for row in categories:
            if revenue_12_months <= float(row["tope_ingresos"]):
                return str(row["categoria"]), float(row["tope_ingresos"]), "ok"
        last = categories[-1]
        return str(last["categoria"]), float(last["tope_ingresos"]), "excedido"

    def dashboard(self, client_id: int) -> dict:
        client = self.database.query_one(
            """
            SELECT c.*, m.categoria_actual,
                   COALESCE(NULLIF(m.actividad_fiscal, ''), m.actividad) AS actividad_fiscal,
                   m.denominacion, m.fecha_alta, m.fecha_baja_monotributo,
                   m.estado_pago_mensual, m.estado_recategorizacion, m.riesgo_exclusion,
                   m.observaciones_fiscales,m.tipo_actividad,m.aporta_sipa,
                   m.aporta_obra_social,m.adherentes_obra_social,m.condicion_especial,
                   COALESCE(i.regimen_principal, '') AS regimen_iibb,
                   COALESCE(i.alicuota, 0) AS alicuota_iibb
            FROM clientes c JOIN monotributo_cliente m ON m.cliente_id = c.id
            LEFT JOIN ingresos_brutos_cliente i ON i.cliente_id = c.id
            WHERE c.id = ?
            """,
            (client_id,),
        )
        if not client:
            raise ValueError(
                "El cliente debe estar definido como monotributista. "
                "Abrí su ficha, seleccioná 'monotributista' como Régimen principal "
                "en la pestaña Regímenes y confirmá los cambios."
            )
        sales = self.vouchers.stats("ventas", client_id)
        purchases = self.vouchers.stats("compras", client_id)
        category, category_limit, category_status = self.suggested_category(
            float(sales.get("ultimos_12", 0))
        )
        counts = self.vouchers.significant_counts(client_id)
        alerts = self.database.query_one(
            "SELECT COUNT(*) AS cantidad FROM alertas_fiscales WHERE cliente_id = ? AND estado IN ('activa','pendiente')",
            (client_id,),
        )
        iibb_rate = float(client["alicuota_iibb"] or self.config.get_float("alicuota_iibb_default", 0.035))
        current_limit_row = self.database.query_one(
            """SELECT tope_ingresos FROM categorias_monotributo WHERE categoria=?
               ORDER BY CASE WHEN estado='Vigente' THEN 0 ELSE 1 END,
                        vigencia_desde DESC LIMIT 1""", (client["categoria_actual"],),
        )
        current_limit = float(current_limit_row["tope_ingresos"] or 0) if current_limit_row else 0.0
        from .monotributo_categories_service import MonotributoCategoriesService
        payment = MonotributoCategoriesService(self.database).client_payment(client_id)
        return {
            "client": dict(client),
            "sales": sales,
            "purchases": purchases,
            "suggested_category": category,
            "category_limit": category_limit,
            "category_status": category_status,
            "current_category_limit": current_limit,
            "current_category_utilization": float(sales.get("ultimos_12", 0)) / current_limit if current_limit else 0,
            "payment": payment,
            "iibb_estimated": float(sales.get("mes", 0)) * iibb_rate,
            "significant": counts["significativos"],
            "usd": counts["usd"],
            "active_alerts": int(alerts["cantidad"] or 0) if alerts else 0,
            "sales_ranking": self.vouchers.ranking("ventas", client_id),
            "purchases_ranking": self.vouchers.ranking("compras", client_id),
            "sales_monthly": self.vouchers.monthly_summary("ventas", client_id),
            "purchases_monthly": self.vouchers.monthly_summary("compras", client_id),
        }
