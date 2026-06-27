from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import Database, initialize_database  # noqa: E402


def main() -> None:
    database = Database(ROOT / "data" / "estudio_contable.db")
    initialize_database(database)
    tables = (
        "alertas_fiscales",
        "comprobantes_ventas",
        "comprobantes_compras",
        "importaciones_archivos",
    )
    for table in tables:
        count = database.query_one(
            f"""
            SELECT COUNT(*) AS n FROM {table} records
            LEFT JOIN clientes clients ON clients.id = records.cliente_id
            WHERE clients.id IS NULL
            """
        )["n"]
        print(f"{table}: {count} huérfano(s)")

    demo = database.query_one(
        "SELECT id FROM clientes WHERE email = ?", ("demo@estudio.local",)
    )
    if demo:
        client_id = int(demo["id"])
        alerts = database.query_one(
            "SELECT COUNT(*) AS n FROM alertas_fiscales WHERE cliente_id = ?",
            (client_id,),
        )["n"]
        sales = database.query_one(
            "SELECT COUNT(*) AS n FROM comprobantes_ventas WHERE cliente_id = ?",
            (client_id,),
        )["n"]
        purchases = database.query_one(
            "SELECT COUNT(*) AS n FROM comprobantes_compras WHERE cliente_id = ?",
            (client_id,),
        )["n"]
        print(
            f"Cliente demo: {alerts} alerta(s), {sales} venta(s), "
            f"{purchases} compra(s)"
        )


if __name__ == "__main__":
    main()
