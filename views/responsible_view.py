from __future__ import annotations

import os
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from utils.formatters import display_date, display_period, money, number_ar

from .common import MetricCard, ScrollableFrame, make_tree_sortable
from .ledger_view import ClientLedgerDialog, TwoRowNotebook
from .theme import COLORS


class ResponsibleInscriptoView(ttk.Frame):
    TAB_TITLES = (
        "Resumen", "Ventas", "Compras", "IVA", "Ganancias", "Autónomos",
        "IIBB", "Ingresos Brutos mensuales", "Clientes", "Proveedores",
        "Vencimientos", "Alertas", "Documentos", "Reportes",
    )

    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        self.clients = app.responsible_service.clients()
        self.client_map = {f"{row['nombre_razon_social']} · {row['cuit_cuil']}": int(row["id"]) for row in self.clients}
        self.selected = tk.StringVar(value=next(iter(self.client_map), ""))
        self.year = tk.StringVar(value=str(date.today().year))
        self.month = tk.StringVar(value=str(date.today().month))
        self.tab_rows: dict[str, list[dict]] = {}

        ttk.Label(self, text="Responsables Inscriptos", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Resumen fiscal, IVA, compras, ventas, acumulados, vencimientos y alertas.", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 10))

        controls = ttk.Frame(self); controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="Cliente").grid(row=0, column=0, sticky="w")
        self.combo = ttk.Combobox(controls, textvariable=self.selected, values=tuple(self.client_map), state="normal", width=46)
        self.combo.grid(row=0, column=1, sticky="ew", padx=6)
        self.combo.bind("<KeyRelease>", self._filter_clients)
        self.combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Label(controls, text="Año").grid(row=0, column=2, sticky="w", padx=(8, 0)); ttk.Entry(controls, textvariable=self.year, width=7).grid(row=0, column=3, padx=5)
        ttk.Label(controls, text="Mes").grid(row=0, column=4, sticky="w"); ttk.Entry(controls, textvariable=self.month, width=5).grid(row=0, column=5, padx=5)
        ttk.Button(controls, text="Actualizar", command=self.refresh).grid(row=0, column=6, padx=4)
        ttk.Button(controls, text="Abrir legajo integral", style="Primary.TButton", command=self.open_ledger).grid(row=0, column=7, padx=4)
        ttk.Button(controls, text="Cambios manuales", command=self.manual_changes).grid(row=1, column=1, columnspan=3, sticky="w", padx=6, pady=(5, 0))
        ttk.Button(controls, text="Reportes", command=self.open_reports_tab).grid(row=1, column=4, columnspan=2, sticky="w", padx=5, pady=(5, 0))
        ttk.Button(controls, text="Exportar Excel", command=lambda: self.export_current("xlsx")).grid(row=1, column=6, padx=4, pady=(5, 0))
        ttk.Button(controls, text="Exportar PDF", command=lambda: self.export_current("pdf")).grid(row=1, column=7, padx=4, pady=(5, 0))
        ttk.Button(controls, text="Imprimir", command=self.print_current).grid(row=1, column=8, padx=4, pady=(5, 0))
        controls.columnconfigure(1, weight=1)

        self.details = TwoRowNotebook(self, columns=7)
        self.details.pack(fill="both", expand=True)
        if self.client_map: self.refresh()
        else:
            ttk.Label(self, text="No hay clientes activos con condición Responsable Inscripto o IVA activo.", style="Subtitle.TLabel").pack(anchor="w", pady=20)

    def _filter_clients(self, _event=None) -> None:
        term = self.selected.get().casefold().strip()
        self.combo.configure(values=tuple(label for label in self.client_map if term in label.casefold()))

    def client_id(self) -> int | None:
        exact = self.client_map.get(self.selected.get())
        if exact: return exact
        term = self.selected.get().casefold().strip()
        matches = [value for label, value in self.client_map.items() if term and term in label.casefold()]
        return matches[0] if len(matches) == 1 else None

    def period_values(self) -> tuple[int, int]:
        try: year, month = int(self.year.get()), int(self.month.get())
        except ValueError as error: raise ValueError("Año y mes deben ser numéricos.") from error
        if not 2000 <= year <= 2100: raise ValueError("Ingresá un año válido.")
        if not 1 <= month <= 12: raise ValueError("Ingresá un mes entre 1 y 12.")
        return year, month

    def refresh(self) -> None:
        client_id = self.client_id()
        if not client_id:
            messagebox.showinfo("Seleccionar cliente", "Seleccioná un Responsable Inscripto por nombre o CUIT/CUIL.", parent=self); return
        try:
            year, month = self.period_values()
            dashboard = self.app.responsible_service.dashboard(client_id, year, month)
        except Exception as error:
            messagebox.showerror("No se pudo cargar", str(error), parent=self); return
        for tab in self.details.tabs(): self.details.forget(tab)
        self.tab_rows = {}
        self._add_summary(dashboard)
        self._add_table("Ventas", self.app.responsible_service.sales_or_purchases(client_id, "ventas", year))
        self._add_table("Compras", self.app.responsible_service.sales_or_purchases(client_id, "compras", year))
        self._add_table("IVA", self.app.responsible_service.iva_monthly(client_id, year, month))
        self._add_table("Ganancias", self.app.responsible_service.obligations(client_id, "ganancia"))
        self._add_table("Autónomos", self.app.responsible_service.obligations(client_id, "autonom"))
        self._add_table("IIBB", self.app.responsible_service.iibb_rows(client_id))
        self._add_table("Ingresos Brutos mensuales", self.app.responsible_service.iibb_rows(client_id, True))
        self._add_table("Clientes", self.app.responsible_service.rankings(client_id, "clientes", year))
        self._add_table("Proveedores", self.app.responsible_service.rankings(client_id, "proveedores", year))
        self._add_table("Vencimientos", self.app.responsible_service.vencimientos(client_id))
        self._add_table("Alertas", self.app.responsible_service.alerts(client_id))
        self._add_table("Documentos", self.app.responsible_service.documents(client_id))
        self._add_reports()

    def _add_summary(self, data: dict) -> None:
        scroll = ScrollableFrame(self.details, padding=12, horizontal=True)
        self.details.add(scroll, text="Resumen"); frame = scroll.content
        risk = str(data["riesgo_fiscal"] or "Bajo")
        state = str(data["estado_fiscal"] or "Activo")
        red_if = lambda condition: COLORS["red"] if condition else COLORS["green"]
        cards = (
            ("Condición fiscal", "Responsable Inscripto", COLORS["green"]),
            ("Denominación / Actividad", data["client"].get("actividad") or "Sin datos", COLORS["blue"]),
            ("Estado fiscal", state, red_if(state.casefold() in ("con deuda", "con alertas", "baja"))),
            ("Riesgo fiscal", risk, red_if(risk.casefold() in ("alto", "urgente", "revisar"))),
            ("Ventas del mes", money(data["ventas"]), COLORS["blue"]),
            ("Compras del mes", money(data["compras"]), COLORS["amber"]),
            ("Ventas año calendario", money(data["ventas_anio"]), COLORS["blue"]),
            ("Compras año calendario", money(data["compras_anio"]), COLORS["amber"]),
            ("Ventas últimos 12 meses", money(data["ventas_12"]), COLORS["blue"]),
            ("Compras últimos 12 meses", money(data["compras_12"]), COLORS["amber"]),
            ("IVA débito fiscal del mes", money(data["iva_debito"]), COLORS["blue"]),
            ("IVA crédito fiscal del mes", money(data["iva_credito"]), COLORS["blue"]),
            ("Saldo IVA estimado", money(data["saldo_iva"]), red_if(data["saldo_iva"] > 0)),
            ("Retenciones sufridas", money(data["retenciones"]), "#EA580C"),
            ("Percepciones sufridas", money(data["percepciones"]), "#EA580C"),
            ("IIBB estimado", money(data["iibb_estimado"]), COLORS["green"]),
            ("Comprobantes significativos", str(data["significativos"]), red_if(data["significativos"] > 0)),
            ("Operaciones USD / alertas", f"{data['usd']} / {data['alertas_activas']}", red_if(data["usd"] + data["alertas_activas"] > 0)),
            ("Vencimientos próximos", str(data["vencimientos_proximos"]), red_if(data["vencimientos_proximos"] > 0)),
            ("Documentación pendiente", str(data["documentacion_pendiente"]), COLORS["amber"] if data["documentacion_pendiente"] else COLORS["green"]),
            ("Tareas pendientes", str(data["tareas_pendientes"]), COLORS["amber"] if data["tareas_pendientes"] else COLORS["green"]),
            ("Pagos al estudio pendientes", str(data["pagos_pendientes"]), COLORS["red"] if data["pagos_pendientes"] else COLORS["green"]),
        )
        frame.columnconfigure(0, minsize=290); frame.columnconfigure(1, minsize=290); frame.columnconfigure(2, minsize=290)
        for index, (title, value, color) in enumerate(cards):
            MetricCard(frame, title, value, color).grid(row=index // 3, column=index % 3, sticky="nsew", padx=5, pady=5)
        raw_rows = []
        numeric = {
            "Ventas del mes": data["ventas"], "Compras del mes": data["compras"],
            "Ventas año calendario": data["ventas_anio"], "Compras año calendario": data["compras_anio"],
            "Ventas últimos 12 meses": data["ventas_12"], "Compras últimos 12 meses": data["compras_12"],
            "IVA débito fiscal": data["iva_debito"], "IVA crédito fiscal": data["iva_credito"],
            "Saldo IVA estimado": data["saldo_iva"], "Retenciones": data["retenciones"],
            "Percepciones": data["percepciones"], "IIBB estimado": data["iibb_estimado"],
        }
        raw_rows.extend({"Indicador": key, "Valor": value} for key, value in numeric.items())
        raw_rows.extend((
            {"Indicador": "Condición fiscal", "Valor": "Responsable Inscripto"},
            {"Indicador": "Actividad", "Valor": data["client"].get("actividad", "")},
            {"Indicador": "Estado fiscal", "Valor": state}, {"Indicador": "Riesgo fiscal", "Valor": risk},
        ))
        self.tab_rows["Resumen"] = raw_rows

    @staticmethod
    def _label(key: str) -> str:
        labels = {
            "periodo": "Período", "ventas": "Ventas gravadas", "compras": "Compras computables",
            "iva_debito": "IVA débito fiscal", "iva_credito": "IVA crédito fiscal",
            "saldo_iva": "Saldo IVA", "importe": "Importe", "total": "Total",
            "obligación": "Obligación", "fecha_desde": "Fecha desde", "fecha_hasta": "Fecha hasta",
        }
        return labels.get(key, key.replace("_", " ").title())

    @staticmethod
    def _format(key: str, value):
        if value is None: return ""
        name = key.casefold()
        if "periodo" in name: return display_period(str(value))
        if "fecha" in name or "vencimiento" in name: return display_date(str(value))
        if isinstance(value, (int, float)) and any(term in name for term in ("importe", "total", "venta", "compra", "iva", "saldo", "retencion", "percepcion", "base", "impuesto", "alicuota")): return number_ar(value)
        return value

    def _add_table(self, title: str, rows: list[dict]) -> None:
        frame = ttk.Frame(self.details, padding=8); self.details.add(frame, text=title)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(0, 5))
        ttk.Label(actions, text=f"{len(rows)} registros", style="Subtitle.TLabel").pack(side="left")
        ttk.Button(actions, text="Exportar Excel", command=lambda: self.export_tab(title, "xlsx")).pack(side="right")
        ttk.Button(actions, text="Exportar PDF", command=lambda: self.export_tab(title, "pdf")).pack(side="right", padx=5)
        ttk.Button(actions, text="Imprimir", command=lambda: self.print_tab(title)).pack(side="right")
        holder = ttk.Frame(frame); holder.pack(fill="both", expand=True)
        display_rows = rows or [{"estado": "Sin información cargada"}]
        hidden = {"id", "cliente_id", "responsable", "actualizado_en", "ultima_actualizacion"}
        columns = tuple(key for key in display_rows[0] if key not in hidden)
        tree = ttk.Treeview(holder, columns=columns, show="headings")
        numeric = set()
        for key in columns:
            tree.heading(key, text=self._label(key)); name = key.casefold()
            is_numeric = any(term in name for term in ("importe", "total", "venta", "compra", "iva", "saldo", "retencion", "percepcion", "base", "impuesto", "alicuota", "operaciones"))
            if is_numeric: numeric.add(key)
            anchor = "e" if is_numeric else ("center" if "fecha" in name or "periodo" in name or name == "estado" else "w")
            tree.column(key, width=140 if anchor != "w" else 190, minwidth=90, anchor=anchor, stretch=True)
        sy = ttk.Scrollbar(holder, orient="vertical", command=tree.yview); sx = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.grid(row=0, column=0, sticky="nsew"); sy.grid(row=0, column=1, sticky="ns"); sx.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1); holder.columnconfigure(0, weight=1)
        for row in display_rows: tree.insert("", "end", values=[self._format(key, row.get(key)) for key in columns])
        make_tree_sortable(tree, numeric)
        self.tab_rows[title] = [{key: value for key, value in row.items() if key not in hidden} for row in rows]

    def _add_reports(self) -> None:
        scroll = ScrollableFrame(self.details, padding=18, horizontal=True); self.details.add(scroll, text="Reportes")
        frame = scroll.content
        ttk.Label(frame, text="Reportes del Responsable Inscripto", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        reports = (
            "Últimos 12 meses", "Ventas mensuales", "Compras mensuales", "Ingresos Brutos mensual",
            "Ranking de clientes", "Ranking de proveedores", "Comprobantes significativos", "Operaciones en USD",
        )
        for index, report in enumerate(reports, 1):
            ttk.Label(frame, text=report).grid(row=index, column=0, sticky="w", pady=4)
            ttk.Button(frame, text="Abrir módulo Reportes", command=lambda: self.app.show_view("reportes")).grid(row=index, column=1, padx=8, pady=4)
        self.tab_rows["Reportes"] = [{"Reporte disponible": report} for report in reports]

    def open_reports_tab(self) -> None:
        if self.details.pages: self.details.select(self.TAB_TITLES.index("Reportes"))

    def open_ledger(self) -> None:
        client_id = self.client_id()
        if not client_id: messagebox.showinfo("Seleccionar cliente", "Seleccioná un cliente.", parent=self); return
        ClientLedgerDialog(self, self.app, client_id)

    def manual_changes(self) -> None:
        client_id = self.client_id()
        if not client_id: messagebox.showinfo("Seleccionar cliente", "Seleccioná un cliente.", parent=self); return
        from .clients_view import ClientForm
        ClientForm(self, self.app, client_id, self.refresh)

    def current_title(self) -> str:
        return self.TAB_TITLES[self.details.current]

    def export_current(self, format_name: str) -> None:
        self.export_tab(self.current_title(), format_name)

    def export_tab(self, title: str, format_name: str) -> None:
        client_id = self.client_id()
        if not client_id: return
        client = next(row for row in self.clients if int(row["id"]) == client_id)
        extension = f".{format_name}"
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, initialfile=f"Responsable Inscripto - {title} - {client['nombre_razon_social']}{extension}", filetypes=((format_name.upper(), f"*{extension}"),))
        if not filename: return
        try:
            method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
            year, month = self.period_values()
            method(Path(filename), f"Responsable Inscripto - {title}", self.tab_rows.get(title, []), f"{client['nombre_razon_social']} · CUIT/CUIL {client['cuit_cuil']} · Período {month:02d}/{year}")
            messagebox.showinfo("Exportación terminada", f"Se creó:\n{filename}", parent=self)
        except Exception as error: messagebox.showerror("No se pudo exportar", str(error), parent=self)

    def print_current(self) -> None:
        self.print_tab(self.current_title())

    def print_tab(self, title: str) -> None:
        client_id = self.client_id()
        if not client_id: return
        client = next(row for row in self.clients if int(row["id"]) == client_id)
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=".pdf", initialfile=f"Responsable Inscripto - {title}.pdf", filetypes=(("PDF", "*.pdf"),))
        if not filename: return
        year, month = self.period_values()
        self.app.report_service.export_table_pdf(Path(filename), f"Responsable Inscripto - {title}", self.tab_rows.get(title, []), f"{client['nombre_razon_social']} · CUIT/CUIL {client['cuit_cuil']} · Período {month:02d}/{year}")
        try: os.startfile(filename, "print")
        except OSError: messagebox.showinfo("PDF listo", f"Abrí e imprimí:\n{filename}", parent=self)
