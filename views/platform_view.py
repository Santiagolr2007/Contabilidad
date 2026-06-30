from __future__ import annotations

import os
import tempfile
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from utils.formatters import display_date, display_period, money, number_ar

from .common import fit_window, make_tree_sortable
from .ledger_view import TwoRowNotebook


MP_TYPES = (
    "Cobranza", "Pago", "Transferencia recibida", "Transferencia realizada",
    "Pago con QR", "Rendimientos / Intereses", "Acreditación",
    "Crédito / Préstamo / Financiación", "Pago de crédito / préstamo",
    "Interés", "Comisión", "Retención", "Percepción", "Impuesto",
    "Devolución", "Contracargo", "Ajuste", "Otro", "A revisar",
)


def formatted(key: str, value):
    if value is None: return ""
    name = key.casefold()
    if "fecha" in name: return display_date(str(value))
    if "periodo" in name: return display_period(str(value))
    if any(term in name for term in ("importe", "saldo", "total", "comision", "retencion", "percepcion", "impuesto", "precio", "descuento", "envio", "venta", "compra", "cobranza", "pago", "transferencia", "interes", "anulacion", "nota")) and isinstance(value, (int, float)):
        return number_ar(value)
    return value


class DynamicTable(ttk.Frame):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.tree = ttk.Treeview(self, show="headings", selectmode="browse")
        y = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); y.grid(row=0, column=1, sticky="ns"); x.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        self.rows: list[dict] = []; self.row_by_item = {}

    def fill(self, rows: list[dict], exclude: tuple[str, ...] = ("id", "cliente_id", "id_importacion", "actualizado_en", "datos_originales_json")) -> None:
        self.rows = rows
        columns = tuple(key for key in (rows[0].keys() if rows else ("estado",)) if key not in exclude)
        self.tree.configure(columns=columns)
        for key in columns:
            self.tree.heading(key, text=key.replace("_", " ").title())
            name = key.casefold()
            anchor = "e" if any(term in name for term in ("importe", "saldo", "total", "precio", "cantidad", "comision", "retencion", "percepcion", "impuesto", "venta", "compra", "cobranza", "pago", "transferencia", "interes", "anulacion", "nota")) else ("center" if "fecha" in name or "periodo" in name or name == "estado" else "w")
            self.tree.column(key, width=135 if anchor != "w" else 190, minwidth=90, anchor=anchor, stretch=True)
        for item in self.tree.get_children(): self.tree.delete(item)
        self.row_by_item = {}
        for row in rows:
            item = self.tree.insert("", "end", iid=str(row.get("id", "")) if row.get("id") is not None and not self.tree.exists(str(row.get("id"))) else None, values=[formatted(key, row.get(key)) for key in columns])
            self.row_by_item[item] = row
        make_tree_sortable(self.tree, {key for key in columns if any(term in key.casefold() for term in ("importe", "saldo", "total", "cantidad", "precio"))})


