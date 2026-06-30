from __future__ import annotations

import tkinter as tk
import re
import os
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from utils.formatters import money, normalize_date, percentage
from utils.validators import positive_number

from .common import fit_window, make_tree_sortable
from .date_widgets import DateEntry


class ReportsView(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        ttk.Label(self, text="Reportes", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Exportaciones Excel operativas de todas las áreas.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 18))
        box = ttk.LabelFrame(self, text="Generar reporte", padding=18)
        box.pack(fill="x")
        self.report_map = {
            label: key for key, label in app.report_service.REPORTS.items()
        }
        self.report = tk.StringVar(value=next(iter(self.report_map)))
        clients = app.client_service.list_clients(include_inactive=True)
        self.client_map = {
            "Todos": None,
            **{
                f"{client['nombre_razon_social']} · {client['cuit_cuil']}": client["id"]
                for client in clients
            },
        }
        self.client = tk.StringVar(value="Todos")
        self.date_from = tk.StringVar()
        self.date_to = tk.StringVar()
        self.platform_filter = tk.StringVar()
        self.source_filter=tk.StringVar(value="ARCA + Mercado Libre")
        self.voucher_type_filter=tk.StringVar();self.currency_filter=tk.StringVar()
        ttk.Label(box, text="Reporte").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(
            box,
            textvariable=self.report,
            values=tuple(self.report_map),
            state="readonly",
            width=48,
        ).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(box, text="Cliente").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(
            box,
            textvariable=self.client,
            values=tuple(self.client_map),
            state="readonly",
            width=48,
        ).grid(row=1, column=1, sticky="ew", padx=10)
        ttk.Label(box, text="Desde").grid(row=2, column=0, sticky="w", pady=6)
        DateEntry(box, self.date_from).grid(row=2, column=1, sticky="ew", padx=10)
        ttk.Label(box, text="Hasta").grid(row=3, column=0, sticky="w", pady=6)
        DateEntry(box, self.date_to).grid(row=3, column=1, sticky="ew", padx=10)
        ttk.Label(box, text="Tipo / contraparte").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(box, textvariable=self.platform_filter).grid(row=4, column=1, sticky="ew", padx=10)
        ttk.Label(box, text="Filtro opcional para Mercado Pago o Mercado Libre", style="Subtitle.TLabel").grid(row=4, column=2, sticky="w")
        ttk.Label(box,text="Fuente de matrices").grid(row=5,column=0,sticky="w",pady=6)
        ttk.Combobox(box,textvariable=self.source_filter,values=("ARCA","Mercado Libre","ARCA + Mercado Libre"),state="readonly").grid(row=5,column=1,sticky="ew",padx=10)
        ttk.Label(box,text="Tipo de comprobante").grid(row=6,column=0,sticky="w",pady=6);ttk.Entry(box,textvariable=self.voucher_type_filter).grid(row=6,column=1,sticky="ew",padx=10)
        ttk.Label(box,text="Moneda").grid(row=7,column=0,sticky="w",pady=6);ttk.Combobox(box,textvariable=self.currency_filter,values=("","ARS","USD"),state="readonly").grid(row=7,column=1,sticky="ew",padx=10)
        actions = ttk.Frame(box)
        actions.grid(row=8, column=1, sticky="e", pady=12)
        ttk.Button(
            actions,
            text="Ver / editar últimos 12 meses",
            command=self.open_last_twelve,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions,
            text="Exportar a Excel",
            style="Primary.TButton",
            command=self.export,
        ).pack(side="left")
        ttk.Button(actions, text="Exportar a PDF", command=lambda: self.export_pdf(False)).pack(side="left", padx=8)
        ttk.Button(actions, text="Imprimir", command=lambda: self.export_pdf(True)).pack(side="left")
        box.columnconfigure(1, weight=1)

    def _selected_client_id(self) -> int | None:
        return self.client_map.get(self.client.get())

    def _date_range(self) -> tuple[str, str]:
        date_from = self.date_from.get().strip()
        date_to = self.date_to.get().strip()
        normalized_from = normalize_date(date_from) if date_from else ""
        normalized_to = normalize_date(date_to) if date_to else ""
        if normalized_from and normalized_to and normalized_from > normalized_to:
            raise ValueError("La fecha Desde no puede ser posterior a la fecha Hasta.")
        return normalized_from, normalized_to

    @staticmethod
    def _safe_filename(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*;]+', " - ", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
        return cleaned or "Reporte"

    def open_last_twelve(self) -> None:
        client_id = self._selected_client_id()
        if not client_id:
            messagebox.showinfo(
                "Seleccionar cliente",
                "Elegí un cliente para consultar los últimos 12 meses.",
                parent=self,
            )
            return
        try:
            date_from, date_to = self._date_range()
            LastTwelveMonthsDialog(
                self, self.app, client_id, date_from=date_from, date_to=date_to
            )
        except Exception as error:
            messagebox.showerror("Rango inválido", str(error), parent=self)

    def export(self) -> None:
        filename = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".xlsx",
            filetypes=(("Excel", "*.xlsx"),),
            initialfile=self._safe_filename(self.report.get()) + ".xlsx",
        )
        if not filename:
            return
        try:
            date_from, date_to = self._date_range()
            self.app.report_service.export_named(
                self.report_map[self.report.get()],
                Path(filename),
                self._selected_client_id(),
                date_from,
                date_to,
                self.platform_filter.get().strip(),
                self.source_filter.get(),self.voucher_type_filter.get().strip(),
                self.currency_filter.get().strip(),
            )
            messagebox.showinfo("Reporte creado", f"Se creó:\n{filename}")
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error))

    def export_pdf(self, print_after: bool = False) -> None:
        filename = filedialog.asksaveasfilename(
            parent=self, defaultextension=".pdf", filetypes=(("PDF", "*.pdf"),),
            initialfile=self._safe_filename(self.report.get()) + ".pdf",
        )
        if not filename: return
        try:
            date_from, date_to = self._date_range()
            self.app.report_service.export_named_pdf(
                self.report_map[self.report.get()], Path(filename),
                self._selected_client_id(), date_from, date_to,
                self.platform_filter.get().strip(),
                self.source_filter.get(),self.voucher_type_filter.get().strip(),
                self.currency_filter.get().strip(),
            )
            if print_after:
                try: os.startfile(filename, "print")
                except OSError: messagebox.showinfo("PDF listo", f"Abrí e imprimí:\n{filename}")
            else:
                messagebox.showinfo("Reporte creado", f"Se creó:\n{filename}")
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error))


class LastTwelveMonthsDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        app,
        client_id: int,
        date_from: str = "",
        date_to: str = "",
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.client_id = client_id
        self.date_from = date_from
        self.date_to = date_to
        self.fixed_amount = tk.StringVar(value="0")
        self.title("Últimos 12 meses")
        fit_window(self, 1180, 680)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Últimos 12 meses", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="Incluye el mes actual. Seleccioná un mes para editar su importe de régimen simplificado.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        columns = (
            "mes", "ventas", "compras", "resultado", "porcentaje", "iibb", "simplificado",
        )
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        settings = (
            ("mes", "Mes y año", 140),
            ("ventas", "Ventas", 135),
            ("compras", "Compras", 135),
            ("resultado", "Resultado", 135),
            ("porcentaje", "Compras / ventas", 130),
            ("iibb", "Ingresos Brutos", 135),
            ("simplificado", "Régimen simplificado", 150),
        )
        for column, title, width in settings:
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width)
        yscroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        make_tree_sortable(
            self.tree,
            {"ventas", "compras", "resultado", "porcentaje", "iibb", "simplificado"},
        )
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        editor = ttk.Frame(body)
        editor.pack(fill="x", pady=(12, 0))
        ttk.Label(editor, text="Importe simplificado del mes seleccionado").pack(side="left")
        ttk.Entry(editor, textvariable=self.fixed_amount, width=18).pack(
            side="left", padx=8
        )
        ttk.Button(editor, text="Guardar importe", command=self.save_fixed).pack(side="left")
        ttk.Button(editor, text="Cerrar", command=self.destroy).pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        report = self.app.report_service.last_twelve_months(
            self.client_id,
            date_from=self.date_from,
            date_to=self.date_to,
        )
        self.rows = {row["periodo"]: row for row in report["rows"]}
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in report["rows"]:
            self.tree.insert(
                "",
                "end",
                iid=row["periodo"],
                values=(
                    row["mes"], money(row["ventas"]), money(row["compras"]),
                    money(row["resultado"]), percentage(row["porcentaje_compras"]),
                    money(row["ingresos_brutos"]), money(row["regimen_simplificado"]),
                ),
            )
        totals = report["totals"]
        self.tree.insert(
            "",
            "end",
            iid="TOTAL",
            tags=("total",),
            values=(
                "TOTAL", money(totals["ventas"]), money(totals["compras"]),
                money(totals["resultado"]), percentage(totals["porcentaje_compras"]),
                money(totals["ingresos_brutos"]), money(totals["regimen_simplificado"]),
            ),
        )
        self.tree.tag_configure("total", background="#D9EAF7")

    def _selection_changed(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection or selection[0] == "TOTAL":
            return
        self.fixed_amount.set(str(self.rows[selection[0]]["regimen_simplificado"]))

    def save_fixed(self) -> None:
        selection = self.tree.selection()
        if not selection or selection[0] == "TOTAL":
            messagebox.showinfo(
                "Seleccionar mes", "Seleccioná un mes de la tabla.", parent=self
            )
            return
        try:
            amount = positive_number(
                self.fixed_amount.get(), "Importe simplificado", allow_zero=True
            )
            self.app.iibb_service.save_fixed_amount(
                self.client_id, selection[0], amount
            )
            self.refresh()
            messagebox.showinfo("Importe guardado", "El importe mensual fue actualizado.", parent=self)
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error), parent=self)
