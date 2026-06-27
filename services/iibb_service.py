from __future__ import annotations

from database import Database

from .config_service import ConfigService


IIBB_REGIMES = (
    "Régimen simplificado",
    "Régimen general/local",
    "Convenio Multilateral",
    "ARBA - REG SIMP",
    "ARBA REG GENERAL",
    "AGIP REG SIMP",
    "AGIP REG GENERAL",
    "CONVENIO MULTILATERAL",
)


class IibbService:
    def __init__(self, database: Database, config: ConfigService) -> None:
        self.database = database
        self.config = config

    def get_profile(self, client_id: int) -> dict:
        row = self.database.query_one(
            "SELECT * FROM ingresos_brutos_cliente WHERE cliente_id = ?", (client_id,)
        )
        return dict(row) if row else {
            "cliente_id": client_id,
            "regimen_principal": "ARBA - REG SIMP",
            "jurisdiccion": "",
            "actividad": "",
            "alicuota": self.config.get_float("alicuota_iibb_default", 0.035),
            "fecha_alta": "",
            "fecha_baja": "",
            "estado": "activo",
            "observaciones": "",
        }

    def save_profile(self, client_id: int, data: dict) -> None:
        regime = data.get("regimen_principal", "")
        if regime not in IIBB_REGIMES:
            raise ValueError("El régimen de Ingresos Brutos no es válido.")
        rate = float(data.get("alicuota", 0))
        if rate < 0:
            raise ValueError("La alícuota no puede ser negativa.")
        self.database.execute(
            """
            INSERT INTO ingresos_brutos_cliente(
                cliente_id, regimen_principal, alicuota, fecha_alta,
                fecha_baja, estado, observaciones, jurisdiccion, actividad
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cliente_id) DO UPDATE SET
                regimen_principal=excluded.regimen_principal,
                alicuota=excluded.alicuota, fecha_alta=excluded.fecha_alta,
                fecha_baja=excluded.fecha_baja, estado=excluded.estado,
                observaciones=excluded.observaciones,
                jurisdiccion=excluded.jurisdiccion, actividad=excluded.actividad
            """,
            (
                client_id,
                regime,
                rate,
                data.get("fecha_alta") or None,
                data.get("fecha_baja") or None,
                data.get("estado", "activo"),
                data.get("observaciones", ""),
                data.get("jurisdiccion", ""),
                data.get("actividad", ""),
            ),
        )

    def calculate_and_save(
        self,
        client_id: int,
        period: str,
        retentions: float = 0,
        perceptions: float = 0,
        prior_balance: float = 0,
        fixed_amount: float = 0,
        observations: str = "",
        presentation_status: str = "pendiente",
        payment_status: str = "pendiente",
        due_date: str = "",
    ) -> dict:
        profile = self.get_profile(client_id)
        row = self.database.query_one(
            """
            SELECT COALESCE(SUM(importe_neto_fiscal), 0) AS base
            FROM comprobantes_ventas WHERE cliente_id = ? AND periodo_fiscal = ?
            """,
            (client_id, period),
        )
        base = max(float(row["base"] or 0), 0)
        simplified = "simp" in profile["regimen_principal"].casefold()
        determined = fixed_amount if simplified and fixed_amount else base * float(profile["alicuota"])
        payable = max(determined - retentions - perceptions - prior_balance, 0)
        self.database.execute(
            """
            INSERT INTO iibb_monotributo(
                cliente_id, periodo, regimen_principal, base_imponible, alicuota,
                impuesto_determinado, retenciones, percepciones, saldo_favor_anterior,
                saldo_pagar, importe_fijo, observaciones
                , estado_presentacion, estado_pago, fecha_vencimiento
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cliente_id, periodo) DO UPDATE SET
                regimen_principal=excluded.regimen_principal,
                base_imponible=excluded.base_imponible, alicuota=excluded.alicuota,
                impuesto_determinado=excluded.impuesto_determinado,
                retenciones=excluded.retenciones, percepciones=excluded.percepciones,
                saldo_favor_anterior=excluded.saldo_favor_anterior,
                saldo_pagar=excluded.saldo_pagar, importe_fijo=excluded.importe_fijo,
                observaciones=excluded.observaciones,
                estado_presentacion=excluded.estado_presentacion,
                estado_pago=excluded.estado_pago,
                fecha_vencimiento=excluded.fecha_vencimiento
            """,
            (
                client_id, period, profile["regimen_principal"], base,
                profile["alicuota"], determined, retentions, perceptions,
                prior_balance, payable, fixed_amount, observations,
                presentation_status, payment_status, due_date or None,
            ),
        )
        return {
            "base": base,
            "determined": determined,
            "payable": payable,
            "regime": profile["regimen_principal"],
        }

    def list_monthly(self, client_id: int) -> list[dict]:
        return [
            dict(row)
            for row in self.database.query(
                "SELECT * FROM iibb_monotributo WHERE cliente_id = ? ORDER BY periodo DESC",
                (client_id,),
            )
        ]

    def add_convenio_jurisdiction(
        self, client_id: int, period: str, jurisdiction: str,
        coefficient: float, rate: float, observations: str = ""
    ) -> int:
        base_row = self.database.query_one(
            "SELECT COALESCE(SUM(importe_neto_fiscal),0) base FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=?",
            (client_id, period),
        )
        assigned = max(float(base_row["base"] or 0), 0) * coefficient
        return self.database.execute(
            """INSERT INTO iibb_convenio_jurisdicciones(
                cliente_id,periodo,jurisdiccion,coeficiente,base_asignada,
                alicuota,impuesto_determinado,observaciones
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (client_id,period,jurisdiction,coefficient,assigned,rate,assigned*rate,observations),
        )

    def list_convenio(self, client_id: int, period: str) -> list[dict]:
        return [dict(row) for row in self.database.query(
            "SELECT * FROM iibb_convenio_jurisdicciones WHERE cliente_id=? AND periodo=? ORDER BY jurisdiccion",
            (client_id,period),
        )]