class BasePlatformPanel(ttk.Frame):
    def __init__(self, parent, app, source: str) -> None:
        super().__init__(parent, padding=10)
        self.app, self.source = app, source
        clients = app.client_service.list_clients(include_inactive=True)
        self.clients = {f"{row['nombre_razon_social']} · {row['cuit_cuil']}": int(row["id"]) for row in clients}
        self.client = tk.StringVar(value=next(iter(self.clients), ""))
        self.period = tk.StringVar(); self.search = tk.StringVar(); self.kind = tk.StringVar(value="Todos")
        self.year=tk.StringVar();self.month=tk.StringVar();self.minimum=tk.StringVar(value="0");self.state_filter=tk.StringVar(value="Todos");self.province=tk.StringVar();self.product_filter=tk.StringVar()
        self.tables: dict[str, DynamicTable] = {}
        self.current_rows: dict[str, list[dict]] = {}
        self.pending_file: Path | None = None
        self.pending_preview: dict | None = None
        self.pending_mapping: dict = {}
        self.pending_options: dict | None = None

    def client_id(self) -> int | None:
        return self.clients.get(self.client.get())

    def create_table_tab(self, notebook, title: str) -> DynamicTable:
        frame = ttk.Frame(notebook, padding=5); notebook.add(frame, text=title)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(0, 5))
        ttk.Button(actions, text="Exportar Excel", command=lambda name=title: self.export_tab(name, "xlsx")).pack(side="right")
        ttk.Button(actions, text="Exportar PDF", command=lambda name=title: self.export_tab(name, "pdf")).pack(side="right", padx=5)
        ttk.Button(actions, text="Imprimir", command=lambda name=title: self.print_tab(name)).pack(side="right")
        table = DynamicTable(frame); table.pack(fill="both", expand=True)
        self.tables[title] = table
        return table

    def export_tab(self, title: str, format_name: str) -> None:
        hidden = {"id", "cliente_id", "id_importacion", "actualizado_en", "datos_originales_json"}
        rows = [{key: value for key, value in row.items() if key not in hidden} for row in self.current_rows.get(title, [])]
        extension = f".{format_name}"
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, initialfile=f"{title.replace('/', '-')}_{date.today().isoformat()}{extension}", filetypes=((format_name.upper(), f"*{extension}"),))
        if not filename: return
        method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
        method(Path(filename), title, rows, f"Cliente: {self.client.get()} | Período: {self.period.get() or 'Todos'}")
        messagebox.showinfo("Exportación terminada", f"Se creó:\n{filename}", parent=self)

    def print_tab(self, title: str) -> None:
        hidden = {"id", "cliente_id", "id_importacion", "actualizado_en", "datos_originales_json"}
        rows = [{key: value for key, value in row.items() if key not in hidden} for row in self.current_rows.get(title, [])]
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=".pdf", initialfile=f"{title.replace('/', '-')}_imprimir.pdf", filetypes=(("PDF", "*.pdf"),))
        if not filename: return
        self.app.report_service.export_table_pdf(Path(filename), title, rows, f"Cliente: {self.client.get()}")
        try:
            os.startfile(filename, "print")
        except (AttributeError, OSError):
            messagebox.showinfo("PDF listo para imprimir", f"Abrí e imprimí:\n{filename}", parent=self)

    def mapping_for(self, filename: str) -> dict | None:
        preview = self.app.platform_service.preview_file(Path(filename), self.source)
        if not preview["missing"]: return {}
        dialog = PlatformMappingDialog(self, preview["missing"], preview["columns"])
        self.wait_window(dialog)
        return dialog.result

    def open_history(self) -> None:
        client_id = self.client_id()
        if not client_id: messagebox.showinfo("Seleccionar cliente", "Debe seleccionar un cliente."); return
        ImportHistoryDialog(self, self.app, client_id, self.refresh)

    def current_title(self) -> str:
        return self.SUBTABS[self.notebook.current]

    def export_current(self, format_name: str) -> None:
        self.export_tab(self.current_title(), format_name)

    def print_current(self) -> None:
        self.print_tab(self.current_title())

    def stage_file(self, title: str) -> bool:
        filename = filedialog.askopenfilename(parent=self, title=title, filetypes=(("Excel o CSV", "*.xls *.xlsx *.csv"),))
        if not filename: return False
        preview = self.app.platform_service.preview_file(Path(filename), self.source)
        mapping = self.mapping_for(filename)
        if mapping is None: return False
        self.pending_file = Path(filename); self.pending_preview = preview; self.pending_mapping = mapping
        self.pending_options = {
            "mapping": mapping, "duplicate_action": "skip",
            "header_row": preview["header_row"], "sheet": preview["sheet"],
            "selected_rows": None, "row_overrides": {},
        }
        messagebox.showinfo("Archivo preparado", f"Se cargó {self.pending_file.name}.\nRevisalo con Vista previa y luego confirmá la importación.", parent=self)
        return True

    def preview_staged(self) -> None:
        if not self.pending_file or not self.pending_preview:
            messagebox.showinfo("Cargar archivo", "Primero cargá un archivo.", parent=self); return
        PlatformImportPreviewDialog(
            self, self.app, self.pending_file, self.source, self.pending_preview,
            self.pending_mapping, self._save_pending_options, action_word="Usar",
        )

    def _save_pending_options(self, options: dict) -> None:
        self.pending_options = options
        messagebox.showinfo("Vista previa guardada", "La selección quedó lista. Presioná Confirmar importación.", parent=self)


