from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from models import Voucher
from utils.formatters import display_date, money
from utils.validators import positive_number
from .date_widgets import DateEntry
from .common import ScrollableFrame, fit_window, make_tree_sortable


class AccountingView(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=22)
        ttk.Label(self, text="Módulo contable", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Carga manual y consulta de comprobantes de ventas y compras.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 12))
        ttk.Button(
            self, text="Crear cliente", style="Primary.TButton",
            command=lambda: app.show_view("clientes", action="new")
        ).pack(anchor="e", pady=(0, 8))
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        notebook.add(VouchersPanel(notebook, app, "ventas"), text="Ventas")
        notebook.add(VouchersPanel(notebook, app, "compras"), text="Compras")


class VouchersPanel(ttk.Frame):
    def __init__(self, parent, app, kind: str, fixed_client_id: int | None = None) -> None:
        super().__init__(parent, padding=12)
        self.app = app
        self.kind = kind
        self.fixed_client_id = fixed_client_id
        self.clients = app.client_service.list_clients()
        self.client_by_label = {
            f"{item['nombre_razon_social']} · {item['cuit_cuil']}": int(item["id"])
            for item in self.clients
        }
        fixed_label = next((label for label, value in self.client_by_label.items() if value == fixed_client_id), "Todos")
        self.client_filter = tk.StringVar(value=fixed_label)
        # Sin un período inicial se muestran todos los comprobantes. El usuario
        # puede completar el filtro cuando necesite limitar la consulta.
        self.period_filter = tk.StringVar(value="")
        self.search_filter = tk.StringVar()

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        label = "venta" if kind == "ventas" else "compra"
        ttk.Button(
            toolbar,
            text=f"+ Cargar {label}",
            style="Primary.TButton",
            command=self.add,
        ).pack(side="left")
        ttk.Button(toolbar, text="Importar ARCA", command=self.import_arca).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(toolbar, text="Exportar Excel", command=self.export).pack(
            side="left", padx=8
        )
        ttk.Button(
            toolbar,
            text=f"Borrar {'ventas' if kind == 'ventas' else 'compras'} importadas",
            command=self.open_delete_dialog,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Eliminar facturas seleccionadas",
            command=self.delete_selected,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Actualizar", command=self.refresh).pack(side="right")

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 10))
        ttk.Label(filters, text="Cliente").grid(row=0, column=0, sticky="w")
        client_combo = ttk.Combobox(
            filters,
            textvariable=self.client_filter,
            values=("Todos", *self.client_by_label.keys()),
            state="disabled" if fixed_client_id else "readonly",
            width=34,
        )
        client_combo.grid(row=0, column=1, padx=(6, 14))
        ttk.Label(filters, text="Período").grid(row=0, column=2, sticky="w")
        ttk.Entry(filters, textvariable=self.period_filter, width=10).grid(
            row=0, column=3, padx=(6, 14)
        )
        ttk.Label(filters, text="Buscar").grid(row=0, column=4, sticky="w")
        ttk.Entry(filters, textvariable=self.search_filter, width=22).grid(
            row=0, column=5, padx=(6, 10)
        )
        ttk.Button(filters, text="Filtrar", command=self.refresh).grid(row=0, column=6)

        self.analysis = ttk.Notebook(self)
        self.analysis.pack(fill="both", expand=True)
        detail_frame = ttk.Frame(self.analysis)
        self.analysis.add(detail_frame, text="Detalle de comprobantes")
        columns = ("fecha","tipo","pv","numero","contraparte","documento","concepto","moneda","cambio","original","pesos","signo","neto","estado","origen","periodo","archivo","observaciones")
        self.tree = ttk.Treeview(
            detail_frame, columns=columns, show="headings", selectmode="extended"
        )
        settings = (
            ("fecha", "Fecha", 90),
            ("tipo", "Tipo", 135),
            ("pv", "Punto venta", 80),
            ("numero", "Número", 90),
            ("contraparte", "Cliente / proveedor", 190),
            ("documento", "CUIT / DNI", 110),
            ("concepto", "Concepto", 120),
            ("moneda", "Moneda", 65),
            ("cambio", "Tipo cambio", 85),
            ("original", "Importe original", 110),
            ("pesos", "Importe pesos", 110),
            ("signo", "Signo", 55),
            ("neto", "Neto fiscal", 105),
            ("estado", "Estado", 80),
            ("origen", "Origen", 75),
            ("periodo", "Período", 80),
            ("archivo", "Archivo origen", 190),
            ("observaciones", "Observaciones", 180),
        )
        for column, title, width in settings:
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width)
        yscroll=ttk.Scrollbar(detail_frame,orient="vertical",command=self.tree.yview); xscroll=ttk.Scrollbar(detail_frame,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set,xscrollcommand=xscroll.set)
        self.tree.grid(row=0,column=0,sticky="nsew");yscroll.grid(row=0,column=1,sticky="ns");xscroll.grid(row=1,column=0,sticky="ew");detail_frame.rowconfigure(0,weight=1);detail_frame.columnconfigure(0,weight=1)
        make_tree_sortable(self.tree,{"cambio","original","pesos","signo","neto"})

        self.summary_tree = self._analysis_tree(
            "Resumen mensual",
            ("periodo", "facturas", "nc", "nd", "anulados", "neto", "cantidad"),
            "resumen_mensual",
        )
        self.significant_tree = self._analysis_tree(
            "Significativos",
            ("fecha", "tipo", "contraparte", "documento", "moneda", "importe", "motivo"),
            "significativos",
        )
        self.foreign_tree = self._analysis_tree(
            "Moneda extranjera",
            ("fecha", "tipo", "contraparte", "moneda", "original", "cambio", "pesos", "estado"),
            "moneda_extranjera",
        )
        self.ranking_tree = self._analysis_tree(
            "Ranking",
            ("puesto", "contraparte", "documento", "total", "cantidad", "porcentaje"),
            "ranking",
        )

        self.total_label = ttk.Label(self, text="")
        self.total_label.pack(anchor="e", pady=(8, 0))
        self.refresh()

    def _selected_client_id(self) -> int | None:
        return self.fixed_client_id or self.client_by_label.get(self.client_filter.get())

    def _analysis_tree(
        self, title: str, columns: tuple[str, ...], section: str
    ) -> ttk.Treeview:
        frame = ttk.Frame(self.analysis, padding=6)
        self.analysis.add(frame, text=title)

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(0, 6))
        ttk.Button(
            actions,
            text="Exportar esta sección",
            command=lambda: self.export_analysis(section),
        ).pack(side="right")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        tree = ttk.Treeview(table, columns=columns, show="headings")
        for column in columns:
            tree.heading(column, text=column.replace("_", " ").title())
            tree.column(column, width=130)
        yscroll = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        make_tree_sortable(
            tree,
            {
                "facturas", "nc", "nd", "anulados", "neto", "cantidad",
                "importe", "original", "cambio", "pesos", "total", "porcentaje",
            },
        )
        return tree

    def refresh(self) -> None:
        try:
            rows = self.app.voucher_service.list(
                self.kind,
                client_id=self._selected_client_id(),
                period=self.period_filter.get(),
                search=self.search_filter.get(),
            )
        except Exception as error:
            messagebox.showerror("Filtros inválidos", str(error))
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        total = 0.0
        for row in rows:
            total += float(row["importe_neto_fiscal"])
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    display_date(row["fecha"]),
                    row["tipo_comprobante"],
                    row["punto_venta"],
                    row["numero_comprobante"],
                    row["contraparte_nombre"],
                    row["contraparte_documento"],
                    row.get("concepto", ""),
                    row["moneda"],
                    row["tipo_cambio"],
                    money(row["importe_original"]),
                    money(row["importe_pesos"]),
                    row["signo_fiscal"],
                    money(row["importe_neto_fiscal"]),
                    row["estado"].title(),
                    row["origen"],
                    row["periodo_fiscal"],
                    row.get("nombre_archivo_origen", ""),
                    row["observaciones"],
                ),
            )
        self.total_label.configure(text=f"{len(rows)} comprobante(s) · Neto: {money(total)}")
        self._refresh_analysis()

    def delete_selected(self) -> None:
        client_id = self._selected_client_id()
        if client_id is None:
            messagebox.showinfo(
                "Seleccionar cliente",
                "Elegí un cliente antes de eliminar comprobantes.",
            )
            return
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(
                "Seleccionar facturas",
                "Seleccioná una o varias filas. Usá Ctrl+clic para elegir filas separadas "
                "o Shift+clic para seleccionar un bloque.",
            )
            return
        if not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Está seguro que desea eliminar {len(selected)} comprobante(s)?\n\n"
            "Esta acción no se puede deshacer y no eliminará al cliente.",
            parent=self,
        ):
            return
        try:
            deleted = self.app.voucher_service.delete_selected(
                self.kind, client_id, [int(item) for item in selected]
            )
            self.app.alert_service.refresh(client_id)
            self.refresh()
            messagebox.showinfo(
                "Comprobantes eliminados",
                f"Se eliminaron {deleted} comprobante(s). Los indicadores fueron recalculados.",
            )
        except Exception as error:
            messagebox.showerror("No se pudo eliminar", str(error))

    def _refresh_analysis(self) -> None:
        client_id=self._selected_client_id()
        for tree in (self.summary_tree,self.significant_tree,self.foreign_tree,self.ranking_tree):
            for item in tree.get_children():tree.delete(item)
        if client_id is None:return
        for row in self.app.voucher_service.monthly_summary(self.kind,client_id):
            self.summary_tree.insert("","end",values=(row["periodo"],money(row["facturas"]),money(row["notas_credito"]),money(row["notas_debito"]),row["anulados"],money(row["total_neto"]),row["cantidad"]))
        for row in self.app.voucher_service.noteworthy(self.kind,client_id):
            self.significant_tree.insert("","end",values=(display_date(row["fecha"]),row["tipo_comprobante"],row["contraparte_nombre"],row["contraparte_documento"],row["moneda"],money(row["importe_pesos"]),row["motivo_alerta"]))
        for row in self.app.voucher_service.noteworthy(self.kind,client_id,True):
            self.foreign_tree.insert("","end",values=(display_date(row["fecha"]),row["tipo_comprobante"],row["contraparte_nombre"],row["moneda"],money(row["importe_original"]),row["tipo_cambio"],money(row["importe_pesos"]),row["estado"]))
        for row in self.app.voucher_service.ranking(self.kind,client_id):
            self.ranking_tree.insert("","end",values=(row["puesto"],row["contraparte_nombre"],row["contraparte_documento"],money(row["total"]),row["cantidad"],f"{row['porcentaje']*100:.1f}%"))

    def add(self) -> None:
        if not self.clients:
            messagebox.showinfo(
                "Sin clientes", "Primero tenés que registrar al menos un cliente activo."
            )
            return
        VoucherForm(self, self.app, self.kind, self.clients, self.refresh)

    def export(self) -> None:
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar comprobantes",
            defaultextension=".xlsx",
            initialfile=f"Reporte de {self.kind}.xlsx",
            filetypes=(("Excel", "*.xlsx"),),
        )
        if not filename:
            return
        try:
            output = self.app.report_service.export_vouchers(
                self.kind,
                Path(filename),
                client_id=self._selected_client_id(),
                period=self.period_filter.get(),
            )
            messagebox.showinfo("Reporte exportado", f"Se creó:\n{output}")
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error))

    def export_analysis(self, section: str) -> None:
        client_id = self._selected_client_id()
        if client_id is None:
            messagebox.showinfo(
                "Seleccionar cliente",
                "Elegí un cliente para exportar esta sección.",
                parent=self,
            )
            return
        section_titles = {
            "resumen_mensual": "Resumen mensual",
            "significativos": "Significativos",
            "moneda_extranjera": "Moneda extranjera",
            "ranking": "Ranking",
        }
        title = section_titles[section]
        filename = filedialog.asksaveasfilename(
            parent=self,
            title=f"Exportar {title.lower()}",
            defaultextension=".xlsx",
            initialfile=f"{title} de {self.kind}.xlsx",
            filetypes=(("Excel", "*.xlsx"),),
        )
        if not filename:
            return
        try:
            output = self.app.report_service.export_accounting_section(
                self.kind,
                section,
                Path(filename),
                client_id,
            )
            messagebox.showinfo(
                "Sección exportada", f"Se creó:\n{output}", parent=self
            )
        except Exception as error:
            messagebox.showerror(
                "No se pudo exportar", str(error), parent=self
            )

    def import_arca(self) -> None:
        client_id = self._selected_client_id()
        if client_id is None:
            messagebox.showinfo(
                "Seleccionar cliente",
                "Elegí el cliente interno al que pertenecen los comprobantes antes de importar.",
            )
            return
        filename = filedialog.askopenfilename(
            parent=self,
            title="Importar comprobantes ARCA",
            filetypes=(("Excel o CSV", "*.xlsx *.csv"), ("Todos", "*.*")),
        )
        if not filename:
            return
        try:
            preview = self.app.import_service.preview(Path(filename), self.kind)
            mapping = dict(preview.mapping)
            if preview.missing:
                dialog = MappingDialog(self, preview.missing, list(preview.dataframe.columns))
                self.wait_window(dialog)
                if dialog.result is None:
                    return
                mapping.update(dialog.result)
            result = self.app.import_service.import_rows(preview, client_id, mapping)
            self.app.alert_service.refresh(client_id)
            self.refresh()
            detail = "\n".join(result["messages"])
            messagebox.showinfo(
                "Importación terminada",
                f"Leídas: {result['read']}\n"
                f"Importadas: {result['imported']}\n"
                f"Duplicadas: {result['duplicates']}\n"
                f"Con error: {result['errors']}"
                + (f"\n\nPrimeros errores:\n{detail}" if detail else ""),
            )
        except Exception as error:
            messagebox.showerror("No se pudo importar", str(error))

    def open_delete_dialog(self) -> None:
        client_id=self._selected_client_id()
        if client_id is None:
            messagebox.showinfo("Seleccionar cliente","Elegí un cliente antes de borrar datos.");return
        DeleteImportedDialog(self,self.app,self.kind,client_id,self.period_filter.get(),self._after_delete)

    def _after_delete(self, deleted: int) -> None:
        client_id=self._selected_client_id()
        if client_id:
            self.app.alert_service.refresh(client_id)
        self.refresh();messagebox.showinfo("Datos borrados",f"Se borraron {deleted} comprobante(s). Los indicadores fueron recalculados.")


