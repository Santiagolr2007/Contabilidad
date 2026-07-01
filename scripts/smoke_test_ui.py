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
from models import Client, FiscalProfile, MonotributoProfile  # noqa: E402


def main() -> None:
    def widget_texts(widget) -> list[str]:
        texts = []
        for child in widget.winfo_children():
            try:
                value = child.cget("text")
            except Exception:
                value = ""
            if value:
                texts.append(str(value))
            texts.extend(widget_texts(child))
        return texts

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
        application.client_service.save(
            Client("Monotributista Smoke", "20111111112"),
            FiscalProfile(regimen_principal="monotributista"),
            MonotributoProfile(categoria_actual="A"),
        )
        application.client_service.save(
            Client("Responsable Smoke SA", "30222222223", tipo_persona="sociedad", rubro="Servicios"),
            FiscalProfile(regimen_principal="Sociedad Responsable Inscripta", condicion_iva="Responsable Inscripto"),
            MonotributoProfile(estado="inactivo"),
        )
        for route in routes:
            print(f"Abriendo: {route}", flush=True)
            application.show_view(route)
            application.update_idletasks()
            print(f"OK: {route}", flush=True)
            if route == "monotributistas":
                assert len(application.current_view.details.pages) == 13
                assert max(int(button.grid_info()["row"]) for button in application.current_view.details.buttons) >= 1
                assert application.current_view.details.pages[0].horizontal
                print("OK: 13 solapas y doble scroll de Monotributo", flush=True)
            elif route == "responsables":
                assert len(application.current_view.details.pages) == 14
                assert max(int(button.grid_info()["row"]) for button in application.current_view.details.buttons) >= 1
                assert application.current_view.details.pages[0].horizontal
                print("OK: 14 solapas y doble scroll de Responsable Inscripto", flush=True)
            elif route == "clientes":
                client_text = " | ".join(widget_texts(application.current_view))
                assert "Sistema Registral" not in client_text
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
                    tab_names = [str(button.cget("text")) for button in ledger.notebook.buttons]
                    assert len(tab_names) == 16
                    assert tab_names.index("Responsable Inscripto") == tab_names.index("Monotributo") + 1
                    for removed in (
                        "Valores Mensuales", "Contactos ARCA", "Domicilios ARCA",
                        "Datos Migratorios", "Societario Libros", "Historial",
                    ):
                        assert removed not in tab_names
                    ledger.destroy()
                    print("OK: legajo integral con 16 solapas y perfiles fiscales", flush=True)
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