class MercadoPagoPanel(BasePlatformPanel):
    SUBTABS = ("Todos los movimientos", "Resumen del archivo", "Resumen Mensual", "Movimientos Significativos", "Ranking Mercado Pago", "Transferencias Recibidas", "Transferencias Realizadas", "Pagos con QR", "Acreditaciones", "Créditos / Préstamos", "Cobranzas", "Pagos", "Intereses", "Ingresos", "Egresos", "Comisiones", "Retenciones", "Percepciones", "Impuestos", "Contracargos / Devoluciones", "Ajustes", "Movimientos a revisar")

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app, "mp")
        self.direction = tk.StringVar(value="Todos"); self.threshold = tk.StringVar(value=number_ar(app.config_service.get_float("mercado_pago_significativo", 1000)))
        toolbar = ttk.Frame(self); toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(toolbar, text="Cargar archivo", style="Primary.TButton", command=self.stage_mp).pack(side="left")
        ttk.Button(toolbar, text="Vista previa", command=self.preview_staged).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Confirmar importación", command=self.confirm_mp).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Limpiar datos", command=self.clean_all).pack(side="left", padx=(10,4))
        ttk.Button(toolbar, text="Exportar Excel", command=lambda:self.export_current("xlsx")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Exportar PDF", command=lambda:self.export_current("pdf")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Imprimir", command=self.print_current).pack(side="left", padx=4)
        utility = ttk.Frame(self); utility.pack(fill="x", pady=(0, 6))
        ttk.Button(utility, text="Editar clasificación", command=self.edit_classification).pack(side="left")
        ttk.Button(utility, text="Limpiar período", command=self.clean_period).pack(side="left", padx=6)
        ttk.Button(utility, text="Actualizar", command=self.refresh).pack(side="right")
        filters = ttk.Frame(self); filters.pack(fill="x", pady=(0, 7))
        for index, (label, widget) in enumerate((
            ("Cliente", ttk.Combobox(filters, textvariable=self.client, values=tuple(self.clients), state="readonly", width=31)),
            ("Período MM/AAAA", ttk.Entry(filters, textvariable=self.period, width=10)),
            ("Tipo", ttk.Combobox(filters, textvariable=self.kind, values=("Todos", *MP_TYPES), state="readonly", width=19)),
            ("Ingreso / Egreso", ttk.Combobox(filters, textvariable=self.direction, values=("Todos", "Ingreso", "Egreso"), state="readonly", width=10)),
            ("Buscar", ttk.Entry(filters, textvariable=self.search, width=18)),
            ("Significativo desde", ttk.Entry(filters, textvariable=self.threshold, width=11)),
            ("Año",ttk.Entry(filters,textvariable=self.year,width=7)),
            ("Mes",ttk.Entry(filters,textvariable=self.month,width=5)),
            ("Importe mínimo",ttk.Entry(filters,textvariable=self.minimum,width=11)),
            ("Estado",ttk.Entry(filters,textvariable=self.state_filter,width=12)),
        )):
            row, column = divmod(index, 3); base = column * 2
            ttk.Label(filters, text=label).grid(row=row, column=base, sticky="w", padx=(5,2), pady=2); widget.grid(row=row, column=base+1, sticky="ew", padx=(0,8), pady=2); filters.columnconfigure(base+1, weight=1)
        ttk.Button(filters, text="Filtrar", command=self.refresh).grid(row=3, column=6, padx=5)
        self.notebook = TwoRowNotebook(self, columns=11); self.notebook.pack(fill="both", expand=True)
        for title in self.SUBTABS: self.create_table_tab(self.notebook, title)
        self.refresh()

    def stage_mp(self) -> None:
        try: self.stage_file("Cargar archivo de Mercado Pago")
        except Exception as error: messagebox.showerror("No se pudo leer", str(error), parent=self)

    def confirm_mp(self) -> None:
        if not self.pending_file or not self.pending_options:
            messagebox.showinfo("Archivo pendiente", "Cargá un archivo antes de confirmar.", parent=self); return
        client_id = self.client_id()
        if not client_id:
            messagebox.showerror("Cliente requerido", "Debe seleccionar un cliente.", parent=self); return
        try:
            options = self.pending_options
            result = self.app.platform_service.import_mercado_pago(self.pending_file, client_id, options["mapping"], options["duplicate_action"], options["header_row"], options["sheet"], options["selected_rows"], options["row_overrides"])
            self.pending_file = None; self.pending_preview = None; self.pending_options = None
            self.refresh(); messagebox.showinfo("Importación Mercado Pago", f"Leídos: {result['read']}\nImportados: {result['imported']}\nDuplicados: {result['duplicates']}\nA revisar: {result['review']}\nRechazados: {result['rejected']}", parent=self)
        except Exception as error: messagebox.showerror("No se pudo importar", str(error), parent=self)

    def import_file(self) -> None:
        client_id = self.client_id()
        if not client_id: messagebox.showerror("Cliente requerido", "Debe seleccionar un cliente.", parent=self); return
        filename = filedialog.askopenfilename(parent=self, filetypes=(("Excel o CSV", "*.xls *.xlsx *.csv"),))
        if not filename: return
        try:
            preview=self.app.platform_service.preview_file(Path(filename),"mp")
            mapping = self.mapping_for(filename)
            if mapping is None: return
            def confirm(options):
                result=self.app.platform_service.import_mercado_pago(Path(filename),client_id,options["mapping"],options["duplicate_action"],options["header_row"],options["sheet"],options["selected_rows"],options["row_overrides"])
                self.refresh();messagebox.showinfo("Importación Mercado Pago",f"Leídos: {result['read']}\nImportados: {result['imported']}\nDuplicados: {result['duplicates']}\nA revisar: {result['review']}\nRechazados: {result['rejected']}",parent=self)
            PlatformImportPreviewDialog(self,self.app,Path(filename),"mp",preview,mapping,confirm)
        except Exception as error: messagebox.showerror("No se pudo importar", str(error), parent=self)

    def refresh(self) -> None:
        client_id = self.client_id()
        if not client_id:
            for title, table in self.tables.items(): self.current_rows[title] = []; table.fill([])
            return
        try:
            minimum=float(self.minimum.get().replace(".","").replace(",",".") or 0)
            rows = self.app.platform_service.list_mp(client_id, self.period.get().strip(), self.kind.get(), self.direction.get(), self.search.get().strip(),self.year.get().strip(),self.month.get().strip(),minimum,self.state_filter.get().strip())
        except ValueError as error:
            messagebox.showerror("Filtro inválido", str(error), parent=self); return
        summary = self.app.platform_service.mp_summary_rows(rows)
        try:
            text = self.threshold.get().replace(".", "").replace(",", "."); threshold = float(text)
        except ValueError: threshold = 1000.0
        try: self.app.config_service.update("mercado_pago_significativo", str(threshold))
        except ValueError: pass
        significant = [row for row in rows if abs(float(row.get("importe_neto") or 0)) >= threshold]
        ranking = [{"direccion": "Ingreso", "posicion": index, **row} for index, row in enumerate(self.app.platform_service.mp_ranking(client_id, "Ingreso"), 1)] + [{"direccion": "Egreso", "posicion": index, **row} for index, row in enumerate(self.app.platform_service.mp_ranking(client_id, "Egreso"), 1)]
        assignments = {
            "Todos los movimientos": rows, "Resumen del archivo": self.app.platform_service.mp_file_summaries(client_id), "Resumen Mensual": summary,
            "Movimientos Significativos": significant, "Ranking Mercado Pago": ranking,
            "Transferencias Recibidas": [r for r in rows if r["tipo_movimiento"] == "Transferencia recibida"],
            "Transferencias Realizadas": [r for r in rows if r["tipo_movimiento"] == "Transferencia realizada"],
            "Pagos con QR": [r for r in rows if r["tipo_movimiento"] == "Pago con QR"],
            "Acreditaciones": [r for r in rows if r["tipo_movimiento"] == "Acreditación"],
            "Créditos / Préstamos": [r for r in rows if "crédito" in r["tipo_movimiento"].casefold() or "préstamo" in r["tipo_movimiento"].casefold()],
            "Cobranzas": [r for r in rows if r["tipo_movimiento"] == "Cobranza"], "Pagos": [r for r in rows if r["tipo_movimiento"] == "Pago"],
            "Intereses": [r for r in rows if r["tipo_movimiento"] in ("Interés","Rendimientos / Intereses")],
            "Ingresos": [r for r in rows if r["ingreso_egreso"] == "Ingreso"], "Egresos": [r for r in rows if r["ingreso_egreso"] == "Egreso"],
            "Comisiones": [r for r in rows if r["tipo_movimiento"] == "Comisión"],
            "Retenciones": [r for r in rows if r["tipo_movimiento"] == "Retención"], "Percepciones": [r for r in rows if r["tipo_movimiento"] == "Percepción"],
            "Impuestos": [r for r in rows if r["tipo_movimiento"] == "Impuesto"], "Contracargos / Devoluciones": [r for r in rows if r["tipo_movimiento"] in ("Contracargo", "Devolución")],
            "Ajustes": [r for r in rows if r["tipo_movimiento"] == "Ajuste"], "Movimientos a revisar": [r for r in rows if r["tipo_movimiento"] in ("Otro", "A revisar")],
        }
        for title, data in assignments.items(): self.current_rows[title] = data; self.tables[title].fill(data)

    def edit_classification(self) -> None:
        table = self.tables["Todos los movimientos"]; selected = table.tree.selection()
        if not selected: messagebox.showinfo("Seleccionar movimiento", "Seleccioná un movimiento.", parent=self); return
        row = table.row_by_item[selected[0]]
        ClassificationDialog(self, lambda value: (self.app.platform_service.update_mp_classification(int(row["id"]), value), self.refresh()))

    def clean_period(self) -> None:
        client_id = self.client_id(); period = self.period.get().strip()
        if not client_id or not period: messagebox.showinfo("Datos requeridos", "Seleccioná cliente y período.", parent=self); return
        if messagebox.askyesno("Confirmar limpieza", "¿Borrar los movimientos de Mercado Pago del período? Esta acción no se puede deshacer.", parent=self):
            deleted = self.app.platform_service.delete_period("mp", client_id, period); self.refresh(); messagebox.showinfo("Datos eliminados", f"Se eliminaron {deleted} movimientos.", parent=self)

    def clean_all(self) -> None:
        client_id = self.client_id()
        if client_id and messagebox.askyesno("Confirmar limpieza", "¿Borrar todos los movimientos de Mercado Pago del cliente? Esta acción no se puede deshacer.", parent=self):
            deleted = self.app.platform_service.delete_all("mp", client_id); self.refresh(); messagebox.showinfo("Datos eliminados", f"Se eliminaron {deleted} movimientos.", parent=self)


