from __future__ import annotations

import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import Database, initialize_database
from database.seed import seed_reference_data
from models import Client, FiscalProfile, MonotributoProfile
from services import (
    ClientService,
    LedgerExportService,
    LedgerService,
)


def main() -> None:
    output = ROOT / "tmp" / "ledger_verify"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "verify.db")
        initialize_database(database)
        seed_reference_data(database)
        client_id = ClientService(database).save(
            Client("Cliente de Verificación", "20300412298"),
            FiscalProfile(regimen_principal="monotributista"),
            MonotributoProfile(
                categoria_actual="C",
                actividad_fiscal="Servicios",
                codigo_actividad="620100",
            ),
        )
        ledger = LedgerService(database)
        ledger.save_record(
            client_id,
            "pagos",
            {
                "fecha_emision": "01/06/2026",
                "periodo": "06-2026",
                "concepto": "Abono mensual",
                "importe_facturado": "150000",
                "importe_cobrado": "50000",
                "estado_pago": "Pago parcial",
                "fecha_vencimiento": "10/06/2026",
                "responsable": "NATALIA",
                "observaciones": "Registro de verificación visual con texto extendido.",
            },
        )
        ledger.save_record(
            client_id,
            "riesgos",
            {
                "tipo_riesgo": "Falta de documentación",
                "nivel": "Alto",
                "estado": "Informado al cliente",
                "recomendacion": "Regularizar documentación pendiente.",
                "responsable": "NATALIA",
            },
        )
        exporter = LedgerExportService(database, ledger)
        print(exporter.export_excel(output / "legajo_verificacion.xlsx", client_id))
        print(exporter.export_pdf(output / "legajo_verificacion.pdf", client_id))


if __name__ == "__main__":
    main()
