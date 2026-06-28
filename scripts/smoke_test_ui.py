from pathlib import Path
import sys
import tempfile
from tkinter import messagebox


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import build_application  # noqa: E402
from views.administrative_view import RecordDialog  # noqa: E402
from views.clients_view import ClientForm  # noqa: E402
from views.reports_view import LastTwelveMonthsDialog  # noqa: E402
from views.ledger_view import ClientLedgerDialog  # noqa: E402


def main() -> None:
    def fail_dialog(title, message, **_kwargs):
        raise RuntimeError(f"{title}: {message}")

    messagebox.showerror = fail_dialog
    routes = (
        "dashboard",
        "clientes",
        "contable",
        "monotributistas",
        "responsables",
        "ganancias",
        "bienes",
        "casas",
        "documentacion",
        "tareas",
        "vencimientos",
        "honorarios",
        "reportes",
        "configuracion",
    )
    with tempfile.TemporaryDirectory() as directory:
        application = build_application(Path(directory) / "smoke.db")
        application.withdraw()
        for route in routes:
            print(f"Abriendo: {route}", flush=True)
            application.show_view(route)
            application.update_idletasks()
            print(f"OK: {route}", flush=True)
            if route == "clientes":
                dialog = ClientForm(
                    application.current_view, application, None, lambda: None
                )
                dialog.update_idletasks()
                dialog.destroy()
                print("OK: formulario de cliente", flush=True)
                clients = application.client_service.list_clients()
                if clients:
                    ledger = ClientLedgerDialog(
                        application.current_view, application, int(clients[0]["id"])
                    )
                    ledger.update_idletasks()
                    ledger.destroy()
                    print("OK: legajo integral", flush=True)
            elif route in ("tareas", "vencimientos", "honorarios"):
                dialog = RecordDialog(
                    application.current_view,
                    application,
                    route,
                    lambda: None,
                )
                dialog.update_idletasks()
                dialog.destroy()
                print(f"OK: formulario de {route}", flush=True)
            elif route == "reportes":
                clients = application.client_service.list_clients()
                if clients:
                    dialog = LastTwelveMonthsDialog(
                        application.current_view,
                        application,
                        int(clients[0]["id"]),
                    )
                    dialog.update_idletasks()
                    dialog.destroy()
                    print("OK: vista de últimos 12 meses", flush=True)
        application.destroy()


if __name__ == "__main__":
    main()
