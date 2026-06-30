from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from utils.formatters import display_date, display_period

from .common import fit_window
from .ledger_view import ClientLedgerDialog
from .theme import COLORS


CARD_DEFINITIONS = (
    ("activos", "● Clientes activos", "clientes_activos", COLORS["green"]),
    ("monotributistas", "◆ Monotributistas", "monotributistas", COLORS["blue"]),
    ("responsables", "■ Responsables Inscriptos", "responsables_inscriptos", "#D97706"),
    ("bienes", "▲ Bienes Personales", "bienes_personales", "#2AA6B8"),
    ("ganancias", "★ Ganancias", "ganancias", COLORS["amber"]),
    ("casas", "● Casas particulares", "casas_particulares", "#B86B8B"),
)


class DashboardView(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=18)
        self.app = app
        self.metrics = app.dashboard_service.general_metrics()
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Dashboard general", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Actualizar datos", command=self.refresh).pack(side="right")
        ttk.Button(top, text="Exportar PDF", command=lambda: self.export_dashboard("pdf")).pack(side="right", padx=6)
        ttk.Button(top, text="Exportar Excel", command=lambda: self.export_dashboard("xlsx")).pack(side="right")
        ttk.Label(self, text="Control general del estudio. Todas las tarjetas y alertas abren su detalle.", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 8))
        ttk.Label(
            self,
            text=f"Total de clientes: {self.metrics.get('total_clientes', 0)}   |   Sociedades activas: {self.metrics.get('sociedades', 0)}",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 4))

        cards = ttk.Frame(self)
        cards.pack(fill="x")
        for index, (key, title, metric, color) in enumerate(CARD_DEFINITIONS):
            cards.columnconfigure(index % 3, weight=1)
            button = tk.Button(
                cards,
                text=f"{title}\n{self.metrics.get(metric, 0)}\nVer detalle",
                command=lambda selected=key, label=title: self.open_category(selected, label),
                bg=color,
                fg="white",
                activebackground=color,
                activeforeground="white",
                relief="flat",
                font=("Segoe UI", 11, "bold"),
                pady=7,
                cursor="hand2",
            )
            button.grid(row=index // 3, column=index % 3, sticky="nsew", padx=5, pady=4)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, pady=(10, 0))
        self._alerts_tab(notebook)
        self._due_tab(notebook)
        self._shortcuts_tab(notebook)

    def refresh(self) -> None:
        self.app.show_view("dashboard")

    def open_category(self, key: str, title: str) -> None:
        if key == "responsables":
            self.app.show_view("responsables")
            return
        rows = self.app.dashboard_service.clients_by_category(key)
        DashboardDetailDialog(self, self.app, title, rows, f"Categoría: {title}")

    def _alerts_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Alertas activas")
        columns = ("tipo", "cantidad", "prioridad")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=9)
        for key, title, width in (("tipo", "Tipo de alerta", 390), ("cantidad", "Clientes afectados", 130), ("prioridad", "Prioridad", 100)):
            tree.heading(key, text=title); tree.column(key, width=width, anchor="center" if key != "tipo" else "w")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        tree.grid(row=0, column=0, sticky="nsew"); yscroll.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        alert_by_id = {}
        alerts = self.app.dashboard_service.active_alerts_summary()
        for alert in alerts:
            item = tree.insert("", "end", values=(alert["tipo_alerta"], alert["cantidad"], alert["prioridad"]))
            alert_by_id[item] = alert
        if not alerts:
            tree.insert("", "end", values=("No hay alertas activas.", "", ""))

        def open_alert(_event=None):
            selected = tree.selection()
            if not selected: return
            alert = alert_by_id.get(selected[0])
            if not alert: return
            rows = self.app.dashboard_service.alert_clients(alert["clave"])
            DashboardDetailDialog(self, self.app, alert["tipo_alerta"], rows, f"Prioridad: {alert['prioridad']}")

        tree.bind("<Double-1>", open_alert)
        ttk.Button(frame, text="Ver detalle de alerta", style="Primary.TButton", command=open_alert).grid(row=1, column=0, sticky="e", pady=(7, 0))

    def _due_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Vencimientos próximos")
        top = ttk.Frame(frame); top.pack(fill="x", pady=(0, 7))
        for days in (7, 15, 30):
            rows = self.app.dashboard_service.upcoming(days)
            clients = len({row["cliente_id"] for row in rows})
            ttk.Button(top, text=f"Dentro de {days} días: {len(rows)} ({clients} clientes)", command=lambda value=days: self.open_due(value)).pack(side="left", padx=(0, 7))
        overdue = self.app.dashboard_service.upcoming(overdue=True)
        ttk.Button(top, text=f"Vencidos: {len(overdue)}", command=lambda: self.open_due(0, True)).pack(side="left")
        columns = ("cliente", "impuesto", "organismo", "periodo", "fecha", "tipo", "estado")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        for key, title, width in (("cliente", "Cliente", 180), ("impuesto", "Impuesto / trámite", 180), ("organismo", "Organismo", 90), ("periodo", "Período", 85), ("fecha", "Fecha", 95), ("tipo", "Tipo", 160), ("estado", "Estado", 90)):
            tree.heading(key, text=title); tree.column(key, width=width, anchor="center" if key in ("periodo", "fecha", "estado") else "w")
        y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); x = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.pack(fill="both", expand=True); y.place(relx=1, rely=0, relheight=.9, anchor="ne"); x.pack(fill="x")
        for row in self.app.dashboard_service.upcoming(30)[:100]:
            tree.insert("", "end", values=(row["cliente"], row["impuesto"], row["organismo"], display_period(row["periodo"]), display_date(row["fecha_vencimiento"]), row["tipo_vencimiento"], row["estado"]))

    def open_due(self, days: int, overdue: bool = False) -> None:
        rows = self.app.dashboard_service.upcoming(days, overdue)
        DashboardDetailDialog(self, self.app, "Vencimientos vencidos" if overdue else f"Vencimientos dentro de {days} días", rows, "Ordenados por fecha ascendente")

    def _shortcuts_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=14)
        notebook.add(frame, text="Accesos rápidos")
        actions = (
            ("Nuevo cliente", lambda: self.app.show_view("clientes", action="new")),
            ("Legajo integral de cliente", lambda: self.app.show_view("clientes")),
            ("Reportes", lambda: self.app.show_view("reportes")),
            ("Vencimientos", lambda: self.app.show_view("vencimientos")),
            ("Honorarios / Pagos", lambda: self.app.show_view("honorarios")),
            ("Documentación pendiente", lambda: DashboardDetailDialog(self, self.app, "Documentación pendiente", self.app.dashboard_service.alert_clients("documentacion_pendiente"), "Pendiente")),
            ("Alertas activas", lambda: self.notebook_select_alerts(notebook)),
        )
        for index, (title, command) in enumerate(actions):
            frame.columnconfigure(index % 4, weight=1)
            ttk.Button(frame, text=title, style="Primary.TButton" if index < 3 else "TButton", command=command).grid(row=index // 4, column=index % 4, sticky="nsew", padx=6, pady=8, ipady=8)

    @staticmethod
    def notebook_select_alerts(notebook: ttk.Notebook) -> None:
        notebook.select(0)

    def export_dashboard(self, format_name: str) -> None:
        rows = [{"Sección": "Categorías", "Indicador": title.lstrip("●◆■▲★ "), "Cantidad": self.metrics.get(metric, 0), "Prioridad": "Informativa"} for _key, title, metric, _color in CARD_DEFINITIONS]
        rows.extend({"Sección": "Alertas activas", "Indicador": alert["tipo_alerta"], "Cantidad": alert["cantidad"], "Prioridad": alert["prioridad"]} for alert in self.app.dashboard_service.active_alerts_summary())
        for days in (7, 15, 30):
            rows.append({"Sección": "Vencimientos", "Indicador": f"Dentro de {days} días", "Cantidad": len(self.app.dashboard_service.upcoming(days)), "Prioridad": "Alta" if days <= 7 else "Media"})
        extension = f".{format_name}"
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, initialfile=f"Dashboard_{date.today().isoformat()}{extension}", filetypes=((format_name.upper(), f"*{extension}"),))
        if not filename: return
        method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
        method(Path(filename), "Dashboard general", rows, "Datos actuales")
        messagebox.showinfo("Dashboard exportado", f"Se creó:\n{filename}", parent=self)


