from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from database import Database, initialize_database
from database.seed import seed_reference_data
from models import Client, FiscalProfile, MonotributoProfile, Voucher
from services import (
    ClientService,
    AlertService,
    ConfigService,
    ImportService,
    IibbService,
    MonotributoService,
    ReportService,
    VoucherService,
)


class StageOneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name)
        self.database = Database(self.path / "test.db")
        initialize_database(self.database)
        seed_reference_data(self.database)
        self.config = ConfigService(self.database)
        self.clients = ClientService(self.database)
        self.vouchers = VoucherService(self.database, self.config)
        self.mono = MonotributoService(self.database, self.vouchers, self.config)
        self.client_id = self.clients.save(
            Client("Persona de Prueba", "20123456786"),
            FiscalProfile(regimen_principal="monotributista"),
            MonotributoProfile(categoria_actual="A"),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_schema_contains_all_requested_tables(self) -> None:
        rows = self.database.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        names = {row["name"] for row in rows}
        expected = {
            "clientes",
            "datos_fiscales_cliente",
            "obligaciones_fiscales",
            "cliente_obligaciones",
            "monotributo_cliente",
            "comprobantes_ventas",
            "comprobantes_compras",
            "iibb_monotributo",
            "categorias_monotributo",
            "recategorizaciones_monotributo",
            "alertas_fiscales",
            "documentacion",
            "tareas",
            "vencimientos",
            "honorarios",
            "configuracion",
        }
        self.assertTrue(expected.issubset(names))

    def test_client_duplicate_and_logical_deactivation(self) -> None:
        with self.assertRaisesRegex(ValueError, "CUIT/CUIL"):
            self.clients.save(
                Client("Duplicado", "20123456786"), FiscalProfile(), None
            )
        self.clients.deactivate(self.client_id)
        self.assertEqual(self.clients.list_clients(), [])
        self.assertEqual(len(self.clients.list_clients(include_inactive=True)), 1)

    def test_alert_recalculation_does_not_require_monotributo_profile(self) -> None:
        other_id = self.clients.save(
            Client("Cliente sin régimen", "20333444559"),
            FiscalProfile(regimen_principal="sin_definir"),
            None,
        )
        count = AlertService(
            self.database, self.config, self.vouchers, self.mono
        ).refresh(other_id)
        self.assertGreaterEqual(count, 1)

    def test_permanent_client_delete_cascades_to_vouchers(self) -> None:
        period = date.today().strftime("%Y-%m")
        self.vouchers.create(
            "ventas",
            Voucher(
                cliente_id=self.client_id,
                fecha=date.today().isoformat(),
                periodo_fiscal=period,
                tipo_comprobante="Factura C",
                punto_venta="99",
                numero_comprobante="1",
                contraparte_nombre="Comprador",
                importe_original=1000,
            ),
        )
        self.database.execute(
            """
            INSERT INTO alertas_fiscales(
                cliente_id, periodo, tipo_alerta, descripcion, gravedad
            ) VALUES (?, ?, 'prueba', 'Alerta de prueba', 'media')
            """,
            (self.client_id, period),
        )
        deleted = self.clients.delete_permanently(self.client_id)
        self.assertEqual(deleted["ventas"], 1)
        self.assertIsNone(
            self.database.query_one("SELECT id FROM clientes WHERE id = ?", (self.client_id,))
        )
        self.assertEqual(
            self.database.query_one(
                "SELECT COUNT(*) AS n FROM comprobantes_ventas WHERE cliente_id = ?",
                (self.client_id,),
            )["n"],
            0,
        )
        self.assertEqual(
            self.database.query_one(
                "SELECT COUNT(*) AS n FROM alertas_fiscales WHERE cliente_id = ?",
                (self.client_id,),
            )["n"],
            0,
        )

    def test_fiscal_sign_usd_conversion_and_annulled(self) -> None:
        period = date.today().strftime("%Y-%m")
        normal = Voucher(
            cliente_id=self.client_id,
            fecha=date.today().isoformat(),
            periodo_fiscal=period,
            tipo_comprobante="Factura C",
            punto_venta="1",
            numero_comprobante="1",
            contraparte_nombre="Cliente A",
            moneda="USD",
            tipo_cambio=1000,
            importe_original=600,
        )
        credit = Voucher(
            cliente_id=self.client_id,
            fecha=date.today().isoformat(),
            periodo_fiscal=period,
            tipo_comprobante="Nota de Crédito C",
            punto_venta="1",
            numero_comprobante="2",
            contraparte_nombre="Cliente A",
            importe_original=100_000,
        )
        annulled = Voucher(
            cliente_id=self.client_id,
            fecha=date.today().isoformat(),
            periodo_fiscal=period,
            tipo_comprobante="Factura C",
            punto_venta="1",
            numero_comprobante="3",
            contraparte_nombre="Cliente B",
            importe_original=200_000,
            estado="anulado",
        )
        self.vouchers.create("ventas", normal)
        self.vouchers.create("ventas", credit)
        self.vouchers.create("ventas", annulled)
        rows = self.vouchers.list("ventas", self.client_id, period)
        by_number = {row["numero_comprobante"]: row for row in rows}
        self.assertEqual(by_number["1"]["importe_neto_fiscal"], 600_000)
        self.assertEqual(by_number["2"]["importe_neto_fiscal"], -100_000)
        self.assertEqual(by_number["3"]["importe_neto_fiscal"], 0)
        self.assertEqual(self.vouchers.stats("ventas", self.client_id)["mes"], 500_000)
        alert_count = self.database.query_one(
            "SELECT COUNT(*) AS n FROM alertas_fiscales WHERE cliente_id = ?",
            (self.client_id,),
        )
        self.assertEqual(alert_count["n"], 2)
        deleted = self.vouchers.delete_selected(
            "ventas",
            self.client_id,
            [by_number["1"]["id"], by_number["2"]["id"]],
        )
        self.assertEqual(deleted, 2)
        remaining = self.vouchers.list("ventas", self.client_id, period)
        self.assertEqual([row["numero_comprobante"] for row in remaining], ["3"])

    def test_dashboard_category_and_excel_export(self) -> None:
        period = date.today().strftime("%Y-%m")
        self.vouchers.create(
            "ventas",
            Voucher(
                cliente_id=self.client_id,
                fecha=date.today().isoformat(),
                periodo_fiscal=period,
                tipo_comprobante="Factura C",
                punto_venta="2",
                numero_comprobante="10",
                contraparte_nombre="Comprador",
                importe_original=1_000_000,
            ),
        )
        dashboard = self.mono.dashboard(self.client_id)
        self.assertEqual(dashboard["sales"]["mes"], 1_000_000)
        self.assertEqual(dashboard["suggested_category"], "A")

        output = self.path / "ventas.xlsx"
        ReportService(self.vouchers).export_vouchers(
            "ventas", output, self.client_id, period
        )
        workbook = load_workbook(output)
        self.assertEqual(workbook.sheetnames, ["Ventas"])
        self.assertEqual(workbook["Ventas"]["A1"].value, "Cliente del estudio")

    def test_each_accounting_section_can_be_exported_to_excel(self) -> None:
        period = date.today().strftime("%Y-%m")
        self.vouchers.create(
            "ventas",
            Voucher(
                cliente_id=self.client_id,
                fecha=date.today().isoformat(),
                periodo_fiscal=period,
                tipo_comprobante="Factura C",
                punto_venta="3",
                numero_comprobante="20",
                contraparte_nombre="Cliente del exterior",
                contraparte_documento="",
                moneda="USD",
                tipo_cambio=1000,
                importe_original=600,
            ),
        )
        exporter = ReportService(self.vouchers)
        expected = {
            "resumen_mensual": ("Resumen mensual", "Período"),
            "significativos": ("Significativos", "Fecha"),
            "moneda_extranjera": ("Moneda extranjera", "Fecha"),
            "ranking": ("Ranking", "Puesto"),
        }
        for section, (sheet_name, first_header) in expected.items():
            output = self.path / f"{section}.xlsx"
            exporter.export_accounting_section(
                "ventas", section, output, self.client_id
            )
            workbook = load_workbook(output)
            self.assertEqual(workbook.sheetnames, [sheet_name])
            sheet = workbook[sheet_name]
            self.assertEqual(sheet["A1"].value, first_header)
            self.assertEqual(sheet.freeze_panes, "A2")
            self.assertGreaterEqual(sheet.max_row, 2)
            workbook.close()

    def test_arca_csv_import_and_iibb(self) -> None:
        source = self.path / "emitidos.csv"
        source.write_text(
            '"Fecha de Emisión";"Tipo de Comprobante";"Punto de Venta";'
            '"Número Desde";"Número Hasta";"Cód. Autorización";'
            '"Tipo Doc. Receptor";"Nro. Doc. Receptor";"Denominación Receptor";'
            '"Tipo Cambio";"Moneda";"Imp. Total"\n'
            '2026-06-01;11;1;10;10;123;80;30700000001;Cliente Uno;1;$;62150,30\n'
            '2026-06-02;13;1;11;11;124;80;30700000001;Cliente Uno;1;$;1250000,50\n',
            encoding="utf-8",
        )
        importer = ImportService(self.database, self.vouchers)
        preview = importer.preview(source, "ventas")
        self.assertEqual(preview.missing, [])
        result = importer.import_rows(preview, self.client_id)
        self.assertEqual(result["imported"], 2)
        rows = self.vouchers.list("ventas", self.client_id, "2026-06")
        self.assertEqual(rows[0]["importe_neto_fiscal"], -1_250_000.50)
        self.assertEqual(rows[0]["nombre_archivo_origen"], "emitidos.csv")
        self.assertIsNotNone(rows[0]["id_importacion"])

        iibb = IibbService(self.database, self.config)
        iibb.save_profile(
            self.client_id,
            {"regimen_principal": "ARBA REG GENERAL", "alicuota": 0.035},
        )
        calculation = iibb.calculate_and_save(self.client_id, "2026-06")
        self.assertEqual(calculation["base"], 0)
        deleted = importer.delete_batch(self.client_id, result["import_id"])
        self.assertEqual(deleted, 2)
        self.assertEqual(self.vouchers.list("ventas", self.client_id, "2026-06"), [])


if __name__ == "__main__":
    unittest.main()
