from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from models import Client, FiscalProfile
from utils.formatters import display_date, display_period, money, normalize_date

from .common import ScrollableFrame, fit_window, make_tree_sortable, selected_tree_id
from .date_widgets import DateEntry, ask_date
from .ledger_view import ClientLedgerDialog
from services.ledger_service import DOCUMENT_OPTIONS


DEFINITIONS = {
    "documentacion": (
        "Documentación y Accesos",
        (
            ("periodo", "Período", "text"),
            ("tipo_documento", "Documento", DOCUMENT_OPTIONS),
            ("estado", "Estado", ("Solicitado", "Recibido", "Pendiente", "Incompleto", "Vencido", "No corresponde", "Requiere actualización")),
            ("fecha_solicitud", "Fecha solicitud", "date"),
            ("fecha_recepcion", "Fecha recepción", "date"),
            ("obligatorio", "Obligatorio", ("Sí", "No", "Según caso", "No corresponde")),
            ("archivo_link", "Link o archivo", "text"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "tareas": (
        "Tareas",
        (
            ("modulo", "Área", "text"),
            ("periodo", "Período", "text"),
            ("titulo", "Tipo de tarea / evento", "text"),
            ("descripcion", "Descripción", "text"),
            ("fecha_inicio", "Fecha", "date"),
            ("fecha_vencimiento", "Fecha de vencimiento", "date"),
            ("fecha_cumplimiento", "Fecha de cumplimiento", "date"),
            ("estado", "Estado", ("Pendiente", "En proceso", "Esperando cliente", "Esperando organismo", "Cumplimentada", "Vencida", "Cancelada", "No corresponde")),
            ("prioridad", "Prioridad", ("Baja", "Media", "Alta", "Urgente")),
            ("medio", "Medio", "text"),
            ("documentacion_vinculada", "Documentación vinculada", "text"),
            ("proximo_paso", "Próximo paso", "text"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "vencimientos": (
        "Vencimientos",
        (
            ("impuesto", "Impuesto / trámite / obligación", "text"),
            ("organismo", "Organismo", ("ARCA", "ARBA", "AGIP", "COMARB", "Municipio", "IGJ", "DPPJ", "Ministerio de Trabajo", "Banco", "Estudio", "Otro")),
            ("periodo", "Período MM/AAAA", "text"),
            ("fecha_vencimiento", "Fecha vencimiento", "date"),
            ("tipo_vencimiento", "Tipo de vencimiento", ("multi", "Presentación", "Pago", "Renovación", "Recategorización", "Alta", "Baja", "Modificación", "Informe", "Control", "Reunión", "Respuesta a intimación", "Vencimiento de certificado", "Vencimiento contractual", "Otro")),
            ("estado", "Estado", ("Pendiente", "Cumplido", "Pagado", "Vencido", "No corresponde")),
            ("importe", "Importe", "text"),
            ("saldo", "Saldo", "text"),
            ("fecha_presentacion", "Fecha presentación", "date"),
            ("fecha_cumplimiento", "Fecha cumplimiento", "date"),
            ("fecha_pago", "Fecha pago", "date"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "honorarios": (
        "Honorarios - pagos al estudio",
        (
            ("numero_presupuesto", "Número de presupuesto", "budget"),
            ("tipo_registro", "Tipo de registro", ("Honorario", "Presupuesto", "Pago", "Abono mensual", "Trabajo extraordinario")),
            ("servicio", "Concepto / servicio", ("Alta inicial", "Abono mensual", "Liquidación mensual", "Presentación anual", "Regularización fiscal", "Regularización impositiva", "Fiscalización", "Moratoria / plan de pago", "Alta ARCA", "Alta IIBB", "Alta municipal", "Alta empleador", "Sueldos", "Casas particulares", "Societario", "Certificación", "Informe", "Consulta", "Otro")),
            ("periodo", "Período MM/AAAA", "text"),
            ("importe", "Importe presupuestado / facturado", "text"),
            ("importe_pagado", "Importe cobrado", "text"),
            ("saldo_pendiente", "Saldo pendiente", "text"),
            ("estado", "Estado de cobro", ("Pendiente", "Cobrado", "Cobro parcial", "Vencido", "Bonificado", "Anulado", "Sin presupuesto asociado", "No corresponde")),
            ("fecha_emision", "Fecha emisión", "date"),
            ("fecha_vencimiento", "Fecha vencimiento", "date"),
            ("fecha_cobro", "Fecha cobro", "date"),
            ("medio_pago", "Medio de cobro", "text"),
            ("comprobante_emitido", "Comprobante emitido", ("Sí", "No", "No corresponde")),
            ("tipo_comprobante", "Tipo de comprobante", "text"),
            ("numero_comprobante", "Número de comprobante", "text"),
            ("condiciones_presupuesto", "Condiciones del presupuesto", "text"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
}


class AdministrativeView(ttk.Frame):
    def __init__(self, parent, app, module: str) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        self.module = module
        title, _ = DEFINITIONS[module]
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=12)
        ttk.Button(
            toolbar, text="+ Agregar", style="Primary.TButton", command=self.add
        ).pack(side="left")
        if module == "documentacion":
            ttk.Button(
                toolbar,
                text="Ver tareas",
                command=lambda: app.show_view("tareas"),
            ).pack(side="left", padx=8)
        if module in ("documentacion", "tareas", "vencimientos", "honorarios"):
            ttk.Button(toolbar, text="Modificar", command=self.edit).pack(
                side="left", padx=(8, 0)
            )
            ttk.Button(toolbar, text="Eliminar", command=self.delete).pack(
                side="left", padx=(8, 0)
            )
        if module in ("documentacion", "tareas", "vencimientos", "honorarios"):
            ttk.Button(toolbar, text="Exportar Excel", command=lambda: self.export("xlsx")).pack(side="left", padx=(8,0))
            ttk.Button(toolbar, text="Exportar PDF", command=lambda: self.export("pdf")).pack(side="left", padx=(5,0))
            ttk.Button(toolbar, text="Abrir legajo", command=self.open_ledger).pack(side="left", padx=(8,0))
        if module == "vencimientos":
            ttk.Button(toolbar, text="Importar vencimientos ARCA", command=self.import_arca).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Actualizar", command=self.refresh).pack(side="right")

        if module in ("documentacion", "tareas", "vencimientos", "honorarios"):
            status_bar = ttk.LabelFrame(self, text="Acciones sobre el registro seleccionado", padding=6)
            status_bar.pack(fill="x", pady=(0, 8))
            actions = {
                "tareas": ("Cumplimentada", "Pendiente", "En proceso", "Vencida", "Cancelada", "No corresponde"),
                "vencimientos": ("Cumplido", "Pagado", "Pendiente", "Vencido", "No corresponde"),
                "honorarios": ("Cobrado", "Cobro parcial", "Pendiente", "Vencido", "Bonificado", "Anulado", "No corresponde"),
                "documentacion": ("Recibido", "Pendiente", "Incompleto", "Vencido", "No corresponde", "Requiere actualización"),
            }[module]
            for status in actions:
                label = {
                    "Cumplimentada": "Marcar cumplimentada",
                    "Cumplido": "Marcar cumplido",
                    "Pagado": "Marcar pagado",
                    "Cobrado": "Marcar como cobrado",
                    "Cobro parcial": "Marcar cobro parcial",
                    "Recibido": "Marcar como recibido",
                }.get(status, status)
                ttk.Button(status_bar, text=label, command=lambda value=status: self.change_status(value)).pack(side="left", padx=3)

        self.filter_state = tk.StringVar(value="Todos")
        self.filter_client = tk.StringVar(value="Todos")
        self.filter_period = tk.StringVar()
        self.filter_budget = tk.StringVar()
        self.filter_type = tk.StringVar(value="Todos")
        self.filter_organism = tk.StringVar(value="Todos")
        self.filter_text = tk.StringVar()
        self.filter_priority = tk.StringVar(value="Todos")
        self.filter_date_from = tk.StringVar()
        self.filter_date_to = tk.StringVar()
        self.filter_due_from = tk.StringVar()
        self.filter_due_to = tk.StringVar()
        clients = app.client_service.list_clients(include_inactive=True)
        self.filter_client_map = {"Todos": None, **{
            f"{row['nombre_razon_social']} · {row['cuit_cuil']}": int(row["id"])
            for row in clients
        }}
        if module in ("documentacion", "tareas", "vencimientos", "honorarios"):
            filters = ttk.Frame(self)
            filters.pack(fill="x", pady=(0, 8))
            ttk.Label(filters, text="Cliente").grid(row=0,column=0,sticky="w")
            ttk.Combobox(filters, textvariable=self.filter_client, values=tuple(self.filter_client_map), state="readonly", width=31).grid(row=0,column=1,sticky="ew",padx=(5,10))
            ttk.Label(filters, text="Estado").grid(row=0,column=2,sticky="w")
            states = {
                "tareas": ("Todos", "Pendiente", "En proceso", "Esperando cliente", "Esperando organismo", "Cumplimentada", "Vencida", "Cancelada", "No corresponde", "Vencidas por fecha"),
                "vencimientos": ("Todos", "Pendiente", "Cumplido", "Pagado", "Vencido", "No corresponde", "Próximos 30 días", "Vencidos por fecha"),
                "honorarios": ("Todos", "Pendiente", "Cobrado", "Cobro parcial", "Vencido", "Bonificado", "Anulado", "Sin presupuesto asociado", "No corresponde"),
                "documentacion": ("Todos", "Recibido", "Pendiente", "Incompleto", "Vencido", "Obligatorios", "No corresponde", "Requiere actualización"),
            }[module]
            ttk.Combobox(filters, textvariable=self.filter_state, values=states, state="readonly", width=18).grid(row=0,column=3,sticky="ew",padx=(5,10))
            ttk.Label(filters, text="Período").grid(row=0,column=4,sticky="w")
            ttk.Entry(filters, textvariable=self.filter_period, width=10).grid(row=0,column=5,sticky="ew",padx=(5,10))
            ttk.Label(filters, text="Desde").grid(row=1,column=0,sticky="w",pady=(4,0))
            DateEntry(filters, self.filter_date_from).grid(row=1,column=1,sticky="ew",padx=(5,10),pady=(4,0))
            ttk.Label(filters, text="Hasta").grid(row=1,column=2,sticky="w",pady=(4,0))
            DateEntry(filters, self.filter_date_to).grid(row=1,column=3,sticky="ew",padx=(5,10),pady=(4,0))
            ttk.Label(filters, text={"tareas":"Área", "vencimientos":"Impuesto / trámite", "honorarios":"Concepto", "documentacion":"Documento"}[module]).grid(row=1,column=4,sticky="w",pady=(4,0))
            ttk.Entry(filters, textvariable=self.filter_text).grid(row=1,column=5,sticky="ew",padx=(5,10),pady=(4,0))
            if module == "vencimientos":
                ttk.Label(filters, text="Organismo").grid(row=2,column=0,sticky="w",pady=(4,0))
                ttk.Combobox(filters, textvariable=self.filter_organism, values=("Todos", "ARCA", "ARBA", "AGIP", "COMARB", "Municipio", "IGJ", "DPPJ", "Ministerio de Trabajo", "Banco", "Estudio", "Otro"), state="readonly").grid(row=2,column=1,sticky="ew",padx=(5,10),pady=(4,0))
            if module == "honorarios":
                ttk.Label(filters, text="Presupuesto").grid(row=2,column=0,sticky="w",pady=(4,0))
                ttk.Entry(filters, textvariable=self.filter_budget).grid(row=2,column=1,sticky="ew",padx=(5,10),pady=(4,0))
            if module == "tareas":
                ttk.Label(filters, text="Prioridad").grid(row=2,column=0,sticky="w",pady=(4,0))
                ttk.Combobox(filters, textvariable=self.filter_priority, values=("Todos", "Baja", "Media", "Alta", "Urgente"), state="readonly").grid(row=2,column=1,sticky="ew",padx=(5,10),pady=(4,0))
                ttk.Label(filters, text="Tipo de tarea").grid(row=2,column=2,sticky="w",pady=(4,0))
                ttk.Entry(filters, textvariable=self.filter_type).grid(row=2,column=3,sticky="ew",padx=(5,10),pady=(4,0))
                ttk.Label(filters, text="Vence desde").grid(row=3,column=0,sticky="w",pady=(4,0))
                DateEntry(filters, self.filter_due_from).grid(row=3,column=1,sticky="ew",padx=(5,10),pady=(4,0))
                ttk.Label(filters, text="Vence hasta").grid(row=3,column=2,sticky="w",pady=(4,0))
                DateEntry(filters, self.filter_due_to).grid(row=3,column=3,sticky="ew",padx=(5,10),pady=(4,0))
            ttk.Button(filters, text="Aplicar filtros", command=self.refresh).grid(row=3 if module=="tareas" else 2,column=6,sticky="e",pady=(4,0))
            filters.columnconfigure(1,weight=1);filters.columnconfigure(3,weight=1)

        self.notebook = ttk.Notebook(self) if module in ("tareas", "vencimientos", "honorarios") else None
        if self.notebook:
            self.notebook.pack(fill="both", expand=True)
        table = ttk.Frame(self.notebook or self)
        if self.notebook:
            self.notebook.add(table, text="Listado completo")
            grouped = ttk.Frame(self.notebook)
            self.notebook.add(grouped, text=f"Clientes con todos sus {'vencimientos' if module == 'vencimientos' else 'honorarios'}")
        else:
            table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, show="headings")
        yscroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.group_tree = None
        if self.notebook:
            self.group_tree = ttk.Treeview(grouped, show="tree headings")
            gy = ttk.Scrollbar(grouped, orient="vertical", command=self.group_tree.yview)
            gx = ttk.Scrollbar(grouped, orient="horizontal", command=self.group_tree.xview)
            self.group_tree.configure(yscrollcommand=gy.set, xscrollcommand=gx.set)
            self.group_tree.grid(row=0, column=0, sticky="nsew")
            gy.grid(row=0, column=1, sticky="ns"); gx.grid(row=1, column=0, sticky="ew")
            grouped.rowconfigure(0, weight=1); grouped.columnconfigure(0, weight=1)
            self.group_tree.bind("<Double-1>", lambda _event: self.edit())
        if module in ("documentacion", "tareas", "vencimientos", "honorarios"):
            self.tree.bind("<Double-1>", lambda _event: self.edit())
            make_tree_sortable(self.tree, {"importe", "importe_pagado", "saldo_pendiente"})
        self.refresh()

    def import_arca(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self, title="Importar vencimientos ARCA",
            filetypes=(("Excel o CSV", "*.xls *.xlsx *.csv"), ("Todos", "*.*")),
        )
        if not filename:
            return
        try:
            preview = self.app.arca_import_service.preview_deadlines(Path(filename))
            if preview.get("missing"):
                dialog=DeadlineMappingDialog(self,preview["missing"],preview["headers"]);self.wait_window(dialog)
                if dialog.result is None:return
                preview=self.app.arca_import_service.preview_deadlines(Path(filename),dialog.result)
            DeadlineImportPreviewDialog(self, self.app, preview, self.refresh)
        except Exception as error:
            messagebox.showerror("No se pudo leer el archivo", str(error), parent=self)

    def refresh(self) -> None:
        rows = self.app.administrative_service.list(self.module)
        if self.module in ("documentacion", "tareas", "vencimientos", "honorarios"):
            selected_client = self.filter_client_map.get(self.filter_client.get())
            period = self.filter_period.get().strip().replace("/", "-")
            if len(period) == 7 and period[2] == "-":
                period = f"{period[3:]}-{period[:2]}"
            rows = [row for row in rows if (selected_client is None or row.get("cliente_id") == selected_client)]
            selected_state = self.filter_state.get()
            if selected_state == "Obligatorios":
                rows = [row for row in rows if str(row.get("obligatorio", "")).casefold() == "sí"]
            elif selected_state == "Próximos 30 días":
                today = date.today().isoformat(); end = (date.today()+timedelta(days=30)).isoformat()
                rows = [row for row in rows if str(row.get("estado", "")).casefold() not in ("pagado", "cumplido", "no corresponde") and today <= str(row.get("fecha_vencimiento") or "") <= end]
            elif selected_state in ("Vencidos por fecha", "Vencidas por fecha"):
                today = date.today().isoformat()
                closed = ("pagado", "cumplido", "cumplimentada", "cancelada", "no corresponde")
                rows = [row for row in rows if str(row.get("estado", "")).casefold() not in closed and str(row.get("fecha_vencimiento") or "") < today]
            else:
                rows = [row for row in rows if selected_state == "Todos" or str(row.get("estado", "")).casefold() == selected_state.casefold()]
            rows = [row for row in rows if (not period or row.get("periodo") == period)]
            if self.module == "honorarios" and self.filter_budget.get().strip():
                budget_term = self.filter_budget.get().strip().casefold()
                rows = [row for row in rows if budget_term in str(row.get("numero_presupuesto") or "").casefold()]
            if self.module == "vencimientos" and self.filter_organism.get() != "Todos":
                rows = [row for row in rows if row.get("organismo") == self.filter_organism.get()]
            if self.module == "tareas" and self.filter_priority.get() != "Todos":
                rows = [row for row in rows if str(row.get("prioridad", "")).casefold() == self.filter_priority.get().casefold()]
            term = self.filter_text.get().strip().casefold()
            searchable = {
                "tareas": ("modulo", "descripcion"),
                "vencimientos": ("impuesto", "tipo_vencimiento"),
                "honorarios": ("servicio", "tipo_registro"),
                "documentacion": ("tipo_documento", "observaciones"),
            }[self.module]
            if term:
                rows = [row for row in rows if term in " ".join(str(row.get(key, "")) for key in searchable).casefold()]
            if self.module == "tareas" and self.filter_type.get().strip():
                type_term = self.filter_type.get().strip().casefold()
                rows = [row for row in rows if type_term in str(row.get("titulo", "")).casefold()]
            try:
                start = normalize_date(self.filter_date_from.get()) if self.filter_date_from.get().strip() else ""
                end = normalize_date(self.filter_date_to.get()) if self.filter_date_to.get().strip() else ""
                due_start = normalize_date(self.filter_due_from.get()) if self.module == "tareas" and self.filter_due_from.get().strip() else ""
                due_end = normalize_date(self.filter_due_to.get()) if self.module == "tareas" and self.filter_due_to.get().strip() else ""
            except ValueError as error:
                messagebox.showerror("Fecha inválida", str(error), parent=self)
                return
            if start and end and start > end:
                messagebox.showerror("Rango inválido", "La fecha Desde no puede ser posterior a Hasta.", parent=self)
                return
            date_key = "fecha_inicio" if self.module == "tareas" else ("fecha_solicitud" if self.module == "documentacion" else "fecha_vencimiento")
            if start: rows = [row for row in rows if str(row.get(date_key) or "") >= start]
            if end: rows = [row for row in rows if str(row.get(date_key) or "") <= end]
            if self.module == "tareas":
                if due_start: rows = [row for row in rows if str(row.get("fecha_vencimiento") or "") >= due_start]
                if due_end: rows = [row for row in rows if str(row.get("fecha_vencimiento") or "") <= due_end]
        self.current_rows = rows
        if self.module == "vencimientos":
            visible = ["cliente_nombre", "impuesto", "organismo", "periodo", "fecha_vencimiento", "tipo_vencimiento", "estado", "fecha_cumplimiento", "fecha_pago", "observaciones"]
        elif self.module == "honorarios":
            visible = ["cliente_nombre", "numero_presupuesto", "periodo", "servicio", "importe", "importe_pagado", "saldo_pendiente", "estado", "fecha_vencimiento", "fecha_cobro", "medio_pago", "comprobante_emitido", "tipo_comprobante", "numero_comprobante", "observaciones"]
        elif self.module == "tareas":
            visible = ["cliente_nombre", "modulo", "titulo", "descripcion", "fecha_inicio", "fecha_vencimiento", "estado", "prioridad", "medio", "documentacion_vinculada", "proximo_paso", "observaciones", "fecha_cumplimiento"]
        elif self.module == "documentacion":
            visible = ["cliente_nombre", "periodo", "tipo_documento", "estado", "fecha_solicitud", "fecha_recepcion", "obligatorio", "archivo_link", "observaciones"]
        else:
            keys = list(rows[0].keys()) if rows else ["id", "cliente_nombre", "estado"]
            visible = [key for key in keys if key not in ("id", "cliente_id", "responsable", "actualizado_en")][:9]
        labels = {
            "cliente_nombre": "Cliente", "modulo": "Área", "titulo": "Tipo de tarea",
            "fecha_inicio": "Fecha", "fecha_vencimiento": "Vencimiento",
            "fecha_cumplimiento": "Cumplimiento", "fecha_pago": "Pago",
            "importe": "Facturado", "importe_pagado": "Cobrado", "saldo_pendiente": "Saldo",
            "servicio": "Concepto", "medio_pago": "Medio de cobro",
            "documentacion_vinculada": "Documentación vinculada", "proximo_paso": "Próximo paso",
        }
        self.tree.configure(columns=visible)
        for key in visible:
            self.tree.heading(key, text=labels.get(key, key.replace("_", " ").title()))
            anchor = "e" if key in ("importe", "importe_pagado", "saldo_pendiente") else ("center" if key.startswith("fecha") or key in ("periodo", "estado", "prioridad") else "w")
            self.tree.column(key, width=180 if key in ("cliente_nombre", "impuesto", "servicio", "descripcion", "observaciones", "documentacion_vinculada", "proximo_paso") else 120, minwidth=85, anchor=anchor, stretch=True)
        make_tree_sortable(self.tree, {"importe", "importe_pagado", "saldo_pendiente"})
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            values = []
            for key in visible:
                value = row.get(key, "")
                if key.startswith("fecha"):
                    value = display_date(value)
                elif key == "periodo":
                    value = display_period(value)
                elif key in ("importe", "importe_pagado", "saldo_pendiente"):
                    value = money(value)
                values.append(value)
            tag = self._status_tag(str(row.get("estado", "")))
            self.tree.insert("", "end", iid=str(row["id"]), values=values, tags=(tag,))
        for tag, color in (("green", "#DCFCE7"), ("yellow", "#FEF3C7"), ("blue", "#DBEAFE"), ("orange", "#FFEDD5"), ("red", "#FEE2E2"), ("gray", "#E5E7EB")):
            self.tree.tag_configure(tag, background=color)
        if self.group_tree is not None:
            grouped_columns = tuple(key for key in visible if key != "cliente_nombre")
            self.group_tree.configure(columns=grouped_columns)
            self.group_tree.heading("#0", text="Cliente")
            self.group_tree.column("#0", width=230, anchor="w")
            for key in grouped_columns:
                self.group_tree.heading(key, text=labels.get(key, key.replace("_", " ").title()))
                self.group_tree.column(key, width=130, minwidth=85, anchor="e" if key in ("importe", "importe_pagado", "saldo_pendiente") else "center" if key.startswith("fecha") or key in ("periodo", "estado") else "w")
            for item in self.group_tree.get_children():
                self.group_tree.delete(item)
            parents = {}
            for row in rows:
                name = row.get("cliente_nombre") or "Sin cliente"
                if name not in parents:
                    parents[name] = self.group_tree.insert("", "end", text=name, open=True)
                values = []
                for key in grouped_columns:
                    value = row.get(key, "")
                    if key.startswith("fecha"): value = display_date(value)
                    elif key == "periodo": value = display_period(value)
                    elif key in ("importe", "importe_pagado", "saldo_pendiente"): value = money(value)
                    values.append(value)
                tag = self._status_tag(str(row.get("estado", "")))
                self.group_tree.insert(parents[name], "end", iid=f"record-{row['id']}", values=values, tags=(tag,))
            for tag, color in (("green", "#DCFCE7"), ("yellow", "#FEF3C7"), ("blue", "#DBEAFE"), ("orange", "#FFEDD5"), ("red", "#FEE2E2"), ("gray", "#E5E7EB")):
                self.group_tree.tag_configure(tag, background=color)

    @staticmethod
    def _status_tag(status: str) -> str:
        value = status.casefold()
        if value in ("cumplimentada", "cumplido", "pagado", "cobrado"): return "green"
        if value in ("pendiente", "cobro parcial"): return "yellow"
        if value in ("en proceso", "bonificado"): return "blue"
        if value in ("esperando cliente", "esperando organismo"): return "orange"
        if value in ("vencido", "vencida"): return "red"
        return "gray"

    def _selected_id(self) -> int | None:
        if self.notebook and self.notebook.index("current") == 1 and self.group_tree:
            selected = self.group_tree.selection()
            if selected and selected[0].startswith("record-"):
                return int(selected[0].split("-", 1)[1])
            return None
        return selected_tree_id(self.tree)

    def _selected_row(self) -> dict | None:
        record_id = self._selected_id()
        return next((row for row in self.current_rows if int(row["id"]) == record_id), None) if record_id else None

    def open_ledger(self) -> None:
        row = self._selected_row()
        if not row or not row.get("cliente_id"):
            messagebox.showinfo("Seleccionar registro", "Seleccioná un registro vinculado a un cliente.", parent=self)
            return
        ClientLedgerDialog(self, self.app, int(row["cliente_id"]))

    def change_status(self, status: str) -> None:
        record_id = self._selected_id()
        if record_id is None:
            messagebox.showinfo("Seleccionar registro", "Seleccioná un registro de la tabla.", parent=self)
            return
        effective_date = None
        amount = None
        if status in ("Cumplimentada", "Cumplido", "Pagado", "Cobrado", "Cobro parcial", "Recibido"):
            entered = ask_date(self, "Fecha efectiva", "Seleccioná la fecha:", date.today())
            if entered is None: return
            try: effective_date = normalize_date(entered)
            except ValueError as error:
                messagebox.showerror("Fecha inválida", str(error), parent=self); return
        if status == "Cobro parcial":
            entered = simpledialog.askstring("Importe cobrado", "Ingresá el importe cobrado:", parent=self)
            if entered is None: return
            try: amount = float(entered.replace(".", "").replace(",", "."))
            except ValueError:
                messagebox.showerror("Importe inválido", "Ingresá un importe válido.", parent=self); return
        try:
            self.app.administrative_service.update_status(self.module, record_id, status, effective_date, amount)
            self.refresh()
        except Exception as error:
            messagebox.showerror("No se pudo actualizar", str(error), parent=self)

    def export(self, format_name: str) -> None:
        extension = f".{format_name}"
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, initialfile=f"{DEFINITIONS[self.module][0]}_{date.today().isoformat()}{extension}", filetypes=((format_name.upper(), f"*{extension}"),))
        if not filename: return
        title = DEFINITIONS[self.module][0]
        filter_text = f"Cliente: {self.filter_client.get()} | Estado: {self.filter_state.get()} | Período: {self.filter_period.get() or 'Todos'}"
        method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
        hidden = {"id", "cliente_id", "responsable", "actualizado_en", "creado_en"}
        rows = [{key: value for key, value in row.items() if key not in hidden} for row in self.current_rows]
        method(Path(filename), title, rows, filter_text)
        messagebox.showinfo("Exportación terminada", f"Se creó:\n{filename}", parent=self)

    def add(self) -> None:
        RecordDialog(self, self.app, self.module, self.refresh)

    def edit(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            messagebox.showinfo("Seleccionar registro", "Seleccioná un registro de la tabla.")
            return
        RecordDialog(self, self.app, self.module, self.refresh, record_id)

    def delete(self) -> None:
        record_id = self._selected_id()
        if record_id is None:
            messagebox.showinfo("Seleccionar registro", "Seleccioná un registro de la tabla.")
            return
        nouns = {
            "documentacion": "el documento",
            "tareas": "la tarea",
            "vencimientos": "el vencimiento",
            "honorarios": "el honorario",
        }
        noun = nouns[self.module]
        if not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Está seguro que desea eliminar {noun}? Esta acción no se puede deshacer.",
            parent=self,
        ):
            return
        try:
            deleted = self.app.administrative_service.delete(self.module, record_id)
            self.refresh()
            if not deleted:
                messagebox.showwarning(
                    "Registro inexistente", "El registro ya había sido eliminado.", parent=self
                )
        except Exception as error:
            messagebox.showerror("No se pudo eliminar", str(error), parent=self)


class DeadlineMappingDialog(tk.Toplevel):
    def __init__(self,parent,missing:list[str],headers:list[str]) -> None:
        super().__init__(parent);self.result=None;self.title("Mapear columnas de vencimientos");fit_window(self,620,420);self.transient(parent.winfo_toplevel());self.grab_set();body=ttk.Frame(self,padding=16);body.pack(fill="both",expand=True);ttk.Label(body,text="Mapeo manual de columnas",style="Title.TLabel").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,10));self.vars={}
        for index,field in enumerate(missing,1):self.vars[field]=tk.StringVar();ttk.Label(body,text=field.replace("_"," ").title()).grid(row=index,column=0,sticky="w",pady=4);ttk.Combobox(body,textvariable=self.vars[field],values=headers,state="readonly").grid(row=index,column=1,sticky="ew",padx=8,pady=4)
        body.columnconfigure(1,weight=1);ttk.Button(body,text="Cancelar",command=self.destroy).grid(row=len(missing)+1,column=0,pady=12);ttk.Button(body,text="Aplicar mapeo",style="Primary.TButton",command=lambda:self.accept(headers)).grid(row=len(missing)+1,column=1,sticky="e",pady=12)
    def accept(self,headers):
        if any(not value.get() for value in self.vars.values()):messagebox.showerror("Mapeo incompleto","Seleccioná todas las columnas.",parent=self);return
        self.result={field:headers.index(value.get()) for field,value in self.vars.items()};self.destroy()


class DeadlineImportPreviewDialog(tk.Toplevel):
    def __init__(self, parent, app, preview: dict, callback) -> None:
        super().__init__(parent)
        self.app = app; self.preview = preview; self.callback = callback
        self.title("Vista previa de vencimientos ARCA importados")
        fit_window(self, 1220, 700); self.transient(parent.winfo_toplevel()); self.grab_set()
        body = ttk.Frame(self, padding=14); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Vista previa de vencimientos ARCA", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"Hoja: {preview['sheet']} · encabezado: fila {preview['header_row']} · detectados: {len(preview['records'])} · errores: {len(preview['errors'])}", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 8))
        frame=ttk.Frame(body); frame.pack(fill="both",expand=True)
        columns=("accion","cliente","cuit","impuesto","organismo","periodo","vencimiento","tipo","estado","importe","confianza")
        self.tree=ttk.Treeview(frame,columns=columns,show="headings",selectmode="browse")
        labels=("Acción","Cliente","CUIT","Impuesto / obligación","Organismo","Período","Vencimiento","Tipo","Estado","Importe","Confianza")
        widths=(85,170,100,210,80,80,95,150,90,100,90)
        for column,label,width in zip(columns,labels,widths): self.tree.heading(column,text=label);self.tree.column(column,width=width,minwidth=60)
        sy=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview);sx=ttk.Scrollbar(frame,orient="horizontal",command=self.tree.xview);self.tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.tree.grid(row=0,column=0,sticky="nsew");sy.grid(row=0,column=1,sticky="ns");sx.grid(row=1,column=0,sticky="ew");frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        for index,row in enumerate(preview["records"]):
            self.tree.insert("","end",iid=str(index),values=(row["accion"],row["cliente"] or "Cliente no encontrado",row["cuit"],row["impuesto"],row["organismo"],display_period(row["periodo"]),display_date(row["fecha_vencimiento"]),row["tipo_vencimiento"],row["estado"],money(row["importe"]),row["confianza"]))
        actions=ttk.Frame(body);actions.pack(fill="x",pady=(10,0))
        self.duplicate_action=tk.StringVar(value="skip");ttk.Label(actions,text="Duplicados").pack(side="left");ttk.Combobox(actions,textvariable=self.duplicate_action,values=("skip","replace","import"),state="readonly",width=10).pack(side="left",padx=(4,10))
        ttk.Button(actions,text="Alternar importar / no importar",command=self.toggle).pack(side="left")
        ttk.Button(actions,text="Editar seleccionado",command=self.edit).pack(side="left",padx=6)
        ttk.Button(actions,text="Cancelar",command=self.destroy).pack(side="right")
        ttk.Button(actions,text="Confirmar importación",style="Primary.TButton",command=self.confirm).pack(side="right",padx=6)

    def selected(self) -> dict | None:
        selection=self.tree.selection(); return self.preview["records"][int(selection[0])] if selection else None

    def redraw(self, index: int) -> None:
        row=self.preview["records"][index]
        self.tree.item(str(index),values=(row["accion"],row["cliente"] or "Cliente no encontrado",row["cuit"],row["impuesto"],row["organismo"],display_period(row["periodo"]),display_date(row["fecha_vencimiento"]),row["tipo_vencimiento"],row["estado"],money(row["importe"]),row["confianza"]))

    def toggle(self) -> None:
        selection=self.tree.selection()
        if not selection:return
        index=int(selection[0]);row=self.preview["records"][index];row["accion"]="No importar" if row["accion"]=="Importar" else "Importar";self.redraw(index)

    def edit(self) -> None:
        selection=self.tree.selection()
        if not selection:return
        index=int(selection[0]); DeadlineRowDialog(self,self.app,self.preview["records"][index],lambda:self.redraw(index))

    def confirm(self) -> None:
        try:
            result=self.app.arca_import_service.import_deadlines(self.preview,self.duplicate_action.get())
            self.callback();messagebox.showinfo("Importación terminada",f"Importados: {result['imported']}\nDuplicados: {result['duplicates']}\nA revisar: {result['review']}\nCon error: {result['rejected']}",parent=self);self.destroy()
        except Exception as error:messagebox.showerror("No se pudo importar",str(error),parent=self)


class DeadlineRowDialog(tk.Toplevel):
    def __init__(self,parent,app,row:dict,callback) -> None:
        super().__init__(parent);self.app=app;self.row=row;self.callback=callback;self.title("Editar vencimiento antes de importar");fit_window(self,650,620);self.transient(parent);self.grab_set()
        body=ScrollableFrame(self,padding=16);body.pack(fill="both",expand=True);frame=body.content
        clients=app.client_service.list_clients(include_inactive=True);self.clients={f"{item['nombre_razon_social']} · {item['cuit_cuil']}":item["id"] for item in clients}
        selected=next((label for label,value in self.clients.items() if value==row.get("client_id")),next(iter(self.clients),""));self.vars={"cliente":tk.StringVar(value=selected)}
        fields=(("cliente","Cliente"),("impuesto","Impuesto"),("organismo","Organismo"),("periodo","Período AAAA-MM"),("fecha_vencimiento","Fecha AAAA-MM-DD"),("tipo_vencimiento","Tipo"),("estado","Estado"),("importe","Importe"),("saldo","Saldo"),("observaciones","Observaciones"))
        for i,(key,label) in enumerate(fields):
            ttk.Label(frame,text=label).grid(row=i,column=0,sticky="w",pady=4)
            if key=="cliente": widget=ttk.Combobox(frame,textvariable=self.vars[key],values=tuple(self.clients),state="readonly");self.client_combo=widget
            else:self.vars[key]=tk.StringVar(value=str(row.get(key,"")));widget=ttk.Entry(frame,textvariable=self.vars[key])
            widget.grid(row=i,column=1,sticky="ew",padx=8,pady=4)
        frame.columnconfigure(1,weight=1);ttk.Button(frame,text="Crear cliente con CUIT detectado",command=self.create_client).grid(row=len(fields),column=0,sticky="w",pady=10);ttk.Button(frame,text="Guardar cambios",style="Primary.TButton",command=self.save).grid(row=len(fields),column=1,sticky="e",pady=10)

    def create_client(self):
        try:
            if not self.row.get("cuit"):raise ValueError("La fila no contiene CUIT para crear el cliente.")
            client_id=self.app.client_service.save(Client(self.row.get("cliente") or f"Cliente {self.row['cuit']}",self.row["cuit"]),FiscalProfile(),None);label=next(label for label,value in self.clients.items() if value==client_id) if client_id in self.clients.values() else f"{self.row.get('cliente') or 'Cliente'} · {self.row['cuit']}";self.clients[label]=client_id;self.client_combo.configure(values=tuple(self.clients));self.vars["cliente"].set(label);messagebox.showinfo("Cliente creado","El cliente mínimo fue creado y vinculado a esta fila.",parent=self)
        except Exception as error:messagebox.showerror("No se pudo crear",str(error),parent=self)

    def save(self):
        try:
            label=self.vars["cliente"].get();self.row["client_id"]=self.clients.get(label);self.row["cliente"]=label.split(" · ")[0] if label else ""
            for key in ("impuesto","organismo","periodo","fecha_vencimiento","tipo_vencimiento","estado","observaciones"):self.row[key]=self.vars[key].get().strip()
            self.row["importe"]=float(self.vars["importe"].get().replace(".","").replace(",",".") or 0);self.row["saldo"]=float(self.vars["saldo"].get().replace(".","").replace(",",".") or 0);self.row["confianza"]="Alta" if self.row["client_id"] else "A revisar";self.callback();self.destroy()
        except Exception as error:messagebox.showerror("Dato inválido",str(error),parent=self)


class AccountingImportHistoryDialog(tk.Toplevel):
    def __init__(self,parent,app,source:str="") -> None:
        super().__init__(parent);self.app=app;self.source=source;self.title("Historial de importaciones");fit_window(self,1050,560);self.transient(parent.winfo_toplevel());self.grab_set();body=ttk.Frame(self,padding=14);body.pack(fill="both",expand=True)
        ttk.Label(body,text="Historial de importaciones contables",style="Title.TLabel").pack(anchor="w");actions=ttk.Frame(body);actions.pack(fill="x",pady=7);ttk.Button(actions,text="Exportar Excel",command=lambda:self.export("xlsx")).pack(side="left");ttk.Button(actions,text="Exportar PDF",command=lambda:self.export("pdf")).pack(side="left",padx=5)
        holder=ttk.Frame(body);holder.pack(fill="both",expand=True);columns=("cliente","fuente","archivo","fecha","leidas","importadas","duplicadas","revisar","error","vigencia","estado","observaciones");self.tree=ttk.Treeview(holder,columns=columns,show="headings")
        for c in columns:self.tree.heading(c,text=c.replace("_"," ").title());self.tree.column(c,width=120 if c not in ("archivo","observaciones") else 210)
        sy=ttk.Scrollbar(holder,orient="vertical",command=self.tree.yview);sx=ttk.Scrollbar(holder,orient="horizontal",command=self.tree.xview);self.tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);self.tree.grid(row=0,column=0,sticky="nsew");sy.grid(row=0,column=1,sticky="ns");sx.grid(row=1,column=0,sticky="ew");holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.rows=app.arca_import_service.history(source)
        for row in self.rows:self.tree.insert("","end",values=(row["cliente"],row["fuente"],row["archivo"],display_date(row["fecha_importacion"]),row["filas_leidas"],row["filas_importadas"],row["filas_duplicadas"],row["filas_revisar"],row["filas_error"],display_date(row["vigencia_detectada"]),row["estado"],row["observaciones"]))
    def export(self,format_name:str):
        extension=f".{format_name}";filename=filedialog.asksaveasfilename(parent=self,defaultextension=extension,filetypes=((format_name.upper(),f"*{extension}"),),initialfile=f"Historial {self.source or 'importaciones'}{extension}")
        if not filename:return
        try:
            method=self.app.report_service.export_table_excel if format_name=="xlsx" else self.app.report_service.export_table_pdf;method(Path(filename),"Historial de importaciones",self.rows,self.source or "Todas")
            messagebox.showinfo("Exportación terminada",f"Se creó:\n{filename}",parent=self)
        except Exception as error:messagebox.showerror("No se pudo exportar",str(error),parent=self)


class RecordDialog(tk.Toplevel):
    def __init__(
        self, parent, app, module: str, callback, record_id: int | None = None
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.module = module
        self.callback = callback
        self.record_id = record_id
        self.title(("Modificar " if record_id else "Agregar ") + DEFINITIONS[module][0])
        fit_window(self, 700, 740)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        footer = ttk.Frame(self, padding=(14, 10))
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            footer, text="Guardar cambios" if record_id else "Guardar",
            style="Primary.TButton", command=self.save,
        ).pack(side="right", padx=8)
        scroll = ScrollableFrame(self, padding=18, horizontal=True)
        scroll.pack(side="top", fill="both", expand=True)
        body = scroll.content
        clients = app.client_service.list_clients(include_inactive=True)
        self.clients = {
            f"{client['nombre_razon_social']} · {client['cuit_cuil']}": client["id"]
            for client in clients
        }
        if module == "tareas":
            self.clients = {"General": None, **self.clients}
        self.vars = {"cliente": tk.StringVar()}
        self.multi_widgets: dict[str, tk.Listbox] = {}
        ttk.Label(body, text="Cliente").grid(row=0, column=0, sticky="w", pady=4)
        self.client_combo = ttk.Combobox(
            body,
            textvariable=self.vars["cliente"],
            values=tuple(self.clients),
            state="normal",
        )
        self.client_combo.grid(row=0, column=1, sticky="ew", padx=8)
        self.client_combo.bind("<KeyRelease>", self._filter_clients)
        self.client_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_budget_options())
        if self.clients:
            self.vars["cliente"].set(next(iter(self.clients)))
        for row, (key, label, kind) in enumerate(DEFINITIONS[module][1], 1):
            self.vars[key] = tk.StringVar()
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if kind == "budget":
                self.budget_combo = ttk.Combobox(body, textvariable=self.vars[key], values=("Sin presupuesto asociado",), state="readonly")
                self.budget_combo.grid(row=row, column=1, sticky="ew", padx=8)
                self.budget_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_budget())
                self.vars[key].set("Sin presupuesto asociado")
            elif kind == "date":
                DateEntry(body, self.vars[key]).grid(
                    row=row, column=1, sticky="ew", padx=8
                )
            elif isinstance(kind, tuple) and kind and kind[0] == "multi":
                options = kind[1:]
                widget = tk.Listbox(body, selectmode="multiple", exportselection=False, height=6)
                for option in options:
                    widget.insert("end", option)
                widget.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
                self.multi_widgets[key] = widget
                ttk.Label(body, text="Selección múltiple: Ctrl + clic", style="Subtitle.TLabel").grid(row=row, column=2, sticky="w")
            elif isinstance(kind, tuple):
                ttk.Combobox(
                    body, textvariable=self.vars[key], values=kind, state="readonly"
                ).grid(row=row, column=1, sticky="ew", padx=8)
                self.vars[key].set(kind[0])
            else:
                ttk.Entry(body, textvariable=self.vars[key]).grid(
                    row=row, column=1, sticky="ew", padx=8
                )
        body.columnconfigure(1, weight=1)
        if "responsable" in self.vars:
            self.vars["responsable"].set("NATALIA")
        self.budget_map: dict[str, dict] = {}
        self._update_budget_options()
        if record_id:
            self._load()

    def _update_budget_options(self) -> None:
        if self.module != "honorarios" or not hasattr(self, "budget_combo"):
            return
        client_id = self.clients.get(self.vars["cliente"].get())
        records = self.app.ledger_service.list_records(int(client_id), "servicio_presupuesto") if client_id else []
        self.budget_map = {
            str(row["datos"].get("numero_presupuesto") or row.get("numero_presupuesto") or ""): row["datos"]
            for row in records
            if row["datos"].get("numero_presupuesto") or row.get("numero_presupuesto")
        }
        self.budget_combo.configure(values=("Sin presupuesto asociado", *self.budget_map.keys()))

    def _apply_budget(self) -> None:
        budget = self.budget_map.get(self.vars.get("numero_presupuesto", tk.StringVar()).get())
        if not budget:
            return
        mapping = {
            "servicio": budget.get("descripcion") or budget.get("concepto", ""),
            "periodo": display_period(str(budget.get("periodo") or "")),
            "importe": budget.get("valor_presupuestado", ""),
            "saldo_pendiente": budget.get("saldo_pendiente") or budget.get("valor_presupuestado", ""),
            "fecha_vencimiento": display_date(str(budget.get("fecha_vencimiento") or "")),
        }
        for key, value in mapping.items():
            if key in self.vars:
                self.vars[key].set(str(value or ""))

    def _filter_clients(self, _event=None) -> None:
        term = self.vars["cliente"].get().casefold()
        self.client_combo.configure(
            values=tuple(label for label in self.clients if term in label.casefold())
        )

    def _load(self) -> None:
        record = self.app.administrative_service.get(self.module, self.record_id)
        if not record:
            messagebox.showerror("Registro inexistente", "El registro ya no existe.", parent=self)
            self.destroy()
            return
        client_label = next(
            (label for label, value in self.clients.items() if value == record.get("cliente_id")),
            next(iter(self.clients), ""),
        )
        self.vars["cliente"].set(client_label)
        self._update_budget_options()
        for key, _label, kind in DEFINITIONS[self.module][1]:
            value = record.get(key) or ""
            if key in self.multi_widgets:
                selected = {item.strip() for item in str(value).split(",")}
                widget = self.multi_widgets[key]
                for index in range(widget.size()):
                    if widget.get(index) in selected:
                        widget.selection_set(index)
            elif kind == "date":
                self.vars[key].set(display_date(str(value)))
            elif key == "periodo":
                self.vars[key].set(display_period(str(value)))
            else:
                self.vars[key].set(str(value))

    def save(self) -> None:
        try:
            data = {key: variable.get().strip() for key, variable in self.vars.items()}
            client_label = data.pop("cliente")
            if client_label not in self.clients:
                raise ValueError("Debe seleccionar un cliente.")
            data["cliente_id"] = self.clients.get(client_label)
            for key, widget in self.multi_widgets.items():
                data[key] = ", ".join(widget.get(index) for index in widget.curselection())
                if not data[key]:
                    raise ValueError(f"Debe seleccionar al menos una opción en {key.replace('_', ' ')}.")
            for key in [key for key in data if key.startswith("fecha_") and data[key]]:
                data[key] = normalize_date(data[key])
            if self.record_id:
                self.app.administrative_service.update(
                    self.module, self.record_id, data
                )
            else:
                self.app.administrative_service.create(self.module, data)
            self.callback()
            self.destroy()
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error), parent=self)