class MercadoLibrePanel(BasePlatformPanel):
    SUBTABS = ("Todas las operaciones", "Ventas Mercado Libre", "Compras Mercado Libre", "Notas de Crédito", "Anulaciones / Devoluciones", "Ventas con reclamo", "Ventas con mediación", "Resumen Mensual", "Productos", "Compradores", "Ventas por provincia", "Proveedores / vendedores principales", "Operaciones significativas", "Operaciones en USD", "Operaciones a revisar")

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app, "ml")
        self.threshold = tk.StringVar(value="500.000,00")
        self.pending_kind = "Ventas"
        toolbar = ttk.Frame(self); toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(toolbar, text="Cargar archivo", style="Primary.TButton", command=self.stage_ml).pack(side="left")
        ttk.Button(toolbar, text="Vista previa", command=self.preview_staged).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Confirmar importación", command=self.confirm_ml).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Limpiar datos", command=self.clean_all).pack(side="left", padx=(10,4))
        ttk.Button(toolbar, text="Exportar Excel", command=lambda:self.export_current("xlsx")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Exportar PDF", command=lambda:self.export_current("pdf")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Imprimir", command=self.print_current).pack(side="left", padx=4)
        utility = ttk.Frame(self); utility.pack(fill="x", pady=(0, 6))
        ttk.Button(utility,text="Editar clasificación",command=self.edit_classification).pack(side="left")
        ttk.Button(utility, text="Limpiar período", command=self.clean_period).pack(side="left", padx=6)
        ttk.Button(utility, text="Actualizar", command=self.refresh).pack(side="right")
        filters = ttk.Frame(self); filters.pack(fill="x", pady=(0, 7))
        for index, (label, widget) in enumerate((
            ("Cliente", ttk.Combobox(filters, textvariable=self.client, values=tuple(self.clients), state="readonly", width=31)),
            ("Período MM/AAAA", ttk.Entry(filters, textvariable=self.period, width=10)),
            ("Tipo", ttk.Combobox(filters, textvariable=self.kind, values=("Todos", "Venta", "Compra", "Nota de crédito", "Anulación"), state="readonly", width=17)),
            ("Buscar", ttk.Entry(filters, textvariable=self.search, width=20)),
            ("Significativo desde", ttk.Entry(filters, textvariable=self.threshold, width=13)),
            ("Año",ttk.Entry(filters,textvariable=self.year,width=7)),
            ("Mes",ttk.Entry(filters,textvariable=self.month,width=5)),
            ("Importe mínimo",ttk.Entry(filters,textvariable=self.minimum,width=11)),
            ("Estado",ttk.Entry(filters,textvariable=self.state_filter,width=13)),
            ("Producto",ttk.Entry(filters,textvariable=self.product_filter,width=15)),
            ("Provincia",ttk.Entry(filters,textvariable=self.province,width=15)),
        )):
            row, column = divmod(index, 3); base = column * 2
            ttk.Label(filters, text=label).grid(row=row, column=base, sticky="w", padx=(6,2), pady=2); widget.grid(row=row, column=base+1, sticky="ew", padx=(0,8), pady=2); filters.columnconfigure(base+1, weight=1)
        ttk.Button(filters, text="Filtrar", command=self.refresh).grid(row=3, column=6, padx=6)
        self.notebook = TwoRowNotebook(self, columns=8); self.notebook.pack(fill="both", expand=True)
        for title in self.SUBTABS: self.create_table_tab(self.notebook, title)
        self.refresh()

    def stage_ml(self) -> None:
        kind = simpledialog.askstring("Tipo de archivo", "Indicá Ventas o Compras:", parent=self, initialvalue=self.pending_kind)
        if kind is None: return
        normalized = kind.strip().casefold()
        if normalized not in ("ventas", "compras"):
            messagebox.showerror("Tipo inválido", "Ingresá Ventas o Compras.", parent=self); return
        self.pending_kind = normalized.title()
        try: self.stage_file(f"Cargar archivo de Mercado Libre - {self.pending_kind}")
        except Exception as error: messagebox.showerror("No se pudo leer", str(error), parent=self)

    def confirm_ml(self) -> None:
        if not self.pending_file or not self.pending_options:
            messagebox.showinfo("Archivo pendiente", "Cargá un archivo antes de confirmar.", parent=self); return
        client_id = self.client_id()
        if not client_id:
            messagebox.showerror("Cliente requerido", "Debe seleccionar un cliente.", parent=self); return
        try:
            options = self.pending_options
            result = self.app.platform_service.import_mercado_libre(self.pending_file, client_id, self.pending_kind, options["mapping"], options["duplicate_action"], options["header_row"], options["sheet"], options["selected_rows"], options["row_overrides"])
            self.pending_file = None; self.pending_preview = None; self.pending_options = None
            self.refresh(); messagebox.showinfo("Importación Mercado Libre", f"Leídos: {result['read']}\nImportados: {result['imported']}\nDuplicados: {result['duplicates']}\nA revisar: {result['review']}\nRechazados: {result['rejected']}", parent=self)
        except Exception as error: messagebox.showerror("No se pudo importar", str(error), parent=self)

    def import_file(self, source_kind: str) -> None:
        client_id = self.client_id()
        if not client_id: messagebox.showerror("Cliente requerido", "Debe seleccionar un cliente.", parent=self); return
        filename = filedialog.askopenfilename(parent=self, filetypes=(("Excel o CSV", "*.xls *.xlsx *.csv"),))
        if not filename: return
        try:
            preview=self.app.platform_service.preview_file(Path(filename),"ml")
            mapping = self.mapping_for(filename)
            if mapping is None: return
            def confirm(options):
                result=self.app.platform_service.import_mercado_libre(Path(filename),client_id,source_kind,options["mapping"],options["duplicate_action"],options["header_row"],options["sheet"],options["selected_rows"],options["row_overrides"])
                self.refresh();messagebox.showinfo("Importación Mercado Libre",f"Leídos: {result['read']}\nImportados: {result['imported']}\nDuplicados: {result['duplicates']}\nA revisar: {result['review']}\nRechazados: {result['rejected']}",parent=self)
            PlatformImportPreviewDialog(self,self.app,Path(filename),"ml",preview,mapping,confirm)
        except Exception as error: messagebox.showerror("No se pudo importar", str(error), parent=self)

    def refresh(self) -> None:
        client_id = self.client_id()
        if not client_id:
            for title, table in self.tables.items(): self.current_rows[title] = []; table.fill([])
            return
        try:
            minimum=float(self.minimum.get().replace(".","").replace(",",".") or 0)
            rows = self.app.platform_service.list_ml(client_id, self.period.get().strip(), self.kind.get(), self.search.get().strip(),self.year.get().strip(),self.month.get().strip(),minimum,self.state_filter.get().strip(),self.province.get().strip(),self.product_filter.get().strip())
        except ValueError as error: messagebox.showerror("Filtro inválido", str(error), parent=self); return
        try: threshold = float(self.threshold.get().replace(".", "").replace(",", "."))
        except ValueError: threshold = 500000.0
        products = self._group(rows,"producto"); counterparts = self._group(rows,"contraparte")
        assignments = {
            "Todas las operaciones": rows, "Ventas Mercado Libre": [r for r in rows if r["tipo_operacion"] == "Venta"],
            "Compras Mercado Libre": [r for r in rows if r["tipo_operacion"] == "Compra"], "Notas de Crédito": [r for r in rows if r["tipo_operacion"] == "Nota de crédito"],
            "Anulaciones / Devoluciones": [r for r in rows if r["tipo_operacion"] in ("Anulación", "Devolución")], "Resumen Mensual": self.app.platform_service.ml_summary_rows(rows),
            "Ventas con reclamo": [r for r in rows if r.get("estado_especial")=="Venta con reclamo"], "Ventas con mediación": [r for r in rows if r.get("estado_especial")=="Venta con mediación"],
            "Productos": products, "Compradores": counterparts, "Ventas por provincia": self._group(rows,"provincia"), "Proveedores / vendedores principales": self._group([r for r in rows if r["tipo_operacion"]=="Compra"],"contraparte"),
            "Operaciones significativas": [r for r in rows if abs(float(r["importe_neto"] or 0)) >= threshold], "Operaciones en USD": [r for r in rows if str(r["moneda"]).upper() not in ("ARS", "$", "PESOS")],
            "Operaciones a revisar": [r for r in rows if not r["id_operacion"] and not r["id_venta"] and not r["numero_comprobante"]],
        }
        for title, data in assignments.items(): self.current_rows[title] = data; self.tables[title].fill(data)

    def edit_classification(self) -> None:
        table=self.tables["Todas las operaciones"];selected=table.tree.selection()
        if not selected:messagebox.showinfo("Seleccionar operación","Seleccioná una operación.",parent=self);return
        row=table.row_by_item[selected[0]];ClassificationDialog(self,lambda value:(self.app.platform_service.update_ml_classification(int(row["id"]),value),self.refresh()),values=("Venta","Compra","Nota de crédito","Anulación","Devolución","Venta con reclamo","Venta con mediación","A revisar"))

    @staticmethod
    def _group(rows: list[dict], key: str) -> list[dict]:
        grouped = {}
        for row in rows:
            name = row.get(key) or "Sin identificar"
            item = grouped.setdefault(name, {key: name, "cantidad_operaciones": 0, "importe_total": 0.0})
            item["cantidad_operaciones"] += 1; item["importe_total"] += float(row.get("importe_neto") or 0)
        return sorted(grouped.values(), key=lambda row: row["importe_total"], reverse=True)

    def clean_period(self) -> None:
        client_id = self.client_id(); period = self.period.get().strip()
        if not client_id or not period: messagebox.showinfo("Datos requeridos", "Seleccioná cliente y período.", parent=self); return
        if messagebox.askyesno("Confirmar limpieza", "¿Borrar las operaciones de Mercado Libre del período? Esta acción no se puede deshacer.", parent=self):
            deleted = self.app.platform_service.delete_period("ml", client_id, period); self.refresh(); messagebox.showinfo("Datos eliminados", f"Se eliminaron {deleted} operaciones.", parent=self)

    def clean_all(self) -> None:
        client_id = self.client_id()
        if client_id and messagebox.askyesno("Confirmar limpieza", "¿Borrar todas las operaciones de Mercado Libre del cliente? Esta acción no se puede deshacer.", parent=self):
            deleted = self.app.platform_service.delete_all("ml", client_id); self.refresh(); messagebox.showinfo("Datos eliminados", f"Se eliminaron {deleted} operaciones.", parent=self)