class DeleteImportedDialog(tk.Toplevel):
    CONFIRMATION="¿Está seguro que desea borrar estos datos? Esta acción no se puede deshacer."
    def __init__(self,parent,app,kind,client_id,period,callback):
        super().__init__(parent);self.app=app;self.kind=kind;self.client_id=client_id;self.period=period;self.callback=callback
        self.title("Borrar datos de comprobantes");fit_window(self,620,430);self.transient(parent.winfo_toplevel());self.grab_set()
        body=ttk.Frame(self,padding=18);body.pack(fill="both",expand=True)
        ttk.Label(body,text="Borrado seguro",style="Title.TLabel").pack(anchor="w")
        ttk.Label(body,text="El cliente no será borrado. Elegí el alcance de los comprobantes a eliminar.",style="Subtitle.TLabel",wraplength=550).pack(anchor="w",pady=(2,14))
        self.batches=app.import_service.list_batches(client_id,kind);self.batch_map={f"#{b['id']} · {b['archivo']} · {b['fecha_importacion']}":b['id'] for b in self.batches};self.batch=tk.StringVar(value=next(iter(self.batch_map),""))
        ttk.Button(body,text=f"Borrar {'ventas' if kind=='ventas' else 'compras'} importadas",command=lambda:self.run(lambda:app.import_service.delete_imported_kind(client_id,kind))).pack(fill="x",pady=4)
        ttk.Button(body,text=f"Borrar datos importados del período {period}",command=lambda:self.run(lambda:app.import_service.delete_period(client_id,period))).pack(fill="x",pady=4)
        line=ttk.Frame(body);line.pack(fill="x",pady=4);ttk.Combobox(line,textvariable=self.batch,values=tuple(self.batch_map),state="readonly").pack(side="left",fill="x",expand=True);ttk.Button(line,text="Borrar archivo importado",state="normal" if self.batch_map else "disabled",command=lambda:self.run(lambda:app.import_service.delete_batch(client_id,self.batch_map[self.batch.get()]))).pack(side="left",padx=(8,0))
        ttk.Button(body,text="Borrar todos los comprobantes del cliente",command=lambda:self.run(lambda:app.import_service.delete_all_vouchers(client_id)),style="Primary.TButton").pack(fill="x",pady=(12,4))

    def run(self,operation):
        if not messagebox.askyesno("Confirmar borrado",self.CONFIRMATION,parent=self):return
        try:deleted=operation();self.destroy();self.callback(deleted)
        except Exception as error:messagebox.showerror("No se pudo borrar",str(error),parent=self)


