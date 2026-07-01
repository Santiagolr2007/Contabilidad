from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database, initialize_database
from database.seed import seed_reference_data
from models import Client, FiscalProfile, MonotributoProfile
from services import ClientService, LedgerService, ResponsibleService


class ResponsibleLedgerPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "test.db")
        initialize_database(self.database)
        seed_reference_data(self.database)
        self.clients = ClientService(self.database)
        self.ledger = LedgerService(self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _client(self, name: str, cuit: str, regime: str = "monotributista") -> int:
        return self.clients.save(
            Client(name, cuit),
            FiscalProfile(regimen_principal=regime, condicion_iva=regime),
            MonotributoProfile(categoria_actual="A") if "mono" in regime.casefold() else None,
        )

    @staticmethod
    def _fiscal(values: dict) -> FiscalProfile:
        return FiscalProfile(
            **{key: values.get(key) for key in FiscalProfile.__dataclass_fields__}
        )

    def test_legajos_are_correlative_editable_and_unique(self) -> None:
        first = self._client("Cliente Uno", "20123456786")
        second = self._client("Cliente Dos", "20345678901")
        self.assertEqual(self.clients.get_bundle(first)["client"]["legajo"], "EA-0010")
        self.assertEqual(self.clients.get_bundle(second)["client"]["legajo"], "EA-0011")

        bundle = self.clients.get_bundle(second)
        client = Client(**{key: bundle["client"].get(key) for key in Client.__dataclass_fields__})
        client.legajo = "EA-0099"
        self.clients.save(client, self._fiscal(bundle["fiscal"]), None)
        self.assertEqual(self.clients.get_bundle(second)["client"]["legajo"], "EA-0099")

        bundle = self.clients.get_bundle(second)
        duplicate = Client(**{key: bundle["client"].get(key) for key in Client.__dataclass_fields__})
        duplicate.legajo = "EA-0010"
        with self.assertRaisesRegex(ValueError, "legajo"):
            self.clients.save(duplicate, self._fiscal(bundle["fiscal"]), None)

    def test_budget_numbers_and_payment_link_are_saved(self) -> None:
        client_id = self._client("Presupuestos SA", "30712345678", "Responsable Inscripto")
        budget_id = self.ledger.save_record(
            client_id,
            "servicio_presupuesto",
            {
                "descripcion": "Abono mensual",
                "periodo": "06/2026",
                "valor_presupuestado": "125000",
                "estado_presupuesto": "Aceptado",
            },
        )
        budget = self.ledger.get_record(budget_id)
        self.assertEqual(budget["datos"]["numero_presupuesto"], "EAP-0010")
        self.assertEqual(float(budget["saldo"]), 125000)

        payment_id = self.ledger.save_record(
            client_id,
            "pagos",
            {
                "numero_presupuesto": "EAP-0010",
                "concepto": "Abono mensual",
                "importe_facturado": "125000",
                "importe_cobrado": "25000",
                "estado_pago": "Cobro parcial",
            },
        )
        payment = self.ledger.get_record(payment_id)
        self.assertEqual(payment["numero_presupuesto"], "EAP-0010")
        self.assertEqual(float(payment["saldo"]), 100000)

        changed = dict(budget["datos"])
        changed["observaciones"] = "Presupuesto actualizado"
        self.ledger.save_record(client_id, "servicio_presupuesto", changed, budget_id)
        initialize_database(self.database)
        self.assertEqual(
            self.ledger.get_record(budget_id)["datos"]["numero_presupuesto"],
            "EAP-0010",
        )

    def test_responsible_profile_and_dynamic_arca_are_complete(self) -> None:
        client_id = self._client(
            "Régimen General SA",
            "30678901234",
            "Responsable Inscripto Ganancias Bienes Personales",
        )
        responsible = ResponsibleService(self.database)
        responsible.save_profile(
            client_id,
            {
                "ri_inscripto": "Sí",
                "iva_ultimo_presentado": "05/2026",
                "gan_inscripto": "Sí",
                "ctrl_riesgo": "Medio",
            },
        )
        profile = responsible.profile(client_id)
        self.assertEqual(profile["iva_ultimo_presentado"], "05/2026")
        self.assertEqual(profile["ctrl_riesgo"], "Medio")

        keys = {field[0] for field in self.ledger.section_fields(client_id, "arca")}
        self.assertIn("ri_alta_iva_arca", keys)
        self.assertIn("gan_estado_arca", keys)
        self.assertIn("bp_estado_arca", keys)
        self.assertIn("ri_mis_comprobantes_arca", keys)

    def test_document_can_be_marked_received_with_date(self) -> None:
        client_id = self._client("Documentación SRL", "30555111222")
        record_id = self.ledger.save_record(
            client_id,
            "documentacion",
            {
                "documento": "Constancia de CUIT",
                "estado": "Solicitado",
                "fecha_solicitud": "01/06/2026",
                "obligatorio": "Sí",
            },
        )
        record = self.ledger.get_record(record_id)
        updated = dict(record["datos"])
        updated.update({"estado": "Recibido", "fecha_recepcion": "15/06/2026"})
        self.ledger.save_record(client_id, "documentacion", updated, record_id)
        received = self.ledger.get_record(record_id)
        self.assertEqual(received["estado"], "Recibido")
        self.assertEqual(received["datos"]["fecha_recepcion"], "2026-06-15")


if __name__ == "__main__":
    unittest.main()