class PlatformImportPreviewDialog(tk.Toplevel):
    def __init__(self,parent,app,path:Path,source:str,preview:dict,manual_mapping:dict,callback,action_word:str="Importar") -> None:
        super().__init__(parent);self.app=app;self.path=path;self.source=source;self.preview=preview;self.manual_mapping=dict(manual_mapping);self.callback=callback;self.row_overrides={};self.action_word=action_word;self.title("Vista previa de importación");fit_window(self,1250,720);self.transient(parent.winfo_toplevel());self.grab_set()
        body=ttk.Frame(self,padding=14);body.pack(fill="both",expand=True);ttk.Label(body,text="Vista previa antes de guardar",style="Title.TLabel").pack(anchor="w");self.info=tk.StringVar();ttk.Label(body,textvariable=self.info,style="Subtitle.TLabel").pack(anchor="w",pady=(2,7))
        top=ttk.Frame(body);top.pack(fill="x",pady=(0,6));ttk.Label(top,text="Duplicados").pack(side="left");self.duplicate=tk.StringVar(value="skip");ttk.Combobox(top,textvariable=self.duplicate,values=("skip","replace","import"),state="readonly",width=12).pack(side="left",padx=6);ttk.Label(top,text="skip=omitir · replace=reemplazar · import=marcar posible duplicado",style="Subtitle.TLabel").pack(side="left")
        ttk.Button(top,text="Cambiar fila de encabezado",command=self.change_header).pack(side="right");ttk.Button(top,text="Mapear columnas",command=self.remap).pack(side="right",padx=6);ttk.Button(top,text="Reintentar lectura",command=self.retry).pack(side="right")
        self.summary=ttk.LabelFrame(body,text="Resumen superior detectado",padding=7);self.summary.pack(fill="x",pady=(0,6));self.summary_label=ttk.Label(self.summary);self.summary_label.pack(anchor="w")
        holder=ttk.Frame(body);holder.pack(fill="both",expand=True);self.tree=ttk.Treeview(holder,show="headings",selectmode="extended");sy=ttk.Scrollbar(holder,orient="vertical",command=self.tree.yview);sx=ttk.Scrollbar(holder,orient="horizontal",command=self.tree.xview);self.tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);self.tree.grid(row=0,column=0,sticky="nsew");sy.grid(row=0,column=1,sticky="ns");sx.grid(row=1,column=0,sticky="ew");holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1);self.tree.bind("<Double-1>",lambda _event:self.edit_row())
        actions=ttk.Frame(body);actions.pack(fill="x",pady=(8,0));ttk.Button(actions,text="Editar fila seleccionada",command=self.edit_row).pack(side="left");ttk.Button(actions,text="Cancelar",command=self.destroy).pack(side="right");ttk.Button(actions,text=f"{action_word} todo",style="Primary.TButton",command=lambda:self.confirm(False)).pack(side="right",padx=6);ttk.Button(actions,text=f"{action_word} solo seleccionadas",command=lambda:self.confirm(True)).pack(side="right")
        self.fill()
    def fill(self):
        p=self.preview;self.info.set(f"Archivo: {self.path.name} · Hoja: {p['sheet']} · Encabezado: fila {p['header_row']} · Registros: {p['rows']} · Columnas reconocidas: {len(p['mapping'])} · Sin reconocer: {len(p['columns'])-len(set(p['mapping'].values()))}")
        summary=p.get("summary",{});self.summary_label.configure(text=" · ".join(f"{key.replace('_',' ').title()}: {number_ar(value)}" for key,value in summary.items()) or "No se detectó resumen superior")
        columns=tuple(column for column in p["columns"] if not str(column).startswith("__"));self.tree.configure(columns=columns)
        for column in columns:self.tree.heading(column,text=str(column));self.tree.column(column,width=145,minwidth=80)
        for item in self.tree.get_children():self.tree.delete(item)
        for row in p["preview"]:
            index=int(row["_source_index"]);values=self.row_overrides.get(index,row);self.tree.insert("","end",iid=str(index),values=[formatted(str(column),values.get(column,"")) for column in columns])
        self.tree.selection_set(self.tree.get_children())
    def change_header(self):
        value=simpledialog.askinteger("Fila de encabezado","Ingresá el número de fila que contiene los encabezados:",parent=self,initialvalue=self.preview["header_row"],minvalue=1)
        if value is None:return
        try:self.preview=self.app.platform_service.preview_file(self.path,self.source,value,self.preview["sheet"]);self.row_overrides={};self.fill()
        except Exception as error:messagebox.showerror("Encabezado inválido",str(error),parent=self)
    def retry(self):
        try:self.preview=self.app.platform_service.preview_file(self.path,self.source);self.row_overrides={};self.fill()
        except Exception as error:messagebox.showerror("No se pudo releer",str(error),parent=self)
    def remap(self):
        aliases=self.app.platform_service.MP_ALIASES if self.source=="mp" else self.app.platform_service.ML_ALIASES
        field=simpledialog.askstring("Campo interno","Escribí el campo interno a mapear.\nOpciones: "+", ".join(aliases),parent=self)
        if not field:return
        if field not in aliases:messagebox.showerror("Campo inválido","El campo interno no existe.",parent=self);return
        dialog=PlatformMappingDialog(self,[field],self.preview["columns"]);self.wait_window(dialog)
        if dialog.result:self.manual_mapping.update(dialog.result)
    def edit_row(self):
        selected=self.tree.selection()
        if not selected:messagebox.showinfo("Seleccionar fila","Seleccioná una fila.",parent=self);return
        index=int(selected[0]);source=next(row for row in self.preview["preview"] if int(row["_source_index"])==index);row=self.row_overrides.setdefault(index,{key:value for key,value in source.items() if key!="_source_index"});PlatformPreviewRowDialog(self,row,self.fill)
    def confirm(self,selected_only:bool):
        selected={int(item) for item in self.tree.selection()} if selected_only else None
        if selected_only and not selected:messagebox.showinfo("Seleccionar filas","Seleccioná al menos una fila.",parent=self);return
        try:self.callback({"mapping":self.manual_mapping,"duplicate_action":self.duplicate.get(),"header_row":self.preview["header_row"],"sheet":self.preview["sheet"],"selected_rows":selected,"row_overrides":self.row_overrides});self.destroy()
        except Exception as error:messagebox.showerror("No se pudo importar",str(error),parent=self)


