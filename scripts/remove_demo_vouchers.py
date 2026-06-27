from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import Database  # noqa: E402


def main() -> None:
    database = Database(ROOT / "data" / "estudio_contable.db")
    client = database.query_one(
        """
        SELECT id FROM clientes
        WHERE email = ? OR nombre_razon_social = ?
        LIMIT 1
        """,
        ("demo@estudio.local", "Cliente Demostración"),
    )
    if not client:
        print("No se encontró el cliente de demostración.")
        return
    client_id = int(client["id"])
    sales = database.query_one(
        "SELECT COUNT(*) AS n FROM comprobantes_ventas WHERE cliente_id = ?",
        (client_id,),
    )["n"]
    purchases = database.query_one(
        "SELECT COUNT(*) AS n FROM comprobantes_compras WHERE cliente_id = ?",
        (client_id,),
    )["n"]
    with database.connection() as connection:
        connection.execute(
            "DELETE FROM comprobantes_ventas WHERE cliente_id = ?", (client_id,)
        )
        connection.execute(
            "DELETE FROM comprobantes_compras WHERE cliente_id = ?", (client_id,)
        )
        connection.execute(
            "DELETE FROM alertas_fiscales WHERE cliente_id = ?", (client_id,)
        )
        connection.execute(
            "DELETE FROM importaciones_archivos WHERE cliente_id = ?", (client_id,)
        )
    print(f"Facturas demo eliminadas: {sales} ventas y {purchases} compras.")


if __name__ == "__main__":
    main()
