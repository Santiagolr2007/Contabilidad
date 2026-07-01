from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from utils.formatters import display_date, display_period, money

from .common import MetricCard, ScrollableFrame, fit_window, selected_tree_id
from .date_widgets import DateEntry, ask_date
from .theme import COLORS


class TwoRowNotebook(ttk.Frame):
    """Menú de secciones en dos filas para evitar pestañas comprimidas."""

    def __init__(self, parent, columns: int = 10) -> None:
        super().__init__(parent)
        self.columns = columns
        self.menu = ttk.Frame(self)
        self.menu.pack(fill="x", pady=(0, 8))
        self.pages: list[ttk.Frame] = []
        self.buttons: list[ttk.Button] = []
        self.current = 0

    def add(self, page: ttk.Frame, text: str) -> None:
        index = len(self.pages)
        self.pages.append(page)
        button = ttk.Button(
            self.menu,
            text=text,
            command=lambda selected=index: self.select(selected),
        )
        button.grid(
            row=index // self.columns,
            column=index % self.columns,
            sticky="ew",
            padx=2,
            pady=2,
        )
        self.menu.columnconfigure(index % self.columns, weight=1)
        self.buttons.append(button)
        if index == 0:
            self.select(0)

    def select(self, index: int) -> None:
        self.current = index
        for page in self.pages:
            page.pack_forget()
        self.pages[index].pack(fill="both", expand=True)
        for position, button in enumerate(self.buttons):
            button.configure(style="Primary.TButton" if position == index else "TButton")

    def tabs(self) -> tuple[ttk.Frame, ...]:
        return tuple(self.pages)

    def forget(self, page) -> None:
        if page not in self.pages:
            return
        index = self.pages.index(page)
        self.pages.pop(index).destroy()
        self.buttons.pop(index).destroy()
        for position, button in enumerate(self.buttons):
            button.grid_configure(row=position // self.columns, column=position % self.columns)
            button.configure(command=lambda selected=position: self.select(selected))
        if self.pages:
            self.select(min(index, len(self.pages) - 1))


class ClientLedgerDialog(tk.Toplevel):
    def __init__(self, parent, app, client_id: int) -> None:
        super().__init__(parent)
        self.app = app
        self.client_id = client_id
        self.title("Legajo integral del cliente")
        fit_window(self, 1320, 820, margin=30)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        top = ttk.Frame(self, padding=(16, 12))
        top.pack(fill="x")
        summary = app.ledger_service.summary(client_id)
        client = summary["client"]
        ttk.Label(top, text=client["nombre_razon_social"], style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"Legajo {client.get('legajo', '—')} · CUIT {client['cuit_cuil']}", style="Subtitle.TLabel").pack(side="left", padx=12)
        ttk.Button(top, text="Exportar legajo", style="Primary.TButton", command=self.export_full).pack(side="right")
        ttk.Button(top, text="Cerrar", command=self.destroy).pack(side="right", padx=8)
        self.notebook = TwoRowNotebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._summary_tab()
        self._data_tab()
        for section in ("servicio_presupuesto", "pagos"):
            self._records_tab(section)
        self._monotributo_tab()
        self._responsible_profile_tab()
        for section in (
            "relevamiento", "arca", "iibb_legajo", "municipal", "laboral",
            "bancos", "documentacion", "riesgos", "eventos", "vencimientos_legajo",
        ):
            self._records_tab(section)

    @staticmethod
    def _tree(parent, columns: tuple[str, ...], widths: dict[str, int]) -> ttk.Treeview:
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            tree.heading(column, text=column.replace("_", " ").title())
            anchor = "e" if any(term in column for term in ("importe", "saldo", "total")) else ("center" if any(term in column for term in ("fecha", "periodo", "estado", "vencimiento")) else "w")
            tree.column(column, width=widths.get(column, 130), minwidth=70, anchor=anchor)
        yscroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        return tree

    @staticmethod
    def _status_tag(status: str) -> str:
        value = status.casefold()
        if value in ("pagado", "cobrado", "cumplido", "cumplimentada", "ok", "activo", "recibido"): return "green"
        if value in ("pendiente", "cobro parcial", "pago parcial", "requiere actualización"): return "yellow"
        if value in ("en proceso", "bonificado", "solicitado"): return "blue"
        if value in ("esperando cliente", "esperando organismo", "incompleto"): return "orange"
        if value in ("vencido", "vencida", "urgente"): return "red"
        return "gray"

    def _summary_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text="Resumen")
        summary = self.app.ledger_service.summary(self.client_id)
        client = summary["client"]
        ttk.Label(
            frame,
            text=(
                f"Legajo {client.get('legajo', '—')} · {client['nombre_razon_social']} · CUIT {client['cuit_cuil']} · "
                f"{summary['tipo_cliente']} · {str(client.get('regimen_principal') or '').replace('_', ' ').title()}\n"
                f"Servicio: {summary['servicio_contratado']} · Estado: {summary['estado_cliente']} · "
                f"Actividad: {summary['actividad_principal'] or 'Sin cargar'}\n"
                f"Observación ejecutiva: {summary['observacion_ejecutiva'] or 'Sin observaciones'}"
            ),
            justify="left", wraplength=1180, style="Subtitle.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=(0, 8))
        cards = (
            ("Estado del legajo", summary["estado_legajo"], COLORS["green"] if summary["estado_legajo"] == "Completo" else COLORS["amber"]),
            ("Riesgo general", summary["riesgo_general"], COLORS["red"] if summary["riesgo_general"] in ("Alto", "Urgente") else COLORS["green"]),
            ("Pagos pendientes", str(summary["pagos_pendientes"]), COLORS["amber"]),
            ("Pagos vencidos", str(summary["pagos_vencidos"]), COLORS["red"]),
            ("Total a cobrar", money(summary["total_pendiente"]), COLORS["red"]),
            ("Documentación pendiente", str(summary["documentacion_pendiente"]), COLORS["amber"]),
            ("Tareas pendientes", str(summary["tareas_pendientes"]), COLORS["amber"]),
            ("Tareas vencidas", str(summary["tareas_vencidas"]), COLORS["red"]),
            ("Próximo vencimiento", display_date(summary["proximo_vencimiento"]), COLORS["blue"]),
        )
        for index, (title, value, color) in enumerate(cards):
            frame.columnconfigure(index % 3, weight=1)
            MetricCard(frame, title, value, color).grid(row=1 + index // 3, column=index % 3, sticky="nsew", padx=5, pady=5)
        area_frame = ttk.LabelFrame(frame, text="Semáforo por área", padding=7)
        area_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        for index, (area, state) in enumerate(summary["estados_area"].items()):
            normalized = state.casefold()
            color = COLORS["muted"] if "no corresponde" in normalized else (
                COLORS["red"] if any(word in normalized for word in ("urgente", "vencido", "alto", "deuda")) else (
                    COLORS["amber"] if any(word in normalized for word in ("pendiente", "revisar", "incompleto", "medio", "sin cargar")) else COLORS["green"]
                )
            )
            tk.Label(area_frame, text=f"{area}: {state}", bg=color, fg="white", padx=7, pady=3).grid(row=index // 4, column=index % 4, sticky="ew", padx=3, pady=3)
            area_frame.columnconfigure(index % 4, weight=1)
        ttk.Button(frame, text="Exportar esta solapa", command=lambda: self.export_sections(["resumen"])).grid(row=6, column=2, sticky="e", pady=8)

    def _data_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Datos del Cliente")
        tree = self._tree(frame, ("campo", "valor"), {"campo": 260, "valor": 650})

        def refresh() -> None:
            for item in tree.get_children():
                tree.delete(item)
            row = self.app.database.query_one(
                "SELECT * FROM clientes WHERE id=?", (self.client_id,)
            )
            if row:
                values = dict(row)
                ordered = (
                    ("fecha_alta_estudio", "Fecha de alta en el estudio"), ("legajo", "Legajo"),
                    ("nombre_razon_social", "Cliente"), ("cuit_cuil", "CUIT"), ("dni", "DNI"),
                    ("fecha_nacimiento", "Fecha de nacimiento"), ("nacionalidad", "Nacionalidad"),
                    ("estado_civil", "Estado civil"), ("tipo_persona_detalle", "Tipo de persona"),
                    ("instagram", "Instagram"), ("telefono", "Teléfono"), ("email", "Mail"),
                    ("domicilio", "Domicilio"), ("codigo_actividad", "Código de actividad"),
                    ("actividad", "Actividad"), ("estado_detalle", "Estado"), ("rubro", "Rubro"),
                    ("observaciones", "Observaciones"),
                )
                for key, label in ordered:
                    value = values.get(key, "")
                    if key.startswith("fecha"):
                        value = display_date(str(value or ""))
                    tree.insert("", "end", values=(label, value or ""))
            records = self.app.ledger_service.list_records(
                self.client_id, "datos_complementarios"
            )
            if records:
                fields = self.app.ledger_service.SECTIONS["datos_complementarios"][1]
                labels = {key: label for key, label, _options in fields}
                for key, value in records[0]["datos"].items():
                    if key in labels and value not in (None, ""):
                        tree.insert("", "end", values=(labels[key], value))

        def edit_base() -> None:
            # Importación diferida para evitar una dependencia circular al cargar vistas.
            from .clients_view import ClientForm

            ClientForm(self, self.app, self.client_id, refresh)

        def edit_contacts() -> None:
            records = self.app.ledger_service.list_records(
                self.client_id, "datos_complementarios"
            )
            record_id = int(records[0]["id"]) if records else None
            LedgerRecordDialog(
                self,
                self.app,
                self.client_id,
                "datos_complementarios",
                refresh,
                record_id,
            )

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Editar datos base", command=edit_base).pack(side="left")
        ttk.Button(
            actions,
            text="Editar domicilios y contactos",
            command=edit_contacts,
        ).pack(side="left", padx=6)
        ttk.Button(actions, text="Exportar esta solapa", command=lambda: self.export_sections(["datos_cliente"])).pack(side="right")
        refresh()

    def _open_client_form(self, callback) -> None:
        from .clients_view import ClientForm
        ClientForm(self, self.app, self.client_id, callback)

    def _monotributo_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Monotributo")
        tk.Label(
            frame, text="Perfil Monotributo", bg="#DCE8F2", fg="#24415C",
            font=("Segoe UI", 12, "bold"), padx=12, pady=7,
        ).pack(fill="x", pady=(0, 7))
        tree = self._tree(frame, ("campo", "valor"), {"campo": 310, "valor": 650})
        rows: list[dict] = []
        labels = {
            "categoria_actual": "Categoría actual", "actividad_fiscal": "Actividad fiscal",
            "codigo_actividad": "Código de actividad", "denominacion": "Denominación",
            "fecha_alta": "Fecha de alta", "fecha_baja_monotributo": "Fecha de baja",
            "estado": "Estado", "tipo_actividad": "Tipo de actividad",
            "aporta_sipa": "Aporta SIPA", "aporta_obra_social": "Aporta obra social",
            "adherentes_obra_social": "Adherentes de obra social",
            "condicion_especial": "Condición especial",
            "observaciones_fiscales": "Observaciones fiscales",
        }

        def refresh() -> None:
            for item in tree.get_children():
                tree.delete(item)
            rows.clear()
            raw = self.app.database.query_one(
                "SELECT * FROM monotributo_cliente WHERE cliente_id=?", (self.client_id,)
            )
            values = dict(raw) if raw else {}
            for key, label in labels.items():
                value = values.get(key, "")
                if key.startswith("fecha"):
                    value = display_date(str(value or ""))
                tree.insert("", "end", values=(label, value or ""))
                rows.append({"Campo": label, "Valor": value or ""})

        def export(format_name: str) -> None:
            extension = f".{format_name}"
            filename = filedialog.asksaveasfilename(
                parent=self, defaultextension=extension,
                initialfile=f"Monotributo_{date.today().isoformat()}{extension}",
                filetypes=((format_name.upper(), f"*{extension}"),),
            )
            if not filename:
                return
            method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
            client = self.app.ledger_service.summary(self.client_id)["client"]
            method(Path(filename), "Monotributo", rows, f"{client['nombre_razon_social']} · Legajo {client.get('legajo','')} · CUIT {client['cuit_cuil']}")
            messagebox.showinfo("Exportación terminada", f"Se creó:\n{filename}", parent=self)

        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Modificar ficha", command=lambda: self._open_client_form(refresh)).pack(side="left")
        ttk.Button(actions, text="Exportar PDF", command=lambda: export("pdf")).pack(side="right")
        ttk.Button(actions, text="Exportar Excel", command=lambda: export("xlsx")).pack(side="right", padx=6)
        refresh()

    def _responsible_profile_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Responsable Inscripto")
        tk.Label(
            frame, text="Perfil Responsable Inscripto", bg="#C9DAEC", fg="#1D3F66",
            font=("Segoe UI", 12, "bold"), padx=12, pady=7,
        ).pack(fill="x", pady=(0, 7))
        tree = self._tree(frame, ("seccion", "campo", "valor"), {"seccion": 210, "campo": 330, "valor": 500})

        def refresh() -> None:
            for item in tree.get_children():
                tree.delete(item)
            values = self.app.responsible_service.profile(self.client_id)
            for section, fields in self.app.responsible_service.PROFILE_SECTIONS:
                for key, label, kind in fields:
                    value = values.get(key, "")
                    if kind == "date":
                        value = display_date(str(value or ""))
                    elif kind == "period":
                        value = display_period(str(value or ""))
                    tree.insert("", "end", values=(section, label, value or ""))

        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Modificar ficha", command=lambda: self._open_client_form(refresh)).pack(side="left")
        ttk.Button(actions, text="Exportar esta solapa", command=lambda: self.export_sections(["responsable_inscripto"])).pack(side="right")
        refresh()

    def _records_tab(self, section: str) -> None:
        title = self.app.ledger_service.SECTIONS[section][0]
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text=title)
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 7))
        search = tk.StringVar()
        state_filter = tk.StringVar(value="Todos")
        tree = self._tree(frame, ("descripcion", "periodo", "estado", "importe", "saldo", "vencimiento"), {"descripcion": 340, "periodo": 90, "estado": 140, "importe": 110, "saldo": 110, "vencimiento": 100})
        totals = ttk.Label(frame, text="", style="Subtitle.TLabel")
        totals.pack(fill="x", pady=(7, 0))

        def refresh() -> None:
            for item in tree.get_children(): tree.delete(item)
            rows = self.app.ledger_service.list_records(self.client_id, section)
            term = search.get().strip().casefold()
            if term:
                rows = [row for row in rows if term in str(row).casefold()]
            selected_state = state_filter.get()
            if section == "documentacion" and selected_state != "Todos":
                if selected_state == "Obligatorios":
                    rows = [row for row in rows if str(row["datos"].get("obligatorio", "")).casefold() == "sí"]
                else:
                    rows = [row for row in rows if str(row["estado"]).casefold() == selected_state.casefold()]
            for row in rows:
                tag = self._status_tag(str(row["estado"]))
                tree.insert("", "end", iid=str(row["id"]), values=(row["descripcion"], display_period(row["periodo"]), row["estado"], money(row["importe"]), money(row["saldo"]), display_date(row["vencimiento"])), tags=(tag,))
            for tag, color in (("green", "#DCFCE7"), ("yellow", "#FEF3C7"), ("blue", "#DBEAFE"), ("orange", "#FFEDD5"), ("red", "#FEE2E2"), ("gray", "#E5E7EB")):
                tree.tag_configure(tag, background=color)
            total_importe = sum(float(row["importe"] or 0) for row in rows)
            total_saldo = sum(float(row["saldo"] or 0) for row in rows)
            if section == "pagos":
                paid = total_importe - total_saldo
                overdue = sum(1 for row in rows if row["saldo"] and row["vencimiento"] and row["vencimiento"] < date.today().isoformat())
                totals_text = (
                    f"Facturado: {money(total_importe)} | Cobrado: {money(paid)} | "
                    f"Pendiente: {money(total_saldo)} | Pendientes: {sum(1 for row in rows if row['saldo'])} | Vencidos: {overdue}"
                )
            else:
                totals_text = f"Registros: {len(rows)} | Importe total: {money(total_importe)} | Saldo total: {money(total_saldo)}"
            totals.configure(text=totals_text)

        def edit() -> None:
            record_id = selected_tree_id(tree)
            if record_id is None:
                messagebox.showinfo("Seleccionar registro", "Seleccioná una fila.", parent=self)
                return
            LedgerRecordDialog(self, self.app, self.client_id, section, refresh, record_id)

        def delete() -> None:
            record_id = selected_tree_id(tree)
            if record_id is None:
                messagebox.showinfo("Seleccionar registro", "Seleccioná una fila.", parent=self)
                return
            if messagebox.askyesno("Confirmar eliminación", "¿Eliminar este registro? La acción quedará asentada en el historial.", parent=self):
                self.app.ledger_service.delete_record(self.client_id, record_id)
                refresh()

        def mark_state(state: str, key: str) -> None:
            record_id = selected_tree_id(tree)
            if record_id is None:
                messagebox.showinfo("Seleccionar registro", "Seleccioná una fila.", parent=self)
                return
            record = self.app.ledger_service.get_record(record_id)
            if not record:
                return
            data = dict(record["datos"])
            data[key] = state
            if section == "pagos":
                total = float(data.get("importe_facturado") or record.get("importe") or 0)
                if state in ("Cobrado", "Cobro parcial"):
                    entered_date = ask_date(self, "Fecha de cobro", "Seleccioná la fecha de cobro:", date.today())
                    if entered_date is None: return
                    from utils.formatters import normalize_date
                    try: data["fecha_cobro"] = normalize_date(entered_date)
                    except ValueError as error:
                        messagebox.showerror("Fecha inválida", str(error), parent=self); return
                if state == "Cobrado":
                    data["importe_cobrado"] = total
                    data["saldo_pendiente"] = 0
                elif state == "Cobro parcial":
                    entered = simpledialog.askstring("Cobro parcial", "Importe cobrado:", parent=self)
                    if entered is None: return
                    try: paid = float(entered.replace(".", "").replace(",", "."))
                    except ValueError:
                        messagebox.showerror("Importe inválido", "Ingresá un importe válido.", parent=self); return
                    if not 0 < paid < total:
                        messagebox.showerror("Importe inválido", "El cobro parcial debe ser mayor a cero y menor al total facturado.", parent=self); return
                    data["importe_cobrado"] = paid
                    data["saldo_pendiente"] = total - paid
            self.app.ledger_service.save_record(self.client_id, section, data, record_id)
            refresh()

        def mark_received() -> None:
            record_id = selected_tree_id(tree)
            if record_id is None:
                messagebox.showinfo("Seleccionar documento", "Seleccioná un documento.", parent=self)
                return
            entered = ask_date(self, "Marcar como recibido", "Fecha de recepción:", date.today())
            if entered is None:
                return
            from utils.formatters import normalize_date
            record = self.app.ledger_service.get_record(record_id)
            if not record:
                return
            data = dict(record["datos"])
            data["estado"] = "Recibido"
            data["fecha_recepcion"] = normalize_date(entered)
            self.app.ledger_service.save_record(self.client_id, section, data, record_id)
            refresh()

        ttk.Button(toolbar, text="+ Agregar", style="Primary.TButton", command=lambda: LedgerRecordDialog(self, self.app, self.client_id, section, refresh)).pack(side="left")
        ttk.Button(toolbar, text="Modificar", command=edit).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Eliminar", command=delete).pack(side="left")
        if section == "pagos":
            ttk.Button(toolbar, text="Marcar como cobrado", command=lambda: mark_state("Cobrado", "estado_pago")).pack(side="left", padx=(6, 0))
            ttk.Button(toolbar, text="Marcar cobro parcial", command=lambda: mark_state("Cobro parcial", "estado_pago")).pack(side="left", padx=4)
        elif section == "servicio_presupuesto":
            ttk.Button(toolbar, text="Aceptar", command=lambda: mark_state("Aceptado", "estado_presupuesto")).pack(side="left", padx=(6, 0))
            ttk.Button(toolbar, text="Rechazar", command=lambda: mark_state("Rechazado", "estado_presupuesto")).pack(side="left", padx=4)
        elif section == "documentacion":
            ttk.Button(toolbar, text="Marcar como recibido", command=mark_received).pack(side="left", padx=(6, 0))
            ttk.Combobox(toolbar, textvariable=state_filter, values=("Todos", "Recibido", "Pendiente", "Incompleto", "Vencido", "Obligatorios", "No corresponde", "Requiere actualización"), state="readonly", width=19).pack(side="right", padx=(6, 0))
        ttk.Entry(toolbar, textvariable=search, width=16).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Filtrar", command=refresh).pack(side="right")
        ttk.Button(toolbar, text="Exportar esta solapa", command=lambda: self.export_sections([section])).pack(side="right")
        tree.bind("<Double-1>", lambda _event: edit())
        refresh()

    def export_full(self) -> None:
        self.export_sections(None)

    def export_sections(self, sections: list[str] | None) -> None:
        LedgerExportDialog(self, self.app, self.client_id, sections)


