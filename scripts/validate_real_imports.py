from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import Database, initialize_database  # noqa: E402
from database.seed import seed_reference_data  # noqa: E402
from models import Client, FiscalProfile, MonotributoProfile  # noqa: E402
from services import ClientService, ConfigService, ImportService, VoucherService  # noqa: E402


def main() -> None:
    source = ROOT / "datos_afip"
    emitted = next(source.glob("comprobantes_consulta_csv_emitidos*.csv"))
    received = next(source.glob("Mis Comprobantes Recibidos*.xlsx"))
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "imports.db")
        initialize_database(database)
        seed_reference_data(database)
        client_id = ClientService(database).save(
            Client("Importación de prueba", "20123456786"),
            FiscalProfile(regimen_principal="monotributista"),
            MonotributoProfile(categoria_actual="A", actividad_fiscal="Servicios"),
        )
        vouchers = VoucherService(database, ConfigService(database))
        importer = ImportService(database, vouchers)
        for kind, path in (("ventas", emitted), ("compras", received)):
            preview = importer.preview(path, kind)
            if preview.missing:
                raise RuntimeError(f"Mapeo incompleto en {path.name}: {preview.missing}")
            result = importer.import_rows(preview, client_id)
            print(kind, result)


if __name__ == "__main__":
    main()
