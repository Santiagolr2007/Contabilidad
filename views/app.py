from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from database import Database
from services import (
    ClientService,
    AdministrativeService,
    ArcaImportService,
    AlertService,
    ConfigService,
    DashboardService,
    ImportService,
    IibbService,
    LedgerService,
    LedgerExportService,
    MonotributoService,
    MonotributoCategoriesService,
    PlatformService,
    ReportService,
    RecategorizationService,
    VoucherService,
)

from .accounting_view import AccountingView
from .administrative_view import AdministrativeView
from .common import fit_window
from .clients_view import ClientsView
from .config_view import ConfigView
from .dashboard_view import DashboardView
from .monotributo_view import MonotributoView
from .reports_view import ReportsView
from .regime_view import RegimeView
from .placeholder_view import PlaceholderView
from .theme import COLORS, configure_theme


class AccountingStudioApp(tk.Tk):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.title("Estudio jurídico-contable · Gestión interna")
        fit_window(self, 1360, 840, margin=24)
        self.minsize(
            min(1000, self.winfo_screenwidth() - 40),
            min(650, self.winfo_screenheight() - 80),
        )
        configure_theme(self)

        self.database = database
        self.config_service = ConfigService(database)
        self.administrative_service = AdministrativeService(database)
        self.arca_import_service = ArcaImportService(database)
        self.client_service = ClientService(database)
        self.voucher_service = VoucherService(database, self.config_service)
        self.import_service = ImportService(database, self.voucher_service)
        self.dashboard_service = DashboardService(database)
        self.monotributo_service = MonotributoService(
            database, self.voucher_service, self.config_service
        )
        self.monotributo_categories_service = MonotributoCategoriesService(database)
        self.iibb_service = IibbService(database, self.config_service)
        self.ledger_service = LedgerService(database)
        self.ledger_export_service = LedgerExportService(database, self.ledger_service)
        self.platform_service = PlatformService(database)
        self.recategorization_service = RecategorizationService(
            database, self.monotributo_service
        )
        self.alert_service = AlertService(
            database, self.config_service, self.voucher_service, self.monotributo_service
        )
        self.report_service = ReportService(self.voucher_service)

        self.sidebar = tk.Frame(self, bg=COLORS["navy"], width=235)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.content = ttk.Frame(self)
        self.content.pack(side="left", fill="both", expand=True)
        self.current_view = None
        self.navigation_buttons: dict[str, tk.Button] = {}
        self._build_sidebar()
        self.show_view("dashboard")
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

    def _build_sidebar(self) -> None:
        brand = tk.Frame(self.sidebar, bg=COLORS["navy"], padx=18, pady=20)
        brand.pack(fill="x")
        tk.Label(
            brand,
            text="ESTUDIO",
            bg=COLORS["navy"],
            fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="Gestión contable y fiscal",
            bg=COLORS["navy"],
            fg="#BFD4E6",
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        navigation = (
            ("dashboard", "Dashboard"),
            ("clientes", "Clientes"),
            ("contable", "Módulo contable"),
            ("monotributistas", "Monotributistas"),
            ("responsables", "Responsables inscriptos"),
            ("ganancias", "Ganancias"),
            ("bienes", "Bienes personales"),
            ("casas", "Casas particulares"),
            ("documentacion", "Documentación"),
            ("vencimientos", "Vencimientos"),
            ("honorarios", "Honorarios"),
            ("reportes", "Reportes"),
            ("configuracion", "Configuración"),
        )
        for key, label in navigation:
            button = tk.Button(
                self.sidebar,
                text=label,
                command=lambda route=key: self.show_view(route),
                anchor="w",
                relief="flat",
                borderwidth=0,
                padx=18,
                pady=8,
                bg=COLORS["navy"],
                fg="#E4EEF6",
                activebackground=COLORS["navy_light"],
                activeforeground="white",
                font=("Segoe UI", 9),
                cursor="hand2",
            )
            button.pack(fill="x")
            self.navigation_buttons[key] = button

        tk.Label(
            self.sidebar,
            text="Etapa 1 · Base local SQLite",
            bg=COLORS["navy"],
            fg="#8FAFC8",
            font=("Segoe UI", 8),
        ).pack(side="bottom", anchor="w", padx=18, pady=14)

    def show_view(self, route: str, **kwargs) -> None:
        if self.current_view is not None:
            self.current_view.destroy()
        for key, button in self.navigation_buttons.items():
            button.configure(
                bg=COLORS["navy_light"] if key == route else COLORS["navy"],
                fg="white" if key == route else "#E4EEF6",
            )

        factories = {
            "dashboard": lambda: DashboardView(self.content, self),
            "clientes": lambda: ClientsView(
                self.content, self, action=kwargs.get("action")
            ),
            "contable": lambda: AccountingView(self.content, self),
            "monotributistas": lambda: MonotributoView(self.content, self),
            "responsables": lambda: RegimeView(self.content,self,"Responsables inscriptos","responsable_inscripto"),
            "ganancias": lambda: RegimeView(self.content,self,"Ganancias","ganancias"),
            "bienes": lambda: RegimeView(self.content,self,"Bienes personales","bienes_personales"),
            "casas": lambda: RegimeView(self.content,self,"Casas particulares","casas_particulares"),
            "documentacion": lambda: AdministrativeView(self.content, self, "documentacion"),
            "tareas": lambda: AdministrativeView(self.content, self, "tareas"),
            "vencimientos": lambda: AdministrativeView(self.content, self, "vencimientos"),
            "honorarios": lambda: AdministrativeView(self.content, self, "honorarios"),
            "reportes": lambda: ReportsView(self.content, self),
            "configuracion": lambda: ConfigView(self.content, self),
        }
        self.current_view = factories.get(route, factories["dashboard"])()
        self.current_view.pack(fill="both", expand=True)
