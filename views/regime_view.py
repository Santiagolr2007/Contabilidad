from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from utils.formatters import display_date, money

from .common import ScrollableFrame, clear_frame
from .ledger_view import ClientLedgerDialog


class RegimeView(ttk.Frame):
    """Vista de regímenes; Responsables Inscriptos usa tarjetas de control integral."""

    def __init__(self, parent, app, title: str, regime: str) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        self.title_text = title
        self.regime = regime
        self.is_responsible = regime == "responsable_inscripto"
        self.rows: list[dict] = []

        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        subtitle = "Control integral de Responsables Inscriptos." if self.is_responsible else "Clientes, movimientos, obligaciones y riesgos del régimen fiscal."
        ttk.Label(self, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 10))

        toolbar = ttk.Frame(self); toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="+ Registrar cliente", style="Primary.TButton", command=lambda: app.show_view("clientes", action="new")).pack(side="left")
        if not self.is_responsible:
            ttk.Button(toolbar, text="Abrir legajo integral", command=self.open_ledger).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Exportar Excel", command=lambda: self.export("xlsx")).pack(side="left", padx=(12, 4))
        ttk.Button(toolbar, text="Exportar PDF", command=lambda: self.export("pdf")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Actualizar", command=self.refresh).pack(side="right")

        self.search = tk.StringVar()
        self.year = tk.StringVar(value=str(date.today().year))
        self.month = tk.StringVar(value=str(date.today().month))
        self.state_filter = tk.StringVar(value="Todos")
        self.risk_filter = tk.StringVar(value="Todos")
        self.due_filter = tk.StringVar(value="Todos")
        self.documentation_filter = tk.StringVar(value="Todos")
        self.payment_filter = tk.StringVar(value="Todos")
        filters = ttk.LabelFrame(self, text="Filtros", padding=7); filters.pack(fill="x", pady=(0, 8))
        controls = (
            ("Cliente", ttk.Entry(filters, textvariable=self.search, width=25)),
            ("Estado", ttk.Combobox(filters, textvariable=self.state_filter, values=("Todos", "activo", "inactivo"), state="readonly", width=12)),
            ("Riesgo", ttk.Combobox(filters, textvariable=self.risk_filter, values=("Todos", "Bajo", "Medio", "Alto", "Urgente", "Sin datos"), state="readonly", width=12)),
            ("Año", ttk.Entry(filters, textvariable=self.year, width=8)),
            ("Mes", ttk.Entry(filters, textvariable=self.month, width=6)),
            ("Vencimientos", ttk.Combobox(filters, textvariable=self.due_filter, values=("Todos", "Próximos", "Vencidos", "Sin pendientes"), state="readonly", width=14)),
            ("Documentación", ttk.Combobox(filters, textvariable=self.documentation_filter, values=("Todos", "Pendiente", "Sin pendiente"), state="readonly", width=14)),
            ("Pagos al estudio", ttk.Combobox(filters, textvariable=self.payment_filter, values=("Todos", "Pendiente", "Sin pendiente"), state="readonly", width=14)),
        )
        for index, (label, widget) in enumerate(controls):
            row, group = divmod(index, 4); column = group * 2
            ttk.Label(filters, text=label).grid(row=row, column=column, sticky="w", padx=(4, 2), pady=3)
            widget.grid(row=row, column=column + 1, sticky="ew", padx=(0, 8), pady=3)
            filters.columnconfigure(column + 1, weight=1)
        ttk.Button(filters, text="Aplicar filtros", command=self.refresh).grid(row=2, column=7, sticky="e", padx=4, pady=3)
        self.count = tk.StringVar(value="0 clientes")
        ttk.Label(filters, textvariable=self.count, style="Subtitle.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", padx=4)

        self.tree = None
        self.cards = None
        if self.is_responsible:
            self.cards = ScrollableFrame(self, padding=4)
            self.cards.pack(fill="both", expand=True)
            self.cards.content.columnconfigure(0, weight=1)
            self.cards.content.columnconfigure(1, weight=1)
        else:
            holder = ttk.Frame(self); holder.pack(fill="both", expand=True)
            columns = ("cuit", "actividad", "estado", "alta", "vencimiento", "riesgo", "ventas_anio", "compras_anio", "ventas_12", "compras_12", "pendientes")
            self.tree = ttk.Treeview(holder, columns=columns, show="tree headings", selectmode="browse")
            self.tree.heading("#0", text="Nombre / razón social"); self.tree.column("#0", width=230)
            labels = ("CUIT/CUIL", "Actividad", "Estado", "Fecha alta", "Próximo vencimiento", "Riesgo", "Ventas año", "Compras año", "Ventas 12 meses", "Compras 12 meses", "Pendientes")
            widths = (105, 170, 80, 90, 115, 80, 115, 115, 120, 120, 90)
            for column, label, width in zip(columns, labels, widths):
                self.tree.heading(column, text=label); self.tree.column(column, width=width, minwidth=65)
            sy = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
            sx = ttk.Scrollbar(holder, orient="horizontal", command=self.tree.xview)
            self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
            self.tree.grid(row=0, column=0, sticky="nsew"); sy.grid(row=0, column=1, sticky="ns"); sx.grid(row=1, column=0, sticky="ew")
            holder.rowconfigure(0, weight=1); holder.columnconfigure(0, weight=1)
            self.tree.bind("<Double-1>", lambda _event: self.open_ledger())
        self.refresh()

    def _clients(self) -> list[dict]:
        if self.is_responsible:
            return self.app.dashboard_service.clients_by_category("responsables")
        term = self.regime.replace("_", " ").casefold()
        return [row for row in self.app.dashboard_service.clients_by_category("activos") if term in str(row.get("condicion_fiscal", "")).replace("_", " ").casefold()]

    def _metrics(self, client_id: int, year: int, month: str) -> dict:
        row = self.app.database.query_one(
            """SELECT
               COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=?),0) ventas_periodo,
               COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal=?),0) compras_periodo,
               COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal LIKE ?),0) ventas_anio,
               COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal LIKE ?),0) compras_anio,
               COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_ventas WHERE cliente_id=? AND fecha>=date('now','start of month','-11 months')),0) ventas_12,
               COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_compras WHERE cliente_id=? AND fecha>=date('now','start of month','-11 months')),0) compras_12,
               (SELECT COUNT(*) FROM vencimientos WHERE cliente_id=? AND LOWER(estado) NOT IN ('pagado','cumplido','no corresponde')) vencimientos_pendientes,
               (SELECT COUNT(*) FROM vencimientos WHERE cliente_id=? AND LOWER(estado) NOT IN ('pagado','cumplido','no corresponde') AND fecha_vencimiento<DATE('now')) vencimientos_vencidos,
               (SELECT COUNT(*) FROM vencimientos WHERE cliente_id=? AND LOWER(estado) NOT IN ('pagado','cumplido','no corresponde') AND fecha_vencimiento BETWEEN DATE('now') AND DATE('now','+30 days')) vencimientos_proximos,
               (SELECT COUNT(*) FROM honorarios WHERE cliente_id=? AND saldo_pendiente>0 AND LOWER(estado) NOT IN ('cobrado','bonificado','anulado','no corresponde')) pagos_pendientes,
               (SELECT COUNT(*) FROM cliente_legajo_registros WHERE cliente_id=? AND seccion='documentacion' AND LOWER(estado) NOT IN ('recibido','aprobado','no corresponde')) documentacion_pendiente,
               (SELECT COUNT(*) FROM alertas_fiscales WHERE cliente_id=? AND estado IN ('activa','pendiente')) alertas""",
            (client_id, f"{year:04d}-{month}", client_id, f"{year:04d}-{month}", client_id, f"{year:04d}-%", client_id, f"{year:04d}-%", client_id, client_id, client_id, client_id, client_id, client_id, client_id),
        )
        return dict(row) if row else {}

    def refresh(self) -> None:
        try: year = int(self.year.get())
        except ValueError:
            messagebox.showerror("Año inválido", "Ingresá un año con cuatro dígitos.", parent=self); return
        month = self.month.get().strip().zfill(2)
        if not month.isdigit() or not 1 <= int(month) <= 12:
            messagebox.showerror("Mes inválido", "Ingresá un mes entre 1 y 12.", parent=self); return
        term = self.search.get().casefold().strip()
        clients = [row for row in self._clients() if (not term or term in f"{row['nombre_razon_social']} {row['cuit_cuil']}".casefold()) and (self.state_filter.get() == "Todos" or str(row.get("estado", "")).casefold() == self.state_filter.get().casefold())]
        self.rows = []
        for client in clients:
            client_id = int(client["cliente_id"])
            metrics = self._metrics(client_id, year, month)
            sales = float(metrics.get("ventas_anio") or 0); purchases = float(metrics.get("compras_anio") or 0)
            row = {**client, **metrics, "ventas_anio": sales, "compras_anio": purchases, "iva_debito": sales * .21, "iva_credito": purchases * .21}
            row["saldo_tecnico"] = row["iva_debito"] - row["iva_credito"]
            risk = str(row.get("riesgo_general") or "Sin datos")
            if self.risk_filter.get() != "Todos" and risk.casefold() != self.risk_filter.get().casefold(): continue
            if self.due_filter.get() == "Próximos" and not row.get("vencimientos_proximos"): continue
            if self.due_filter.get() == "Vencidos" and not row.get("vencimientos_vencidos"): continue
            if self.due_filter.get() == "Sin pendientes" and row.get("vencimientos_pendientes"): continue
            if self.documentation_filter.get() == "Pendiente" and not row.get("documentacion_pendiente"): continue
            if self.documentation_filter.get() == "Sin pendiente" and row.get("documentacion_pendiente"): continue
            if self.payment_filter.get() == "Pendiente" and not row.get("pagos_pendientes"): continue
            if self.payment_filter.get() == "Sin pendiente" and row.get("pagos_pendientes"): continue
            self.rows.append(row)
        if self.is_responsible: self._render_cards()
        else: self._render_table()
        self.count.set(f"{len(self.rows)} clientes")

    def _render_table(self) -> None:
        assert self.tree is not None
        for item in self.tree.get_children(): self.tree.delete(item)
        for row in self.rows:
            self.tree.insert("", "end", iid=str(row["cliente_id"]), text=row["nombre_razon_social"], values=(row["cuit_cuil"], row.get("actividad", ""), row.get("estado", ""), display_date(row.get("fecha_alta_estudio")), display_date(row.get("proximo_vencimiento")), row.get("riesgo_general", ""), money(row["ventas_anio"]), money(row["compras_anio"]), money(row.get("ventas_12")), money(row.get("compras_12")), row.get("vencimientos_pendientes", 0)))

    def _card_color(self, row: dict) -> str:
        risk = str(row.get("riesgo_general") or "").casefold()
        if risk in ("alto", "urgente") or row.get("vencimientos_vencidos"): return "#DC2626"
        if row.get("pagos_pendientes") or row.get("documentacion_pendiente"): return "#EA580C"
        if row.get("vencimientos_proximos") or row.get("alertas"): return "#D97706"
        if not any(float(row.get(key) or 0) for key in ("ventas_anio", "compras_anio", "ventas_12", "compras_12")): return "#6B7280"
        return "#15803D"

    def _render_cards(self) -> None:
        assert self.cards is not None
        clear_frame(self.cards.content)
        if not self.rows:
            ttk.Label(self.cards.content, text="No hay Responsables Inscriptos con los filtros seleccionados.", style="Subtitle.TLabel").grid(row=0, column=0, columnspan=2, pady=30)
            return
        for index, row in enumerate(self.rows):
            color = self._card_color(row)
            card = tk.Frame(self.cards.content, bg="white", highlightbackground=color, highlightthickness=3, padx=14, pady=11)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=7, pady=7)
            tk.Label(card, text=row["nombre_razon_social"], bg="white", fg="#17324D", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")
            tk.Label(card, text=f"{row['cuit_cuil']}  ·  Responsable Inscripto  ·  {row.get('estado','')}", bg="white", fg="#475569", anchor="w").pack(fill="x")
            tk.Label(card, text=f"Actividad: {row.get('actividad') or 'Sin datos'}", bg="white", fg="#475569", anchor="w").pack(fill="x", pady=(0, 5))
            lines = (
                f"Ventas año: {money(row['ventas_anio'])}   |   Ventas 12 meses: {money(row.get('ventas_12'))}",
                f"Compras año: {money(row['compras_anio'])}   |   Compras 12 meses: {money(row.get('compras_12'))}",
                f"IVA débito est.: {money(row['iva_debito'])}   |   IVA crédito est.: {money(row['iva_credito'])}",
                f"Saldo técnico estimado: {money(row['saldo_tecnico'])}",
                f"Vencimientos próximos: {row.get('vencimientos_proximos',0)}   |   Pagos pendientes: {row.get('pagos_pendientes',0)}",
                f"Documentación pendiente: {row.get('documentacion_pendiente',0)}   |   Alertas: {row.get('alertas',0)}",
                f"Riesgo general: {row.get('riesgo_general') or 'Sin datos'}",
            )
            for line in lines: tk.Label(card, text=line, bg="white", fg="#1F2937", anchor="w").pack(fill="x")
            tk.Button(card, text="Abrir legajo", command=lambda client_id=int(row["cliente_id"]): self._open_ledger_id(client_id), bg=color, fg="white", activebackground=color, activeforeground="white", relief="flat", padx=12, pady=5).pack(anchor="e", pady=(8, 0))

    def _open_ledger_id(self, client_id: int) -> None:
        ClientLedgerDialog(self, self.app, client_id)

    def open_ledger(self) -> None:
        if self.tree is None or not self.tree.selection():
            messagebox.showinfo("Seleccionar cliente", "Seleccioná un cliente.", parent=self); return
        self._open_ledger_id(int(self.tree.selection()[0]))

    def _export_rows(self) -> list[dict]:
        return [{
            "Cliente": row["nombre_razon_social"], "CUIT / CUIL": row["cuit_cuil"],
            "Condición fiscal": "Responsable Inscripto" if self.is_responsible else row.get("condicion_fiscal", ""),
            "Estado": row.get("estado", ""), "Actividad": row.get("actividad", ""),
            "Ventas año": row.get("ventas_anio", 0), "Ventas últimos 12 meses": row.get("ventas_12", 0),
            "Compras año": row.get("compras_anio", 0), "Compras últimos 12 meses": row.get("compras_12", 0),
            "IVA débito estimado": row.get("iva_debito", 0), "IVA crédito estimado": row.get("iva_credito", 0),
            "Saldo técnico estimado": row.get("saldo_tecnico", 0), "Vencimientos próximos": row.get("vencimientos_proximos", 0),
            "Pagos pendientes": row.get("pagos_pendientes", 0), "Documentación pendiente": row.get("documentacion_pendiente", 0),
            "Riesgo general": row.get("riesgo_general", ""), "Alertas": row.get("alertas", 0),
        } for row in self.rows]

    def export(self, format_name: str) -> None:
        extension = ".xlsx" if format_name == "xlsx" else ".pdf"
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=extension, filetypes=(("Excel", "*.xlsx"),) if format_name == "xlsx" else (("PDF", "*.pdf"),), initialfile=f"{self.title_text} {self.year.get()}{extension}")
        if not filename: return
        try:
            method = self.app.report_service.export_table_excel if format_name == "xlsx" else self.app.report_service.export_table_pdf
            method(Path(filename), self.title_text, self._export_rows(), f"Año {self.year.get()} · Mes {self.month.get()}")
            messagebox.showinfo("Exportación terminada", f"Se creó:\n{filename}", parent=self)
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error), parent=self)
