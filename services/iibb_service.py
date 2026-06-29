from __future__ import annotations

from database import Database
from utils.formatters import normalize_date, normalize_period
from utils.validators import positive_number

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

ARGENTINA_JURISDICTIONS = (
    "Buenos Aires", "CABA", "Catamarca", "Chaco", "Chubut", "Córdoba",
    "Corrientes", "Entre Ríos", "Formosa", "Jujuy", "La Pampa", "La Rioja",
    "Mendoza", "Misiones", "Neuquén", "Río Negro", "Salta", "San Juan",
    "San Luis", "Santa Cruz", "Santa Fe", "Santiago del Estero",
    "Tierra del Fuego", "Tucumán",
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
                normalize_date(data["fecha_alta"]) if data.get("fecha_alta") else None,
                normalize_date(data["fecha_baja"]) if data.get("fecha_baja") else None,
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
        period = normalize_period(period)
        retentions = float(retentions)
        perceptions = float(perceptions)
        prior_balance = float(prior_balance)
        fixed_amount = float(fixed_amount)
        if min(retentions, perceptions, prior_balance, fixed_amount) < 0:
            raise ValueError("Retenciones, percepciones, saldos e importe fijo no pueden ser negativos.")
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
        determined = round(
            fixed_amount if simplified and fixed_amount else base * float(profile["alicuota"]),
            2,
        )
        payable = max(round(determined - retentions - perceptions - prior_balance, 2), 0)
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
                presentation_status, payment_status, normalize_date(due_date) if due_date else None,
            ),
        )
        return {
            "base": base,
            "determined": determined,
            "payable": payable,
            "regime": profile["regimen_principal"],
            "retentions": retentions,
            "fixed_amount": fixed_amount,
        }

    def monthly_detail(self, client_id: int, period: str) -> dict:
        """Detalle de ventas e IIBB calculado para un cliente y período."""
        period = normalize_period(period)
        profile = self.get_profile(client_id)
        rate = float(profile.get("alicuota") or 0)
        rows = [
            dict(row)
            for row in self.database.query(
                """
                SELECT id, fecha, tipo_comprobante, punto_venta,
                       numero_comprobante, contraparte_nombre,
                       contraparte_documento, importe_neto_fiscal AS importe_venta
                FROM comprobantes_ventas
                WHERE cliente_id = ? AND periodo_fiscal = ?
                ORDER BY fecha, punto_venta, numero_comprobante, id
                """,
                (client_id, period),
            )
        ]
        for row in rows:
            row["alicuota"] = rate
            row["impuesto_calculado"] = round(
                float(row["importe_venta"] or 0) * rate, 2
            )
        base = max(sum(float(row["importe_venta"] or 0) for row in rows), 0)
        stored = self.database.query_one(
            "SELECT * FROM iibb_monotributo WHERE cliente_id = ? AND periodo = ?",
            (client_id, period),
        )
        record = dict(stored) if stored else {}
        retentions = float(record.get("retenciones") or 0)
        fixed_amount = float(record.get("importe_fijo") or 0)
        simplified = "simp" in str(profile.get("regimen_principal", "")).casefold()
        determined = fixed_amount if simplified and fixed_amount else round(base * rate, 2)
        payable = max(round(determined - retentions, 2), 0)
        return {
            "client_id": client_id,
            "period": period,
            "profile": profile,
            "rows": rows,
            "base": round(base, 2),
            "rate": rate,
            "determined": determined,
            "retentions": retentions,
            "fixed_amount": fixed_amount,
            "payable": payable,
        }

    def save_fixed_amount(self, client_id: int, period: str, amount: float) -> None:
        period = normalize_period(period)
        amount = float(amount)
        if amount < 0:
            raise ValueError("El importe mensual simplificado no puede ser negativo.")
        detail = self.monthly_detail(client_id, period)
        self.database.execute(
            """
            INSERT INTO iibb_monotributo(
                cliente_id, periodo, regimen_principal, base_imponible, alicuota,
                impuesto_determinado, importe_fijo, saldo_pagar
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cliente_id, periodo) DO UPDATE SET
                regimen_principal = excluded.regimen_principal,
                base_imponible = excluded.base_imponible,
                alicuota = excluded.alicuota,
                impuesto_determinado = excluded.impuesto_determinado,
                importe_fijo = excluded.importe_fijo,
                saldo_pagar = MAX(
                    excluded.impuesto_determinado
                    - iibb_monotributo.retenciones
                    - iibb_monotributo.percepciones
                    - iibb_monotributo.saldo_favor_anterior,
                    0
                )
            """,
            (
                client_id,
                period,
                detail["profile"]["regimen_principal"],
                detail["base"],
                detail["rate"],
                amount if amount > 0 else detail["base"] * detail["rate"],
                amount,
                max((amount if amount > 0 else detail["base"] * detail["rate"]), 0),
            ),
        )

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

    def list_jurisdictions(self, client_id: int) -> list[dict]:
        return [dict(row) for row in self.database.query(
            "SELECT * FROM iibb_jurisdicciones_cliente WHERE cliente_id=? ORDER BY jurisdiccion",
            (client_id,),
        )]

    def save_jurisdiction(self, client_id: int, data: dict) -> int:
        jurisdiction = str(data.get("jurisdiccion") or "").strip()
        if jurisdiction not in ARGENTINA_JURISDICTIONS:
            raise ValueError("Seleccioná una jurisdicción argentina válida.")
        percentage = positive_number(data.get("porcentaje") or 0, "Porcentaje", True)
        if percentage < 0 or percentage > 100:
            raise ValueError("El porcentaje debe estar entre 0,00 y 100,00.")
        return self.database.execute(
            """INSERT INTO iibb_jurisdicciones_cliente(cliente_id,jurisdiccion,porcentaje,regimen,fecha_alta,estado,observaciones)
               VALUES(?,?,?,?,?,?,?) ON CONFLICT(cliente_id,jurisdiccion) DO UPDATE SET
               porcentaje=excluded.porcentaje,regimen=excluded.regimen,fecha_alta=excluded.fecha_alta,
               estado=excluded.estado,observaciones=excluded.observaciones""",
            (client_id,jurisdiction,percentage,data.get("regimen","A revisar"),data.get("fecha_alta") or None,data.get("estado","Activo"),data.get("observaciones","")),
        )

    def delete_jurisdiction(self, client_id: int, jurisdiction: str) -> int:
        with self.database.connection() as connection:
            return int(connection.execute("DELETE FROM iibb_jurisdicciones_cliente WHERE cliente_id=? AND jurisdiccion=?", (client_id,jurisdiction)).rowcount)

    def jurisdiction_total(self, client_id: int) -> float:
        row = self.database.query_one("SELECT COALESCE(SUM(porcentaje),0) total FROM iibb_jurisdicciones_cliente WHERE cliente_id=?", (client_id,))
        return round(float(row["total"] or 0), 2)