class LedgerRecordDialog(tk.Toplevel):
    def __init__(self, parent, app, client_id: int, section: str, callback, record_id: int | None = None) -> None:
        super().__init__(parent)
        self.app, self.client_id, self.section, self.callback, self.record_id = app, client_id, section, callback, record_id
        self.title(("Modificar " if record_id else "Agregar ") + app.ledger_service.SECTIONS[section][0])
        fit_window(self, 820, 760)
        self.transient(parent); self.grab_set()
        footer = ttk.Frame(self, padding=10); footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Guardar", style="Primary.TButton", command=self.save).pack(side="right", padx=8)
        style = ttk.Style(self)
        style.configure("LedgerLabel.TLabel", background="#DED8CC", foreground="#334155", padding=(7, 5))
        style.configure("LedgerValue.TEntry", fieldbackground="#FBFAF7", padding=4)
        scroll = ScrollableFrame(self, padding=16, horizontal=True); scroll.pack(fill="both", expand=True); body = scroll.content
        self.vars = {}
        self.multi_widgets: dict[str, tk.Listbox] = {}
        self.budget_map = {
            str(record["datos"].get("numero_presupuesto") or record.get("numero_presupuesto") or ""): record["datos"]
            for record in app.ledger_service.list_records(client_id, "servicio_presupuesto")
            if record["datos"].get("numero_presupuesto") or record.get("numero_presupuesto")
        }
        for row, (key, label, options) in enumerate(app.ledger_service.section_fields(client_id, section)):
            ttk.Label(body, text=label, style="LedgerLabel.TLabel").grid(row=row, column=0, sticky="ew", pady=3)
            var = tk.StringVar(); self.vars[key] = var
            is_multi = (
                (section == "servicio_presupuesto" and key == "tipo_servicio")
                or (section == "vencimientos_legajo" and key == "tipo")
                or (section == "iibb_legajo" and key == "jurisdiccion")
                or bool(options and options[0] == "multi")
            )
            if key == "numero_presupuesto" and section == "pagos":
                values = ("Sin presupuesto asociado", *self.budget_map.keys())
                widget = ttk.Combobox(body, textvariable=var, values=values, state="readonly")
                var.set(values[0])
                widget.bind("<<ComboboxSelected>>", lambda _event: self._apply_budget())
            elif is_multi and options:
                widget = tk.Listbox(
                    body,
                    selectmode="multiple",
                    exportselection=False,
                    height=7,
                    borderwidth=1,
                    relief="solid",
                )
                for option in (options[1:] if options and options[0] == "multi" else options):
                    widget.insert("end", option)
                self.multi_widgets[key] = widget
                tk.Label(
                    body,
                    text="Selección múltiple: Ctrl + clic o varios clics.",
                    fg=COLORS["blue"], bg=COLORS["background"], font=("Segoe UI", 8),
                ).grid(row=row, column=2, sticky="w", padx=(8, 0), pady=4)
            elif options:
                widget = ttk.Combobox(body, textvariable=var, values=options, state="readonly")
                var.set(options[0])
                tk.Label(
                    body,
                    text="Opciones: " + " · ".join(options),
                    fg=COLORS["blue"],
                    bg=COLORS["background"],
                    justify="left",
                    wraplength=300,
                    font=("Segoe UI", 8),
                ).grid(row=row, column=2, sticky="w", padx=(8, 0), pady=4)
            elif "fecha" in key or key == "vencimiento":
                widget = DateEntry(body, var)
            else:
                widget = ttk.Entry(
                    body,
                    textvariable=var,
                    show="•" if "contrasena" in key else "",
                    style="LedgerValue.TEntry",
                )
            widget.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(0, minsize=250)
        if record_id:
            record = app.ledger_service.get_record(record_id)
            if record:
                for key, value in record["datos"].items():
                    if key in self.multi_widgets:
                        selected = {part.strip() for part in str(value or "").split(",")}
                        widget = self.multi_widgets[key]
                        for index in range(widget.size()):
                            if widget.get(index) in selected:
                                widget.selection_set(index)
                    elif key in self.vars:
                        if "fecha" in key or key == "vencimiento":
                            self.vars[key].set(display_date(str(value or "")))
                        elif key == "periodo":
                            self.vars[key].set(display_period(str(value or "")))
                        else:
                            self.vars[key].set(str(value or ""))

    def _apply_budget(self) -> None:
        number = self.vars.get("numero_presupuesto", tk.StringVar()).get()
        budget = self.budget_map.get(number)
        if not budget:
            return
        mapping = {
            "concepto": budget.get("descripcion") or budget.get("concepto", ""),
            "periodo": display_period(str(budget.get("periodo") or "")),
            "importe_facturado": budget.get("valor_presupuestado", ""),
            "saldo_pendiente": budget.get("saldo_pendiente") or budget.get("valor_presupuestado", ""),
            "fecha_vencimiento": display_date(str(budget.get("fecha_vencimiento") or "")),
        }
        for key, value in mapping.items():
            if key in self.vars:
                self.vars[key].set(str(value or ""))

    def save(self) -> None:
        try:
            data = {key: var.get().strip() for key, var in self.vars.items()}
            for key, widget in self.multi_widgets.items():
                data[key] = ", ".join(widget.get(index) for index in widget.curselection())
            self.app.ledger_service.save_record(self.client_id, self.section, data, self.record_id)
            self.callback(); self.destroy()
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error), parent=self)


