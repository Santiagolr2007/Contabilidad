from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from utils.formatters import display_date, display_period, money, percentage
from utils.validators import positive_number

from .common import MetricCard, ScrollableFrame, fit_window, make_tree_sortable
from .theme import COLORS
from .accounting_view import VouchersPanel


class MonotributoView(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        self.clients = app.monotributo_service.list_clients()
        self.client_map = {
            f"{item['nombre_razon_social']} · {item['cuit_cuil']}": int(item["id"])
            for item in self.clients
        }
        self.selected = tk.StringVar()

        ttk.Label(self, text="Monotributistas", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Resumen fiscal, acumulados, recategorización estimada y rankings.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        selector = ttk.Frame(self)
        selector.pack(fill="x", pady=(0, 12))
        ttk.Label(selector, text="Cliente").pack(side="left")
        combo = ttk.Combobox(
            selector,
            textvariable=self.selected,
            values=tuple(self.client_map),
            state="readonly",
            width=48,
        )
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(selector, text="Actualizar", command=self.refresh).pack(side="left")

        self.details = ttk.Notebook(self)
        self.details.pack(fill="both", expand=True)

        if self.client_map:
            self.selected.set(next(iter(self.client_map)))
            self.refresh()
        else:
            ttk.Label(
                self,
                text="No hay clientes activos con régimen monotributista.",
                style="Subtitle.TLabel",
            ).pack(anchor="w", pady=20)

    def refresh(self) -> None:
        client_id = self.client_map.get(self.selected.get())
        if not client_id:
            return
        try:
            data = self.app.monotributo_service.dashboard(client_id)
        except Exception as error:
            messagebox.showerror("No se pudo cargar el dashboard", str(error))
            return
        for tab in self.details.tabs():
            self.details.forget(tab)

        self._add_summary_tab(data)
        self.details.add(VouchersPanel(self.details,self.app,"ventas",client_id),text="Ventas")
        self.details.add(VouchersPanel(self.details,self.app,"compras",client_id),text="Compras")
        self._add_activity_tab(data)
        self._add_iibb_tab(client_id)
        self._add_iibb_monthly_tab(client_id)
        self._add_recat_tab(client_id)
        self._add_ranking_tab("Clientes", data["sales_ranking"])
        self._add_ranking_tab("Proveedores", data["purchases_ranking"])
        self._add_alerts_tab(client_id)
        self._add_documentation_tab()
        self._add_reports_tab()

    def _add_summary_tab(self, data: dict) -> None:
        # El resumen es un panel fijo de tarjetas: no debe capturar la rueda ni
        # desplazarse verticalmente dentro de la ficha del monotributista.
        frame = ttk.Frame(self.details, padding=12)
        self.details.add(frame, text="Resumen")
        sales,purchases=data["sales"],data["purchases"]
        risk="Excedido" if data["category_status"]=="excedido" else ("Revisar" if data["active_alerts"] else "Normal")
        cards=(("Actividad fiscal",data["client"].get("actividad_fiscal") or "—",COLORS["green"]),("Denominación",data["client"].get("denominacion") or "—",COLORS["green"]),("Categoría actual",data["client"].get("categoria_actual") or "—",COLORS["blue"]),("Categoría sugerida",data["suggested_category"],COLORS["green"]),("Riesgo fiscal",risk,COLORS["red"] if risk!="Normal" else COLORS["green"]),("Ventas del mes",money(sales.get("mes",0)),COLORS["blue"]),("Ventas año calendario",money(sales.get("anio",0)),COLORS["blue"]),("Ventas últimos 12 meses",money(sales.get("ultimos_12",0)),COLORS["blue"]),("Compras del mes",money(purchases.get("mes",0)),COLORS["amber"]),("Compras año calendario",money(purchases.get("anio",0)),COLORS["amber"]),("Compras últimos 12 meses",money(purchases.get("ultimos_12",0)),COLORS["amber"]),("IIBB estimado",money(data["iibb_estimated"]),COLORS["green"]),("Comprobantes significativos",str(data["significant"]),COLORS["red"]),("USD / alertas",f"{data['usd']} / {data['active_alerts']}",COLORS["red"]))
        for index,(title,value,color) in enumerate(cards):
            frame.columnconfigure(index%3,weight=1)
            MetricCard(frame,title,value,color).grid(row=index//3,column=index%3,sticky="nsew",padx=5,pady=5)

    def _add_activity_tab(self, data: dict) -> None:
        scroll=ScrollableFrame(self.details,padding=16);self.details.add(scroll,text="Monotributo");frame=scroll.content
        client=data["client"]
        items=(("Actividad fiscal",client.get("actividad_fiscal") or "—"),("Denominación",client.get("denominacion") or "—"),("Categoría actual",client.get("categoria_actual") or "—"),("Categoría sugerida",data["suggested_category"]),("Alta monotributo",display_date(client.get("fecha_alta")) or "—"),("Ingresos últimos 12 meses",money(data["sales"].get("ultimos_12",0))),("Ventas año",money(data["sales"].get("anio",0))),("Compras año",money(data["purchases"].get("anio",0))),("Estado pago mensual",client.get("estado_pago_mensual") or "pendiente"),("Estado recategorización",client.get("estado_recategorizacion") or "pendiente"),("Riesgo exclusión",client.get("riesgo_exclusion") or "normal"),("Observaciones",client.get("observaciones_fiscales") or "—"))
        for row,(label,value) in enumerate(items):
            ttk.Label(frame,text=label,font=("Segoe UI",9,"bold")).grid(row=row,column=0,sticky="w",pady=5); ttk.Label(frame,text=value).grid(row=row,column=1,sticky="w",padx=15)
        ttk.Label(frame,text="Código de actividad",font=("Segoe UI",9,"bold")).grid(row=len(items),column=0,sticky="w",pady=5)
        ttk.Label(frame,text=client.get("codigo_actividad") or "—").grid(row=len(items),column=1,sticky="w",padx=15,pady=5)

    def _add_iibb_tab(self, client_id: int) -> None:
        scroll=ScrollableFrame(self.details,padding=12);self.details.add(scroll,text="IIBB");frame=scroll.content
        profile=self.app.iibb_service.get_profile(client_id); vars={k:tk.StringVar(value=(display_date(v) if k.startswith("fecha") else str(v or ""))) for k,v in profile.items()}
        jurisdictions=self.app.iibb_service.list_jurisdictions(client_id); vars["jurisdiccion"].set(", ".join(row["jurisdiccion"] for row in jurisdictions))
        period=tk.StringVar(value=__import__('datetime').date.today().strftime("%m/%Y")); extras={k:tk.StringVar(value="0") for k in ("retenciones","percepciones","saldo","fijo")};extras.update({"presentacion":tk.StringVar(value="pendiente"),"pago":tk.StringVar(value="pendiente"),"vencimiento":tk.StringVar(value="")})
        fields=(("Jurisdicción","jurisdiccion"),("Régimen", "regimen_principal"),("Actividad","actividad"),("Alícuota decimal","alicuota"),("Fecha alta","fecha_alta"),("Fecha baja","fecha_baja"),("Estado","estado"),("Observaciones","observaciones"))
        for row,(label,key) in enumerate(fields):
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky="w",pady=3)
            if key=="regimen_principal": widget=ttk.Combobox(frame,textvariable=vars[key],values=("Régimen simplificado","Régimen general/local","Convenio Multilateral","ARBA - REG SIMP","ARBA REG GENERAL","AGIP REG SIMP","AGIP REG GENERAL","CONVENIO MULTILATERAL"),state="readonly")
            else: widget=ttk.Entry(frame,textvariable=vars[key],state="readonly" if key=="jurisdiccion" else "normal")
            widget.grid(row=row,column=1,sticky="ew",padx=8,pady=3)
        offset=len(fields)
        for index,(label,var) in enumerate((("Período",period),("Retenciones",extras["retenciones"]),("Percepciones",extras["percepciones"]),("Saldo a favor",extras["saldo"]),("Importe fijo simplificado",extras["fijo"]),("Estado presentación",extras["presentacion"]),("Estado pago",extras["pago"]),("Fecha vencimiento",extras["vencimiento"]))):
            ttk.Label(frame,text=label).grid(row=index,column=2,sticky="w",padx=(20,0),pady=3); ttk.Entry(frame,textvariable=var).grid(row=index,column=3,sticky="ew",padx=8,pady=3)
        def calculate():
            try:
                self.app.iibb_service.save_profile(client_id,{k:v.get() for k,v in vars.items()}); result=self.app.iibb_service.calculate_and_save(client_id,period.get(),positive_number(extras["retenciones"].get(),"Retenciones",True),positive_number(extras["percepciones"].get(),"Percepciones",True),positive_number(extras["saldo"].get(),"Saldo",True),positive_number(extras["fijo"].get(),"Importe fijo",True),presentation_status=extras["presentacion"].get(),payment_status=extras["pago"].get(),due_date=extras["vencimiento"].get()); messagebox.showinfo("Ingresos Brutos",f"Base: {money(result['base'])}\nImpuesto: {money(result['determined'])}\nSaldo a pagar: {money(result['payable'])}")
            except Exception as error: messagebox.showerror("No se pudo calcular",str(error))
        ttk.Button(frame,text="Guardar y calcular",style="Primary.TButton",command=calculate).grid(row=offset,column=3,sticky="e",pady=10)
        def manage_jurisdictions():
            from .clients_view import IibbJurisdictionsDialog
            IibbJurisdictionsDialog(frame,self.app,client_id,lambda:vars["jurisdiccion"].set(", ".join(row["jurisdiccion"] for row in self.app.iibb_service.list_jurisdictions(client_id))))
        ttk.Button(frame,text="Jurisdicciones / porcentajes",command=manage_jurisdictions).grid(row=offset,column=1,sticky="w",pady=10)
        ttk.Button(frame,text="Agregar jurisdicción Convenio Multilateral",command=lambda:ConvenioDialog(frame,self.app,client_id,period.get())).grid(row=offset+1,column=3,sticky="e",pady=4); frame.columnconfigure(1,weight=1); frame.columnconfigure(3,weight=1)

    def _add_iibb_monthly_tab(self, client_id: int) -> None:
        frame = ttk.Frame(self.details, padding=10)
        self.details.add(frame, text="Ingresos Brutos mensuales")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 8))
        period = tk.StringVar(value=date.today().strftime("%m/%Y"))
        retentions = tk.StringVar(value="0")
        fixed_amount = tk.StringVar(value="0")
        ttk.Label(controls, text="Período").pack(side="left")
        ttk.Entry(controls, textvariable=period, width=10).pack(side="left", padx=(6, 14))
        ttk.Label(controls, text="Retenciones").pack(side="left")
        ttk.Entry(controls, textvariable=retentions, width=13).pack(side="left", padx=(6, 14))
        ttk.Label(controls, text="Importe simplificado").pack(side="left")
        ttk.Entry(controls, textvariable=fixed_amount, width=13).pack(side="left", padx=(6, 14))

        summary = ttk.Frame(frame)
        summary.pack(fill="x", pady=(0, 8))
        summary_vars = {
            "base": tk.StringVar(value=money(0)),
            "rate": tk.StringVar(value="3.5%"),
            "determined": tk.StringVar(value=money(0)),
            "retentions": tk.StringVar(value=money(0)),
            "payable": tk.StringVar(value=money(0)),
        }
        for column, (label, key) in enumerate(
            (
                ("Ventas netas", "base"),
                ("Alícuota", "rate"),
                ("IIBB determinado", "determined"),
                ("Retenciones", "retentions"),
                ("Importe por pagar", "payable"),
            )
        ):
            box = ttk.LabelFrame(summary, text=label, padding=8)
            box.grid(row=0, column=column, sticky="nsew", padx=4)
            ttk.Label(box, textvariable=summary_vars[key]).pack()
            summary.columnconfigure(column, weight=1)

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        columns = (
            "fecha", "tipo", "pv", "numero", "contraparte", "documento",
            "importe", "alicuota", "impuesto",
        )
        tree = ttk.Treeview(table, columns=columns, show="headings")
        settings = (
            ("fecha", "Fecha", 90),
            ("tipo", "Comprobante", 140),
            ("pv", "Punto venta", 80),
            ("numero", "Número", 90),
            ("contraparte", "Cliente", 190),
            ("documento", "CUIT / DNI", 110),
            ("importe", "Importe venta", 120),
            ("alicuota", "Alícuota IIBB", 95),
            ("impuesto", "Impuesto", 120),
        )
        for column, title, width in settings:
            tree.heading(column, text=title)
            tree.column(column, width=width)
        yscroll = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        make_tree_sortable(tree, {"importe", "alicuota", "impuesto"})

        def load_period() -> None:
            try:
                detail = self.app.iibb_service.monthly_detail(client_id, period.get())
                for item in tree.get_children():
                    tree.delete(item)
                for row in detail["rows"]:
                    tree.insert(
                        "",
                        "end",
                        values=(
                            display_date(row["fecha"]), row["tipo_comprobante"], row["punto_venta"],
                            row["numero_comprobante"], row["contraparte_nombre"],
                            row["contraparte_documento"], money(row["importe_venta"]),
                            percentage(row["alicuota"]), money(row["impuesto_calculado"]),
                        ),
                    )
                retentions.set(str(detail["retentions"]))
                fixed_amount.set(str(detail["fixed_amount"]))
                summary_vars["base"].set(money(detail["base"]))
                summary_vars["rate"].set(percentage(detail["rate"]))
                summary_vars["determined"].set(money(detail["determined"]))
                summary_vars["retentions"].set(money(detail["retentions"]))
                summary_vars["payable"].set(money(detail["payable"]))
            except Exception as error:
                messagebox.showerror("No se pudo consultar IIBB", str(error))

        def save_calculation() -> None:
            try:
                result = self.app.iibb_service.calculate_and_save(
                    client_id,
                    period.get(),
                    retentions=positive_number(
                        retentions.get(), "Retenciones", allow_zero=True
                    ),
                    fixed_amount=positive_number(
                        fixed_amount.get(), "Importe simplificado", allow_zero=True
                    ),
                )
                load_period()
                messagebox.showinfo(
                    "Ingresos Brutos",
                    f"Impuesto determinado: {money(result['determined'])}\n"
                    f"Importe por pagar: {money(result['payable'])}",
                )
            except Exception as error:
                messagebox.showerror("No se pudo calcular", str(error))

        ttk.Button(controls, text="Consultar", command=load_period).pack(side="left")
        ttk.Button(
            controls,
            text="Guardar y calcular",
            style="Primary.TButton",
            command=save_calculation,
        ).pack(side="right")
        load_period()

    def _add_recat_tab(self, client_id: int) -> None:
        scroll=ScrollableFrame(self.details,padding=14);self.details.add(scroll,text="Recateg.");frame=scroll.content
        calc=self.app.recategorization_service.calculate(client_id)
        for row,(label,key) in enumerate((("Cliente","cliente"),("Actividad fiscal","actividad_fiscal"),("Denominación","denominacion"),("Período desde","periodo_desde"),("Período hasta","periodo_hasta"),("Ventas 12 meses","ventas"),("Categoría actual","categoria_actual"),("Categoría sugerida","categoria_sugerida"),("Diferencia al tope","diferencia_tope"),("Estado","estado"))):
            value=money(calc[key]) if key in ("ventas","diferencia_tope") else (display_period(calc[key]) if key.startswith("periodo") else calc[key]); ttk.Label(frame,text=label,font=("Segoe UI",9,"bold")).grid(row=row,column=0,sticky="w",pady=3); ttk.Label(frame,text=value).grid(row=row,column=1,sticky="w",padx=10)
        extras={k:tk.StringVar(value="0") for k in ("alquileres","energia","superficie","precio_unitario_maximo")}
        for index,(key,var) in enumerate(extras.items()): ttk.Label(frame,text=key.replace("_"," ").title()).grid(row=index,column=2,sticky="w",padx=(25,0)); ttk.Entry(frame,textvariable=var).grid(row=index,column=3,padx=8,pady=3)
        def save():
            try:self.app.recategorization_service.save(client_id,{k:float(v.get()) for k,v in extras.items()});messagebox.showinfo("Recategorización","Análisis guardado.")
            except Exception as error:messagebox.showerror("No se pudo guardar",str(error))
        ttk.Button(frame,text="Guardar análisis",style="Primary.TButton",command=save).grid(row=5,column=3,sticky="e",pady=8)

    def _add_alerts_tab(self, client_id: int) -> None:
        frame = ttk.Frame(self.details, padding=10)
        self.details.add(frame, text="Alertas")
        ttk.Button(
            frame,
            text="Recalcular alertas",
            command=lambda: self._refresh_alerts(client_id),
        ).pack(anchor="e", pady=(0, 6))
        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        columns = ("periodo", "tipo", "descripcion", "gravedad", "estado")
        tree = ttk.Treeview(table, columns=columns, show="headings")
        widths = {"periodo": 90, "tipo": 190, "descripcion": 480, "gravedad": 90, "estado": 100}
        for column in columns:
            tree.heading(column, text=column.title())
            tree.column(column, width=widths[column], minwidth=70)
        self._add_tree_scrollbars(table, tree)
        for row in self.app.database.query(
            "SELECT * FROM alertas_fiscales WHERE cliente_id=? ORDER BY fecha_creacion DESC",
            (client_id,),
        ):
            tree.insert("", "end", values=(display_period(row["periodo"]), row["tipo_alerta"], row["descripcion"], row["gravedad"], row["estado"]))

    def _refresh_alerts(self, client_id: int) -> None:
        try:
            count=self.app.alert_service.refresh(client_id); messagebox.showinfo("Alertas",f"Se generaron {count} alertas automáticas."); self.refresh()
        except Exception as error: messagebox.showerror("No se pudieron recalcular",str(error))

    def _add_documentation_tab(self) -> None:
        frame=ttk.Frame(self.details,padding=18);self.details.add(frame,text="Documentos")
        ttk.Button(frame,text="Abrir documentación y tareas",style="Primary.TButton",command=lambda:self.app.show_view("documentacion")).pack(anchor="w",pady=5)

    def _add_reports_tab(self) -> None:
        frame=ttk.Frame(self.details,padding=18);self.details.add(frame,text="Reportes")
        ttk.Button(frame,text="Abrir reportes Excel",style="Primary.TButton",command=lambda:self.app.show_view("reportes")).pack(anchor="w",pady=5)

    def _add_monthly_tab(self, title: str, rows: list[dict]) -> None:
        frame = ttk.Frame(self.details, padding=10)
        self.details.add(frame, text=title)
        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        columns = ("periodo", "facturas", "nc", "nd", "neto", "cantidad")
        tree = ttk.Treeview(table, columns=columns, show="headings")
        settings = (
            ("periodo", "Período", 90),
            ("facturas", "Facturas", 130),
            ("nc", "Notas de crédito", 130),
            ("nd", "Notas de débito", 130),
            ("neto", "Neto", 130),
            ("cantidad", "Cantidad", 80),
        )
        for column, label, width in settings:
            tree.heading(column, text=label)
            tree.column(column, width=width)
        self._add_tree_scrollbars(table, tree)
        make_tree_sortable(tree, {"cantidad", "total", "participacion"})
        for row in rows:
            tree.insert(
                "",
                "end",
                values=(
                    display_period(row["periodo"]),
                    money(row["facturas"]),
                    money(row["notas_credito"]),
                    money(row["notas_debito"]),
                    money(row["total_neto"]),
                    row["cantidad"],
                ),
            )

    def _add_ranking_tab(self, title: str, rows: list[dict]) -> None:
        frame = ttk.Frame(self.details, padding=10)
        self.details.add(frame, text=title)
        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        columns = ("puesto", "nombre", "documento", "cantidad", "total", "participacion")
        tree = ttk.Treeview(table, columns=columns, show="headings")
        settings = (
            ("puesto", "Puesto", 60),
            ("nombre", "Nombre", 340),
            ("documento", "CUIT/DNI", 110),
            ("cantidad", "Comprobantes", 90),
            ("total", "Total", 130),
            ("participacion", "% total", 80),
        )
        for column, label, width in settings:
            tree.heading(column, text=label)
            tree.column(column, width=width)
        self._add_tree_scrollbars(table, tree)
        make_tree_sortable(tree, {"cantidad", "total", "participacion"})
        for row in rows:
            tree.insert(
                "",
                "end",
                values=(
                    row["puesto"],
                    row["contraparte_nombre"],
                    row["contraparte_documento"],
                    row["cantidad"],
                    money(row["total"]),
                    percentage(row["porcentaje"]),
                ),
            )

    @staticmethod
    def _add_tree_scrollbars(parent, tree: ttk.Treeview) -> None:
        yscroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)


