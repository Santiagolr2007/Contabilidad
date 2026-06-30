from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database, initialize_database
from database.seed import seed_reference_data
from models import Client, FiscalProfile, MonotributoProfile
from services import ClientService, ResponsibleService


class ResponsibleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "test.db")
        initialize_database(self.database); seed_reference_data(self.database)
        clients = ClientService(self.database)
        self.client_id = clients.save(
            Client("Sociedad IVA SA", "30712345678", tipo_persona="sociedad", rubro="Comercio"),
            FiscalProfile(regimen_principal="Sociedad Responsable Inscripta", condicion_iva="Responsable Inscripto"),
            MonotributoProfile(estado="inactivo"),
        )
        self.mono_id = clients.save(
            Client("Solo Monotributo", "20345678901"),
            FiscalProfile(regimen_principal="monotributista"),
            MonotributoProfile(categoria_actual="A"),
        )
        self.service = ResponsibleService(self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _seed_movements(self) -> None:
        sale = (self.client_id, "2026-06-10", "2026-06", "Factura A", "1", "0001", "Contraparte", "30111111118", "ARS", 1, 100000, 100000, 1, 100000, "normal", "ARCA")
        self.database.execute("""INSERT INTO comprobantes_ventas(cliente_id,fecha,periodo_fiscal,tipo_comprobante,punto_venta,numero_comprobante,contraparte_nombre,contraparte_documento,moneda,tipo_cambio,importe_original,importe_pesos,signo_fiscal,importe_neto_fiscal,estado,origen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", sale)
        purchase = (self.client_id, "2026-06-11", "2026-06", "Factura A", "1", "0002", "Proveedor", "30222222229", "ARS", 1, 40000, 40000, 1, 40000, "normal", "ARCA")
        self.database.execute("""INSERT INTO comprobantes_compras(cliente_id,fecha,periodo_fiscal,tipo_comprobante,punto_venta,numero_comprobante,contraparte_nombre,contraparte_documento,moneda,tipo_cambio,importe_original,importe_pesos,signo_fiscal,importe_neto_fiscal,estado,origen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", purchase)
        self.database.execute("INSERT INTO operaciones_mercado_libre(cliente_id,fecha,periodo,tipo_operacion,contraparte,importe_neto,retenciones,percepciones,moneda) VALUES(?,?,?,?,?,?,?,?,?)", (self.client_id, "2026-06-12", "2026-06", "Venta", "Comprador ML", 50000, 200, 100, "ARS"))
        self.database.execute("INSERT INTO operaciones_mercado_libre(cliente_id,fecha,periodo,tipo_operacion,contraparte,importe_neto,moneda) VALUES(?,?,?,?,?,?,?)", (self.client_id, "2026-06-14", "2026-06", "Compra", "Proveedor ML", 10000, "ARS"))
        self.database.execute("INSERT INTO movimientos_mercado_pago(cliente_id,fecha,periodo,tipo_movimiento,importe_neto,retenciones,percepciones,moneda) VALUES(?,?,?,?,?,?,?,?)", (self.client_id, "2026-06-15", "2026-06", "Cobranza", 1000, 1000, 500, "USD"))
        self.database.execute("INSERT INTO iibb_monotributo(cliente_id,periodo,base_imponible,alicuota,impuesto_determinado,retenciones,percepciones) VALUES(?,?,?,?,?,?,?)", (self.client_id, "2026-06", 150000, .035, 5250, 300, 200))
        self.database.execute("INSERT INTO vencimientos(cliente_id,impuesto,periodo,fecha_vencimiento,estado) VALUES(?,?,?,?,?)", (self.client_id, "IVA", "2026-06", "2026-06-30", "Pendiente"))
        self.database.execute("INSERT INTO documentacion(cliente_id,periodo,tipo_documento,estado) VALUES(?,?,?,?)", (self.client_id, "2026-06", "Libro IVA", "Solicitada"))
        self.database.execute("INSERT INTO tareas(cliente_id,modulo,titulo,estado,prioridad) VALUES(?,?,?,?,?)", (self.client_id, "IVA", "Control", "Pendiente", "Alta"))
        self.database.execute("INSERT INTO honorarios(cliente_id,servicio,periodo,importe,estado,saldo_pendiente) VALUES(?,?,?,?,?,?)", (self.client_id, "Abono", "2026-06", 50000, "Pendiente", 50000))

    def test_selector_only_contains_responsables_and_iva(self) -> None:
        ids = {row["id"] for row in self.service.clients()}
        self.assertIn(self.client_id, ids)
        self.assertNotIn(self.mono_id, ids)

    def test_dashboard_combines_arca_platforms_iibb_and_pending_items(self) -> None:
        self._seed_movements()
        data = self.service.dashboard(self.client_id, 2026, 6)
        self.assertEqual(data["ventas"], 150000)
        self.assertEqual(data["compras"], 50000)
        self.assertEqual(data["iva_debito"], 31500)
        self.assertEqual(data["iva_credito"], 10500)
        self.assertEqual(data["saldo_iva"], 21000)
        self.assertEqual(data["retenciones"], 1500)
        self.assertEqual(data["percepciones"], 800)
        self.assertEqual(data["iibb_estimado"], 5250)
        self.assertEqual(data["usd"], 1)
        self.assertEqual(data["vencimientos_proximos"], 1)
        self.assertEqual(data["documentacion_pendiente"], 1)
        self.assertGreaterEqual(data["tareas_pendientes"], 1)
        self.assertEqual(data["pagos_pendientes"], 1)
        self.assertEqual(len(self.service.iva_monthly(self.client_id, 2026, 6)), 12)
        sales = self.service.sales_or_purchases(self.client_id, "ventas", 2026)
        self.assertEqual({row["fuente"] for row in sales}, {"ARCA", "Mercado Libre"})
        self.assertTrue(all("id" not in row and "cliente_id" not in row for row in sales))


if __name__ == "__main__":
    unittest.main()