class LedgerExportDialog(tk.Toplevel):
    def __init__(self, parent, app, client_id: int, sections: list[str] | None) -> None:
        super().__init__(parent)
        self.app, self.client_id, self.sections = app, client_id, sections
        self.title("Exportar legajo"); fit_window(self, 650, 700 if sections is None else 300); self.transient(parent); self.grab_set()
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Formato de exportación", style="Title.TLabel").pack(anchor="w")
        self.section_vars = {}
        if sections is None:
            ttk.Label(body, text="Seleccioná una, varias o todas las solapas.", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 8))
            selector = ScrollableFrame(body, padding=6); selector.pack(fill="both", expand=True, pady=(0, 8))
            for index, section in enumerate(app.ledger_export_service.SECTION_ORDER):
                variable = tk.BooleanVar(value=True); self.section_vars[section] = variable
                ttk.Checkbutton(selector.content, text=app.ledger_export_service.section_title(section), variable=variable).grid(row=index // 2, column=index % 2, sticky="w", padx=8, pady=3)
        ttk.Button(body, text="Excel", command=lambda: self.run("xlsx")).pack(fill="x", pady=(16, 5))
        ttk.Button(body, text="PDF", command=lambda: self.run("pdf")).pack(fill="x", pady=5)
        ttk.Button(body, text="Excel y PDF", style="Primary.TButton", command=lambda: self.run("both")).pack(fill="x", pady=5)

    def run(self, format_name: str) -> None:
        summary = self.app.ledger_service.summary(self.client_id)
        client = summary["client"]
        selected_sections = self.sections or [
            section for section, variable in self.section_vars.items() if variable.get()
        ]
        if not selected_sections:
            messagebox.showinfo("Seleccionar solapas", "Seleccioná al menos una solapa.", parent=self)
            return
        safe_name = self.app.ledger_export_service.safe_name(client["nombre_razon_social"])
        if len(selected_sections) == 1:
            section_name = self.app.ledger_export_service.safe_name(
                self.app.ledger_export_service.section_title(selected_sections[0])
            )
            stem = f"{safe_name}_{client['cuit_cuil']}_{section_name}_{date.today().isoformat()}"
        else:
            stem = f"Legajo_Cliente_{safe_name}_{client['cuit_cuil']}_{date.today().isoformat()}"
        try:
            if format_name == "both":
                directory = filedialog.askdirectory(parent=self, title="Elegir carpeta")
                if not directory: return
                paths = [
                    self.app.ledger_export_service.export_excel(Path(directory) / f"{stem}.xlsx", self.client_id, selected_sections),
                    self.app.ledger_export_service.export_pdf(Path(directory) / f"{stem}.pdf", self.client_id, selected_sections),
                ]
                message = "\n".join(str(path) for path in paths)
            else:
                filename = filedialog.asksaveasfilename(parent=self, defaultextension=f".{format_name}", initialfile=f"{stem}.{format_name}", filetypes=((format_name.upper(), f"*.{format_name}"),))
                if not filename: return
                method = self.app.ledger_export_service.export_excel if format_name == "xlsx" else self.app.ledger_export_service.export_pdf
                message = str(method(Path(filename), self.client_id, selected_sections))
            messagebox.showinfo("Exportación terminada", f"Se creó:\n{message}", parent=self)
            self.destroy()
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error), parent=self)