class DashboardDetailDialog(tk.Toplevel):
    def __init__(self, parent, app, title: str, rows: list[dict], filter_text: str = "") -> None:
        super().__init__(parent)
        self.app, self.title_text, self.rows, self.filter_text = app, title, rows, filter_text
        self.title(title); fit_window(self, 1250, 720); self.transient(parent.winfo_toplevel()); self.grab_set()
        top = ttk.Frame(self, padding=12); top.pack(fill="x")
        ttk.Label(top, text=title, style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Cerrar", command=self.destroy).pack(side="right")
        ttk.Button(top, text="Exportar PDF", command=lambda: self.export("pdf")).pack(side="right", padx=6)
        ttk.Button(top, text="Exportar Excel", command=lambda: self.export("xlsx")).pack(side="right")
        columns = tuple(key for key in (rows[0].keys() if rows else ("Estado",)) if key not in ("cliente_id", "id"))
        container = ttk.Frame(self, padding=(12, 0, 12, 12)); container.pack(fill="both", expand=True)
        tree = ttk.Treeview(container, columns=columns, show="headings")
        self.tree = tree
        for key in columns:
            tree.heading(key, text=key.replace("_", " ").title())
            tree.column(key, width=145, anchor="center" if "fecha" in key or "periodo" in key or key == "estado" else "w")
        y = ttk.Scrollbar(container, orient="vertical", command=tree.yview); x = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky="nsew"); y.grid(row=0, column=1, sticky="ns"); x.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1); container.columnconfigure(0, weight=1)
        self.row_by_item = {}
        for row in rows:
            values = []
            for key in columns:
                value = row.get(key, "")
                if "fecha" in key: value = display_date(value)
                elif "periodo" in key: value = display_period(value)
                values.append(value)
            item = tree.insert("", "end", values=values); self.row_by_item[item] = row
        tree.bind("<Double-1>", lambda _event: self.open_ledger())
        ttk.Button(container, text="Abrir legajo", style="Primary.TButton", command=self.open_ledger).grid(row=2, column=0, sticky="e", pady=(8, 0))

    def open_ledger(self) -> None:
        selected = self.tree.selection()
        if not selected: return
        client_id = self.row_by_item[selected[0]].get("cliente_id")
        if client_id:
            ClientLedgerDialog(self, self.app, int(client_id))

    def export(self, format_name: str) -> None:
        extension = f".{format_name}"
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, initialfile=f"{self.title_text.replace('/', '-')}_{date.today().isoformat()}{extension}", filetypes=((format_name.upper(), f"*{extension}"),))
        if not filename: return
        method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
        method(Path(filename), self.title_text, self.rows, self.filter_text)
        messagebox.showinfo("Reporte exportado", f"Se creó:\n{filename}", parent=self)