class PlatformPreviewRowDialog(tk.Toplevel):
    def __init__(self,parent,row:dict,callback) -> None:
        super().__init__(parent);self.row=row;self.callback=callback;self.title("Editar fila antes de importar");fit_window(self,700,650);self.transient(parent);self.grab_set();frame=ttk.Frame(self,padding=16);frame.pack(fill="both",expand=True);canvas=tk.Canvas(frame,highlightthickness=0);scroll=ttk.Scrollbar(frame,orient="vertical",command=canvas.yview);body=ttk.Frame(canvas);body.bind("<Configure>",lambda _event:canvas.configure(scrollregion=canvas.bbox("all")));canvas.create_window((0,0),window=body,anchor="nw");canvas.configure(yscrollcommand=scroll.set);canvas.pack(side="left",fill="both",expand=True);scroll.pack(side="right",fill="y");self.vars={}
        for index,(key,value) in enumerate(row.items()):self.vars[key]=tk.StringVar(value=str(value));ttk.Label(body,text=str(key)).grid(row=index,column=0,sticky="w",pady=3);ttk.Entry(body,textvariable=self.vars[key],width=55).grid(row=index,column=1,sticky="ew",padx=8,pady=3)
        body.columnconfigure(1,weight=1);ttk.Button(body,text="Guardar cambios",style="Primary.TButton",command=self.save).grid(row=len(row),column=1,sticky="e",pady=10)
    def save(self):self.row.update({key:value.get() for key,value in self.vars.items()});self.callback();self.destroy()


