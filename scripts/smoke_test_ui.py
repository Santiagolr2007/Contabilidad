from pathlib import Path
import sys
import tempfile
from tkinter import messagebox


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import build_application  # noqa: E402


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
        application.destroy()


if __name__ == "__main__":
    main()
