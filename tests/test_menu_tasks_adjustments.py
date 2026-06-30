from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from database import Database, initialize_database
from database.seed import seed_reference_data
from models import Client, FiscalProfile, MonotributoProfile
from services import (
    AdministrativeService,
    ClientService,
    ConfigService,
    DashboardService,
    LedgerService,
    ReportService,
    VoucherService,
)


class MenuTasksAdjustmentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = Database(self.root / "test.db")
        initialize_database(self.database)
        seed_reference_data(self.database)
        self.client_id = ClientService(self.database).save(
            Client("Cliente Consolidado", "20345678901", rubro="Servicios"),
            FiscalProfile(regimen_principal="responsable_inscripto"),
            MonotributoProfile(),
        )
        self.ledger = LedgerService(self.database)
        self.admin = AdministrativeService(self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_schema_supports_completion_and_collection_details(self) -> None:
        task_columns = {row["name"] for row in self.database.query("PRAGMA table_info(tareas)")}
        due_columns = {row["name"] for row in self.database.query("PRAGMA table_info(vencimientos)")}
        fee_columns = {row["name"] for row in self.database.query("PRAGMA table_info(honorarios)")}
        self.assertTrue({"medio", "documentacion_vinculada", "proximo_paso", "fecha_cumplimiento"} <= task_columns)
        self.assertIn("fecha_cumplimiento", due_columns)
        self.assertTrue({"comprobante_emitido", "tipo_comprobante", "condiciones_presupuesto"} <= fee_columns)

    def test_general_screens_include_records_created_inside_ledger(self) -> None:
        self.ledger.save_record(self.client_id, "eventos", {
            "fecha": "01/06/2026", "area": "ARCA", "tipo_evento": "Presentación",
            "descripcion": "Presentar IVA", "estado": "Pendiente", "prioridad": "Alta",
            "fecha_vencimiento": "15/06/2026", "medio": "Web",
            "documentacion_vinculada": "Libro IVA", "proximo_paso": "Enviar acuse",
        })
        self.ledger.save_record(self.client_id, "vencimientos_legajo", {
            "organismo": "ARCA", "impuesto_tramite": "IVA", "periodo": "05/2026",
            "fecha_vencimiento": "20/06/2026", "tipo": "Presentación", "estado": "Pendiente",
        })
        self.ledger.save_record(self.client_id, "pagos", {
            "fecha_emision": "01/06/2026", "periodo": "06/2026", "concepto": "Abono mensual",
            "importe_facturado": "100000", "importe_cobrado": "0", "saldo_pendiente": "100000",
            "estado_pago": "Pendiente", "fecha_vencimiento": "10/06/2026",
        })
        task = next(row for row in self.admin.list("tareas") if row["titulo"] == "Presentación")
        due = next(row for row in self.admin.list("vencimientos") if row["impuesto"] == "IVA")
        fee = next(row for row in self.admin.list("honorarios") if row["servicio"] == "Abono mensual")
        self.assertGreater(task["id"], self.admin.GENERIC_OFFSET)
        self.admin.update_status("tareas", task["id"], "Cumplimentada", "2026-06-12")
        self.admin.update_status("vencimientos", due["id"], "Pagado", "2026-06-18")
        self.admin.update_status("honorarios", fee["id"], "Cobro parcial", "2026-06-08", 40000)
        self.assertEqual(self.admin.get("tareas", task["id"])["fecha_cumplimiento"], "2026-06-12")
        self.assertEqual(self.admin.get("vencimientos", due["id"])["fecha_pago"], "2026-06-18")
        updated_fee = self.admin.get("honorarios", fee["id"])
        self.assertEqual(updated_fee["estado"], "Cobro parcial")
        self.assertEqual(updated_fee["saldo_pendiente"], 60000)

    def test_task_report_has_all_public_fields_and_exports_pdf(self) -> None:
        self.ledger.save_record(self.client_id, "eventos", {
            "fecha": "01/06/2026", "area": "Contable", "tipo_evento": "Control",
            "descripcion": "Control mensual", "estado": "En proceso", "prioridad": "Media",
            "fecha_vencimiento": "30/06/2026", "medio": "Email", "proximo_paso": "Revisar",
        })
        config = ConfigService(self.database)
        reports = ReportService(VoucherService(self.database, config))
        xlsx = self.root / "tareas.xlsx"
        pdf = self.root / "tareas.pdf"
        reports.export_named("tareas", xlsx, self.client_id, "01/06/2026", "30/06/2026", "", "ARCA + Mercado Libre", "", "", "Todos", "Contable", "Control", "Media")
        reports.export_named_pdf("tareas", pdf, self.client_id, "01/06/2026", "30/06/2026", "", "ARCA + Mercado Libre", "", "", "Todos", "Contable", "Control", "Media")
        workbook = load_workbook(xlsx)
        headers = [cell.value for cell in workbook["Tareas"][1]]
        workbook.close()
        self.assertIn("Cliente", headers)
        self.assertIn("CUIT / CUIL", headers)
        self.assertIn("Próximo paso", headers)
        self.assertNotIn("id", {str(value).casefold() for value in headers})
        self.assertNotIn("responsable", {str(value).casefold() for value in headers})
        self.assertGreater(pdf.stat().st_size, 1000)

    def test_dashboard_never_returns_empty_alert_cards(self) -> None:
        alerts = DashboardService(self.database).active_alerts_summary()
        self.assertTrue(all(alert["cantidad"] > 0 for alert in alerts))


if __name__ == "__main__":
    unittest.main()
