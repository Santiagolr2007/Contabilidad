from __future__ import annotations

import sys
from pathlib import Path
from tkinter import messagebox

from database import Database, initialize_database
from database.seed import seed_demo_data, seed_reference_data
from views import AccountingStudioApp


ROOT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = ROOT_DIR / "data" / "estudio_contable.db"


def build_application(database_path: Path = DATABASE_PATH) -> AccountingStudioApp:
    database = Database(database_path)
    initialize_database(database)
    seed_reference_data(database)
    seed_demo_data(database)
    return AccountingStudioApp(database)


def main() -> int:
    try:
        application = build_application()
        application.mainloop()
        return 0
    except Exception as error:
        try:
            messagebox.showerror(
                "No se pudo iniciar la aplicación",
                f"Ocurrió un error durante el inicio:\n\n{error}",
            )
        except Exception:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