class ConvenioDialog(tk.Toplevel):
    def __init__(self,parent,app,client_id:int,period:str):
        super().__init__(parent);self.app=app;self.client_id=client_id;self.period=period;self.title("Jurisdicción de Convenio Multilateral");fit_window(self,560,400);self.transient(parent.winfo_toplevel());self.grab_set()
        self.vars={k:tk.StringVar() for k in ("jurisdiccion","coeficiente","alicuota","observaciones")};body=ttk.Frame(self,padding=18);body.pack(fill="both",expand=True)
        for row,(key,label) in enumerate((("jurisdiccion","Jurisdicción"),("coeficiente","Coeficiente"),("alicuota","Alícuota"),("observaciones","Observaciones"))):ttk.Label(body,text=label).grid(row=row,column=0,sticky="w",pady=5);ttk.Entry(body,textvariable=self.vars[key]).grid(row=row,column=1,sticky="ew",padx=8,pady=5)
        body.columnconfigure(1,weight=1);ttk.Button(body,text="Guardar jurisdicción",style="Primary.TButton",command=self.save).grid(row=5,column=1,sticky="e",pady=12)
    def save(self):
        try:self.app.iibb_service.add_convenio_jurisdiction(self.client_id,self.period,self.vars["jurisdiccion"].get(),float(self.vars["coeficiente"].get().replace(",",".")),float(self.vars["alicuota"].get().replace(",",".")),self.vars["observaciones"].get());messagebox.showinfo("Convenio Multilateral","Jurisdicción guardada.",parent=self);self.destroy()
        except Exception as error:messagebox.showerror("No se pudo guardar",str(error),parent=self)
