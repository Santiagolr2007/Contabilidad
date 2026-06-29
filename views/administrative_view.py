from __future__ import annotations

import tkinter as tk
import os
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from utils.formatters import display_date, display_period, money, normalize_date

from .common import ScrollableFrame, fit_window, selected_tree_id
from .date_widgets import DateEntry


DEFINITIONS = {
    "documentacion": (
        "Documentación y tareas",
        (
            ("periodo", "Período", "text"),
            ("tipo_documento", "Documento", "text"),
            ("estado", "Estado", ("Solicitada", "Recibida", "Incompleta", "Observada", "Aprobada")),
            ("fecha_solicitud", "Fecha solicitud", "date"),
            ("fecha_recepcion", "Fecha recepción", "date"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "tareas": (
        "Tareas y trabajos",
        (
            ("modulo", "Módulo", "text"),
            ("periodo", "Período", "text"),
            ("titulo", "Título", "text"),
            ("descripcion", "Descripción", "text"),
            ("responsable", "Responsable", "text"),
            ("fecha_inicio", "Fecha inicio", "date"),
            ("fecha_vencimiento", "Vencimiento", "date"),
            ("fecha_finalizacion", "Finalización", "date"),
            ("estado", "Estado", ("pendiente", "esperando documentación", "en proceso", "para revisar", "finalizado", "facturado", "cobrado", "archivado")),
            ("prioridad", "Prioridad", ("baja", "media", "alta")),
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
            ("estado", "Estado", ("pendiente", "presentado", "pagado", "vencido")),
            ("responsable", "Responsable", "text"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "honorarios": (
        "Honorarios",
        (
            ("servicio", "Servicio", "text"),
            ("periodo", "Período MM/AAAA", "text"),
            ("importe", "Importe", "text"),
            ("estado", "Estado", ("pendiente de facturar", "facturado", "pendiente de cobro", "cobrado parcial", "cobrado total", "vencido")),
            ("fecha_emision", "Fecha emisión", "date"),
            ("fecha_cobro", "Fecha cobro", "date"),
            ("medio_pago", "Medio de pago", "text"),
            ("saldo_pendiente", "Saldo pendiente", "text"),
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
        if module in ("tareas", "vencimientos", "honorarios"):
            ttk.Button(toolbar, text="Modificar", command=self.edit).pack(
                side="left", padx=(8, 0)
            )
            ttk.Button(toolbar, text="Eliminar", command=self.delete).pack(
                side="left", padx=(8, 0)
            )
        if module in ("vencimientos", "honorarios"):
            ttk.Button(toolbar, text="Exportar Excel", command=lambda: self.export("xlsx")).pack(side="left", padx=(8,0))
            ttk.Button(toolbar, text="Exportar PDF", command=lambda: self.export("pdf")).pack(side="left", padx=(5,0))
            ttk.Button(toolbar, text="Imprimir", command=lambda: self.export("pdf", True)).pack(side="left", padx=(5,0))
        ttk.Button(toolbar, text="Actualizar", command=self.refresh).pack(side="right")

        self.filter_state = tk.StringVar(value="Todos")
        self.filter_client = tk.StringVar(value="Todos")
        self.filter_period = tk.StringVar()
        self.filter_type = tk.StringVar(value="Todos")
        self.filter_organism = tk.StringVar(value="Todos")
        clients = app.client_service.list_clients(include_inactive=True)
        self.filter_client_map = {"Todos": None, **{
            f"{row['nombre_razon_social']} · {row['cuit_cuil']}": int(row["id"])
            for row in clients
        }}
        if module in ("vencimientos", "honorarios"):
            filters = ttk.Frame(self)
            filters.pack(fill="x", pady=(0, 8))
            ttk.Label(filters, text="Cliente").grid(row=0,column=0,sticky="w")
            ttk.Combobox(filters, textvariable=self.filter_client, values=tuple(self.filter_client_map), state="readonly", width=31).grid(row=0,column=1,sticky="ew",padx=(5,10))
            ttk.Label(filters, text="Estado").grid(row=0,column=2,sticky="w")
            states = ("Todos", "pendiente", "presentado", "pagado", "vencido", "Próximos 30 días", "Vencidos por fecha") if module == "vencimientos" else ("Todos", "pendiente de facturar", "facturado", "pendiente de cobro", "cobrado parcial", "cobrado total", "vencido")
            ttk.Combobox(filters, textvariable=self.filter_state, values=states, state="readonly", width=18).grid(row=0,column=3,sticky="ew",padx=(5,10))
            ttk.Label(filters, text="Período").grid(row=0,column=4,sticky="w")
            ttk.Entry(filters, textvariable=self.filter_period, width=10).grid(row=0,column=5,sticky="ew",padx=(5,10))
            if module == "vencimientos":
                ttk.Label(filters, text="Tipo").grid(row=1,column=0,sticky="w",pady=(4,0))
                ttk.Combobox(filters, textvariable=self.filter_type, values=("Todos", "Presentación", "Pago", "Renovación", "Control", "Otro"), state="readonly", width=14).grid(row=1,column=1,sticky="ew",padx=(5,10),pady=(4,0))
                ttk.Label(filters, text="Organismo").grid(row=1,column=2,sticky="w",pady=(4,0))
                ttk.Combobox(filters, textvariable=self.filter_organism, values=("Todos", "ARCA", "ARBA", "AGIP", "COMARB", "Municipio", "IGJ", "DPPJ", "Ministerio de Trabajo", "Banco", "Estudio", "Otro"), state="readonly", width=13).grid(row=1,column=3,sticky="ew",padx=(5,10),pady=(4,0))
            ttk.Button(filters, text="Aplicar", command=self.refresh).grid(row=1 if module=="vencimientos" else 0,column=6,sticky="e",pady=(4,0))
            filters.columnconfigure(1,weight=1);filters.columnconfigure(3,weight=1)

        self.notebook = ttk.Notebook(self) if module in ("vencimientos", "honorarios") else None
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
        if module in ("tareas", "vencimientos", "honorarios"):
            self.tree.bind("<Double-1>", lambda _event: self.edit())
        self.refresh()

    def refresh(self) -> None:
        rows = self.app.administrative_service.list(self.module)
        if self.module in ("vencimientos", "honorarios"):
            selected_client = self.filter_client_map.get(self.filter_client.get())
            period = self.filter_period.get().strip().replace("/", "-")
            if len(period) == 7 and period[2] == "-":
                period = f"{period[3:]}-{period[:2]}"
            rows = [row for row in rows if (selected_client is None or row.get("cliente_id") == selected_client)]
            selected_state = self.filter_state.get()
            if selected_state == "Próximos 30 días":
                today = date.today().isoformat(); end = (date.today()+timedelta(days=30)).isoformat()
                rows = [row for row in rows if row.get("estado") not in ("pagado","presentado") and today <= str(row.get("fecha_vencimiento") or "") <= end]
            elif selected_state == "Vencidos por fecha":
                today = date.today().isoformat(); rows = [row for row in rows if row.get("estado") not in ("pagado","presentado") and str(row.get("fecha_vencimiento") or "") < today]
            else:
                rows = [row for row in rows if (selected_state == "Todos" or row.get("estado") == selected_state)]
            rows = [row for row in rows if (not period or row.get("periodo") == period)]
            if self.module == "vencimientos" and self.filter_type.get() != "Todos":
                rows = [row for row in rows if self.filter_type.get().casefold() in str(row.get("tipo_vencimiento", "")).casefold()]
            if self.module == "vencimientos" and self.filter_organism.get() != "Todos":
                rows = [row for row in rows if row.get("organismo") == self.filter_organism.get()]
        self.current_rows = rows
        if self.module == "vencimientos":
            visible = ["cliente_nombre", "impuesto", "organismo", "periodo", "fecha_vencimiento", "tipo_vencimiento", "estado", "responsable", "observaciones"]
        elif self.module == "honorarios":
            visible = ["cliente_nombre", "servicio", "periodo", "importe", "estado", "fecha_emision", "fecha_cobro", "saldo_pendiente", "observaciones"]
        else:
            keys = list(rows[0].keys()) if rows else ["id", "cliente_nombre", "estado"]
            visible = [key for key in keys if key not in ("cliente_id", "descripcion", "observaciones")][:9]
        self.tree.configure(columns=visible)
        for key in visible:
            self.tree.heading(key, text=key.replace("_", " ").title())
            anchor = "e" if key in ("importe", "saldo_pendiente") else ("center" if key.startswith("fecha") or key in ("periodo", "estado") else "w")
            self.tree.column(key, width=145 if key in ("cliente_nombre", "impuesto", "servicio", "observaciones") else 115, anchor=anchor)
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
                elif key in ("importe", "saldo_pendiente"):
                    value = money(value)
                values.append(value)
            self.tree.insert(
                "", "end", iid=str(row["id"]), values=values
            )
        if self.group_tree is not None:
            grouped_columns = tuple(key for key in visible if key != "cliente_nombre")
            self.group_tree.configure(columns=grouped_columns)
            self.group_tree.heading("#0", text="Cliente")
            self.group_tree.column("#0", width=230, anchor="w")
            for key in grouped_columns:
                self.group_tree.heading(key, text=key.replace("_", " ").title())
                self.group_tree.column(key, width=120, anchor="e" if key in ("importe", "saldo_pendiente") else "center" if key.startswith("fecha") or key in ("periodo", "estado") else "w")
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
                    elif key in ("importe", "saldo_pendiente"): value = money(value)
                    values.append(value)
                self.group_tree.insert(parents[name], "end", iid=f"record-{row['id']}", values=values)

    def _selected_id(self) -> int | None:
        if self.notebook and self.notebook.index("current") == 1 and self.group_tree:
            selected = self.group_tree.selection()
            if selected and selected[0].startswith("record-"):
                return int(selected[0].split("-", 1)[1])
            return None
        return selected_tree_id(self.tree)

    def export(self, format_name: str, print_after: bool = False) -> None:
        extension = f".{format_name}"
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, initialfile=f"{DEFINITIONS[self.module][0]}_{date.today().isoformat()}{extension}", filetypes=((format_name.upper(), f"*{extension}"),))
        if not filename: return
        title = DEFINITIONS[self.module][0]
        filter_text = f"Cliente: {self.filter_client.get()} | Estado: {self.filter_state.get()} | Período: {self.filter_period.get() or 'Todos'}"
        method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
        method(Path(filename), title, self.current_rows, filter_text)
        if print_after:
            try: os.startfile(filename, "print")
            except OSError: messagebox.showinfo("PDF listo", f"Abrí e imprimí:\n{filename}", parent=self)
        else: messagebox.showinfo("Exportación terminada", f"Se creó:\n{filename}", parent=self)

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
        scroll = ScrollableFrame(self, padding=18)
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
        if self.clients:
            self.vars["cliente"].set(next(iter(self.clients)))
        for row, (key, label, kind) in enumerate(DEFINITIONS[module][1], 1):
            self.vars[key] = tk.StringVar()
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if kind == "date":
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
        if record_id:
            self._load()

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