class MappingDialog(tk.Toplevel):
    LABELS = {
        "fecha": "Fecha",
        "tipo_comprobante": "Tipo de comprobante",
        "punto_venta": "Punto de venta",
        "numero_desde": "Número desde",
        "denominacion_receptor": "Denominación receptor",
        "denominacion_emisor": "Denominación emisor",
        "moneda": "Moneda",
        "importe_total": "Importe total",
    }

    def __init__(self, parent, missing: list[str], columns: list[str]) -> None:
        super().__init__(parent)
        self.title("Mapear columnas")
        fit_window(self, 620, 520)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.result: dict[str, str] | None = None
        self.variables: dict[str, tk.StringVar] = {}
        footer = ttk.Frame(self, padding=(14, 10))
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            footer, text="Continuar", style="Primary.TButton", command=self.accept
        ).pack(side="right", padx=8)
        scroll = ScrollableFrame(self, padding=18)
        scroll.pack(side="top", fill="both", expand=True)
        body = scroll.content
        ttk.Label(body, text="Mapeo manual", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="Seleccioná la columna del archivo correspondiente a cada campo obligatorio.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 14))
        form = ttk.Frame(body)
        form.pack(fill="both", expand=True)
        for row, field in enumerate(missing):
            ttk.Label(form, text=self.LABELS.get(field, field)).grid(
                row=row, column=0, sticky="w", pady=5
            )
            variable = tk.StringVar()
            self.variables[field] = variable
            ttk.Combobox(
                form, textvariable=variable, values=columns, state="readonly"
            ).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=5)
        form.columnconfigure(1, weight=1)

    def accept(self) -> None:
        if any(not variable.get() for variable in self.variables.values()):
            messagebox.showerror(
                "Mapeo incompleto", "Seleccioná una columna para cada campo.", parent=self
            )
            return
        self.result = {field: variable.get() for field, variable in self.variables.items()}
        self.destroy()