class BatchLedgerExportDialog(tk.Toplevel):
    def __init__(self, parent, app, client_ids: list[int]) -> None:
        super().__init__(parent)
        self.app, self.client_ids = app, client_ids
        self.title("Exportar clientes seleccionados"); fit_window(self, 650, 700); self.transient(parent); self.grab_set()
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"{len(client_ids)} cliente(s) seleccionados", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="Solapas a incluir", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 6))
        selector = ScrollableFrame(body, padding=6); selector.pack(fill="both", expand=True)
        self.section_vars = {}
        for index, section in enumerate(app.ledger_export_service.SECTION_ORDER):
            variable = tk.BooleanVar(value=True); self.section_vars[section] = variable
            ttk.Checkbutton(selector.content, text=app.ledger_export_service.section_title(section), variable=variable).grid(row=index // 2, column=index % 2, sticky="w", padx=8, pady=3)
        ttk.Button(body, text="Excel", command=lambda: self.run(("xlsx",))).pack(fill="x", pady=(16, 5))
        ttk.Button(body, text="PDF", command=lambda: self.run(("pdf",))).pack(fill="x", pady=5)
        ttk.Button(body, text="Excel y PDF", style="Primary.TButton", command=lambda: self.run(("xlsx", "pdf"))).pack(fill="x", pady=5)

    def run(self, formats: tuple[str, ...]) -> None:
        sections = [section for section, variable in self.section_vars.items() if variable.get()]
        if not sections:
            messagebox.showinfo("Seleccionar solapas", "Seleccioná al menos una solapa.", parent=self); return
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=".zip", initialfile=f"Legajos_Clientes_Seleccionados_{date.today().isoformat()}.zip", filetypes=(("ZIP", "*.zip"),))
        if not filename: return
        try:
            output = self.app.ledger_export_service.export_batch(Path(filename), self.client_ids, formats, sections)
            messagebox.showinfo("Exportación terminada", f"Se creó:\n{output}", parent=self); self.destroy()
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error), parent=self)