class PlatformMappingDialog(tk.Toplevel):
    def __init__(self, parent, missing: list[str], columns: list[str]) -> None:
        super().__init__(parent); self.title("Mapear columnas"); fit_window(self, 620, 400); self.transient(parent.winfo_toplevel()); self.grab_set(); self.result = None
        body = ttk.Frame(self, padding=18); body.pack(fill="both", expand=True); self.vars = {}
        ttk.Label(body, text="Columnas no reconocidas", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        for index, field in enumerate(missing, 1):
            ttk.Label(body, text=field.replace("_", " ").title()).grid(row=index, column=0, sticky="w", pady=5)
            var = tk.StringVar(); self.vars[field] = var; ttk.Combobox(body, textvariable=var, values=columns, state="readonly").grid(row=index, column=1, sticky="ew", padx=8)
        body.columnconfigure(1, weight=1)
        ttk.Button(body, text="Cancelar", command=self.destroy).grid(row=len(missing)+1, column=0, pady=15)
        ttk.Button(body, text="Continuar", style="Primary.TButton", command=self.accept).grid(row=len(missing)+1, column=1, sticky="e", pady=15)

    def accept(self):
        if any(not var.get() for var in self.vars.values()): messagebox.showerror("Mapeo incompleto", "Seleccioná todas las columnas.", parent=self); return
        self.result = {key: var.get() for key, var in self.vars.items()}; self.destroy()


class ClassificationDialog(tk.Toplevel):
    def __init__(self, parent, callback, values=MP_TYPES) -> None:
        super().__init__(parent); self.title("Clasificación manual"); fit_window(self, 420, 180); self.transient(parent.winfo_toplevel()); self.grab_set(); self.callback = callback
        body = ttk.Frame(self, padding=18); body.pack(fill="both", expand=True); self.value = tk.StringVar(value="A revisar")
        ttk.Label(body, text="Clasificación").pack(anchor="w"); ttk.Combobox(body, textvariable=self.value, values=values, state="readonly").pack(fill="x", pady=8)
        ttk.Button(body, text="Guardar", style="Primary.TButton", command=self.save).pack(anchor="e")

    def save(self): self.callback(self.value.get()); self.destroy()


class ImportHistoryDialog(tk.Toplevel):
    def __init__(self, parent, app, client_id: int, callback) -> None:
        super().__init__(parent); self.app, self.client_id, self.callback = app, client_id, callback; self.title("Historial de importaciones"); fit_window(self, 1150, 620); self.transient(parent.winfo_toplevel()); self.grab_set()
        top = ttk.Frame(self, padding=10); top.pack(fill="x"); ttk.Label(top, text="Historial de importaciones", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Cerrar", command=self.destroy).pack(side="right"); ttk.Button(top, text="Eliminar importación", command=self.delete).pack(side="right", padx=6); ttk.Button(top, text="Exportar Excel", command=lambda:self.export("xlsx")).pack(side="right"); ttk.Button(top, text="Exportar PDF", command=lambda:self.export("pdf")).pack(side="right", padx=5); ttk.Button(top, text="Imprimir", command=lambda:self.export("pdf",True)).pack(side="right")
        self.table = DynamicTable(self); self.table.pack(fill="both", expand=True, padx=10, pady=(0,10)); self.refresh()

    def refresh(self): self.rows = self.app.platform_service.imports(self.client_id); self.table.fill(self.rows)
    def delete(self):
        selected = self.table.tree.selection()
        if not selected: return
        row = self.table.row_by_item[selected[0]]
        if messagebox.askyesno("Confirmar", "¿Borrar todos los datos de este archivo importado?", parent=self):
            self.app.platform_service.delete_import(int(row["id"]), self.client_id); self.refresh(); self.callback()
    def export(self, format_name: str, print_after: bool = False):
        extension=f".{format_name}"; filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, initialfile=f"Historial_importaciones{extension}", filetypes=((format_name.upper(), f"*{extension}"),))
        if not filename:return
        method=self.app.report_service.export_table_excel if format_name=="xlsx" else self.app.report_service.export_table_pdf
        method(Path(filename), "Historial de importaciones", self.rows, self.app.client_service.get_bundle(self.client_id)["client"]["nombre_razon_social"])
        if print_after:
            try:os.startfile(filename,"print")
            except OSError:messagebox.showinfo("PDF listo",f"Abrí e imprimí:\n{filename}",parent=self)
