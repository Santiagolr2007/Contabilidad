from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import Database, initialize_database  # noqa: E402
from database.seed import seed_demo_data, seed_reference_data  # noqa: E402


def main() -> None:
    path = ROOT / "data" / "estudio_contable.db"
    database = Database(path)
    initialize_database(database)
    seed_reference_data(database)
    seed_demo_data(database)
    print(f"Base lista: {path}")
    print(f"Clientes: {database.query_one('SELECT COUNT(*) AS n FROM clientes')['n']}")
    print(
        "Comprobantes: "
        f"{database.query_one('SELECT COUNT(*) AS n FROM comprobantes_ventas')['n']} ventas, "
        f"{database.query_one('SELECT COUNT(*) AS n FROM comprobantes_compras')['n']} compras"
    )


if __name__ == "__main__":
    main()