class VoucherForm(tk.Toplevel):
    TYPES = (
        "Factura A",
        "Factura B",
        "Factura C",
        "Nota de Crédito A",
        "Nota de Crédito B",
        "Nota de Crédito C",
        "Nota de Débito A",
        "Nota de Débito B",
        "Nota de Débito C",
        "Otro",
    )

    def __init__(self, parent, app, kind: str, clients: list[dict], on_saved) -> None:
        super().__init__(parent)
        self.app = app
        self.kind = kind
        self.on_saved = on_saved
        self.client_map = {
            f"{item['nombre_razon_social']} · {item['cuit_cuil']}": int(item["id"])
            for item in clients
        }
        self.vars = {key: tk.StringVar() for key in (
            "client", "date", "period", "type", "point", "number",
            "counterparty", "document", "currency", "rate", "amount", "state", "notes"
        )}
        noun = "Venta" if kind == "ventas" else "Compra"
        self.title(f"Cargar {noun.lower()}")
        fit_window(self, 700, 720)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        footer = ttk.Frame(self, padding=(14, 10))
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            footer,
            text="Guardar comprobante",
            style="Primary.TButton",
            command=self.save,
        ).pack(side="right", padx=8)
        scroll = ScrollableFrame(self, padding=18)
        scroll.pack(side="top", fill="both", expand=True)
        body = scroll.content
        ttk.Label(body, text=f"Nueva {noun.lower()}", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        self._combo(body, 1, "Cliente del estudio *", "client", tuple(self.client_map))
        ttk.Label(body, text="Fecha *").grid(row=2, column=0, sticky="w", pady=4)
        DateEntry(body, self.vars["date"]).grid(
            row=2, column=1, sticky="ew", padx=(12, 0), pady=4
        )
        self._entry(body, 3, "Período fiscal *", "period")
        self._combo(body, 4, "Tipo de comprobante *", "type", self.TYPES)
        self._entry(body, 5, "Punto de venta *", "point")
        self._entry(body, 6, "Número *", "number")
        counterparty_label = "Cliente receptor *" if kind == "ventas" else "Proveedor *"
        self._entry(body, 7, counterparty_label, "counterparty")
        self._entry(body, 8, "CUIT/DNI", "document")
        self._combo(body, 9, "Moneda", "currency", ("ARS", "USD", "EUR", "BRL", "UYU", "OTRA"))
        self._entry(body, 10, "Tipo de cambio", "rate")
        self._entry(body, 11, "Importe original *", "amount")
        self._combo(body, 12, "Estado", "state", ("normal", "anulado", "observado"))
        self._entry(body, 13, "Observaciones", "notes")

        today = date.today()
        self.vars["client"].set(next(iter(self.client_map)))
        self.vars["date"].set(today.strftime("%d/%m/%Y"))
        self.vars["period"].set(today.strftime("%Y-%m"))
        self.vars["type"].set("Factura C" if kind == "ventas" else "Factura A")
        self.vars["currency"].set("ARS")
        self.vars["rate"].set("1")
        self.vars["state"].set("normal")

    def _entry(self, parent, row: int, label: str, key: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.vars[key]).grid(
            row=row, column=1, sticky="ew", padx=(12, 0), pady=4
        )
        parent.columnconfigure(1, weight=1)

    def _combo(self, parent, row: int, label: str, key: str, values) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.vars[key],
            values=values,
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)

    def save(self) -> None:
        try:
            amount = positive_number(self.vars["amount"].get(), "Importe")
            rate = positive_number(self.vars["rate"].get(), "Tipo de cambio")
            voucher = Voucher(
                cliente_id=self.client_map[self.vars["client"].get()],
                fecha=self.vars["date"].get(),
                periodo_fiscal=self.vars["period"].get(),
                tipo_comprobante=self.vars["type"].get(),
                punto_venta=self.vars["point"].get(),
                numero_comprobante=self.vars["number"].get(),
                contraparte_nombre=self.vars["counterparty"].get(),
                contraparte_documento=self.vars["document"].get(),
                moneda=self.vars["currency"].get(),
                tipo_cambio=rate,
                importe_original=amount,
                estado=self.vars["state"].get(),
                observaciones=self.vars["notes"].get(),
            )
            self.app.voucher_service.create(self.kind, voucher)
            self.on_saved()
            self.destroy()
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error), parent=self)
