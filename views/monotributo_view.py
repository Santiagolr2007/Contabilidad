from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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
        ttk.Button(selector, text="Importar categorías ARCA", command=self.import_categories).pack(side="left", padx=8)
        ttk.Button(selector,text="Historial categorías",command=self.open_categories_history).pack(side="left")
        ttk.Button(selector,text="Cambios manuales",command=lambda:CategoryChangesDialog(self,self.app)).pack(side="left",padx=6)

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
        self._add_categories_tab(client_id)
        self._add_recat_tab(client_id)
        self._add_ranking_tab("Clientes", data["sales_ranking"])
        self._add_ranking_tab("Proveedores", data["purchases_ranking"])
        self._add_alerts_tab(client_id)
        self._add_documentation_tab()
        self._add_reports_tab()

    def import_categories(self) -> None:
        filename=filedialog.askopenfilename(parent=self,title="Importar categorías de Monotributo ARCA",filetypes=(("Documento PDF","*.pdf"),))
        if not filename:return
        try:
            preview=self.app.monotributo_categories_service.preview_pdf(Path(filename));CategoriesImportPreviewDialog(self,self.app,preview,self.refresh)
        except Exception as error:messagebox.showerror("No se pudo leer el PDF",str(error),parent=self)

    def open_categories_history(self) -> None:
        from .administrative_view import AccountingImportHistoryDialog
        AccountingImportHistoryDialog(self,self.app,"ARCA Monotributo Categorías PDF")

    def _add_categories_tab(self, client_id: int) -> None:
        frame=ttk.Frame(self.details,padding=10);self.details.add(frame,text="Categorías / Límites")
        payment=self.app.monotributo_categories_service.client_payment(client_id)
        summary=ttk.LabelFrame(frame,text="Valor mensual del cliente",padding=8);summary.pack(fill="x",pady=(0,8))
        text=(f"Categoría {payment['category'] or '—'} · {payment['activity'] or '—'} · "
              f"Impuesto integrado {money(payment['integrated_tax'])} + SIPA {money(payment['sipa'])} + "
              f"Obra social {money(payment['health'])} + adherentes {money(payment['adherents'])} = "
              f"Total ajustado {money(payment['adjusted_total'])} · Vigencia {display_date(payment['vigencia']) or '—'} · {payment['source'] or 'sin fuente'}")
        ttk.Label(summary,text=text,wraplength=1100).pack(anchor="w")
        actions=ttk.Frame(frame);actions.pack(fill="x",pady=(0,5))
        holder=ttk.Frame(frame);holder.pack(fill="both",expand=True)
        columns=("categoria","vigencia","ingresos","superficie","energia","alquileres","precio","integrado_s","integrado_v","sipa","obra","total_s","total_v","estado","fuente")
        tree=ttk.Treeview(holder,columns=columns,show="headings")
        labels=("Categoría","Vigencia","Ingresos brutos","Superficie","Energía","Alquileres","Precio unitario","Imp. servicios","Imp. ventas","SIPA","Obra social","Total servicios","Total ventas","Estado","Fuente")
        for column,label in zip(columns,labels):tree.heading(column,text=label);tree.column(column,width=105,minwidth=70)
        self._add_tree_scrollbars(holder,tree)
        versions=self.app.monotributo_categories_service.list_versions()
        for row in versions:
            tree.insert("","end",iid=str(row["id"]),values=(row["categoria"],display_date(row["vigencia_desde"]),money(row["tope_ingresos"]),row["tope_superficie"],row["tope_energia"],money(row["tope_alquileres"]),money(row["precio_unitario_maximo"]),money(row["impuesto_integrado_servicios"]),money(row["impuesto_integrado_ventas"]),money(row["aporte_sipa"]),money(row["aporte_obra_social"]),money(row["total_servicios"]),money(row["total_ventas"]),row["estado"],row["fuente"]))
        def edit_existing():
            selected=tree.selection()
            if not selected:messagebox.showinfo("Seleccionar categoría","Seleccioná una categoría.",parent=self);return
            source=next(row for row in versions if row["id"]==int(selected[0]));ExistingCategoryDialog(self,self.app,source,self.refresh)
        ttk.Button(actions,text="Modificar categoría seleccionada",command=edit_existing).pack(side="left")
        def add_manual():
            row={"categoria":"A","vigencia_desde":date.today().isoformat(),"estado":"Vigente","fuente":"Carga manual","observaciones":""}
            for field in self.app.monotributo_categories_service.FIELDS:row[field]=0
            ManualCategoryDialog(self,self.app,row,self.refresh)
        ttk.Button(actions,text="Agregar categoría manual",command=add_manual).pack(side="left",padx=6)
        tree.bind("<Double-1>",lambda _event:edit_existing())

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
        display_fields=(("Cliente","cliente"),("Actividad fiscal","actividad_fiscal"),("Denominación","denominacion"),("Período desde","periodo_desde"),("Período hasta","periodo_hasta"),("Ventas 12 meses","ventas"),("Límite categoría actual","limite_categoria"),("Porcentaje utilizado","porcentaje_utilizado"),("Diferencia al límite","diferencia_tope"),("Límite categoría máxima","limite_maximo"),("Diferencia a categoría máxima","diferencia_maximo"),("Categoría actual","categoria_actual"),("Categoría sugerida","categoria_sugerida"),("Estado","estado"))
        for row,(label,key) in enumerate(display_fields):
            value=percentage(calc[key]) if key=="porcentaje_utilizado" else money(calc[key]) if key in ("ventas","limite_categoria","diferencia_tope","limite_maximo","diferencia_maximo") else (display_period(calc[key]) if key.startswith("periodo") else calc[key]); ttk.Label(frame,text=label,font=("Segoe UI",9,"bold")).grid(row=row,column=0,sticky="w",pady=3); ttk.Label(frame,text=value).grid(row=row,column=1,sticky="w",padx=10)
        extras={k:tk.StringVar(value="0") for k in ("alquileres","energia","superficie","precio_unitario_maximo")}
        for index,(key,var) in enumerate(extras.items()): ttk.Label(frame,text=key.replace("_"," ").title()).grid(row=index,column=2,sticky="w",padx=(25,0)); ttk.Entry(frame,textvariable=var).grid(row=index,column=3,padx=8,pady=3)
        def save():
            try:
                values={k:float(v.get().replace(",",".")) for k,v in extras.items()};result=self.app.recategorization_service.calculate(client_id,values);self.app.recategorization_service.save(client_id,values)
                parameter_text="\n".join(f"{key.replace('_',' ').title()}: {item['estado']} ({item['actual']} / {item['limite']})" for key,item in result["controles_parametros"].items());messagebox.showinfo("Recategorización",f"Análisis guardado.\nEstado: {result['estado']}\n\n{parameter_text}")
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


class CategoryChangesDialog(tk.Toplevel):
    def __init__(self,parent,app) -> None:
        super().__init__(parent);self.app=app;self.title("Historial de cambios de categorías");fit_window(self,1000,520);self.transient(parent.winfo_toplevel());self.grab_set();body=ttk.Frame(self,padding=14);body.pack(fill="both",expand=True);actions=ttk.Frame(body);actions.pack(fill="x",pady=(0,6));ttk.Button(actions,text="Exportar Excel",command=lambda:self.export("xlsx")).pack(side="left");ttk.Button(actions,text="Exportar PDF",command=lambda:self.export("pdf")).pack(side="left",padx=5)
        holder=ttk.Frame(body);holder.pack(fill="both",expand=True);columns=("categoria","vigencia_desde","campo","valor_anterior","valor_nuevo","responsable","motivo","fecha");self.tree=ttk.Treeview(holder,columns=columns,show="headings")
        for c in columns:self.tree.heading(c,text=c.replace("_"," ").title());self.tree.column(c,width=125)
        MonotributoView._add_tree_scrollbars(holder,self.tree);self.rows=app.monotributo_categories_service.change_history()
        for row in self.rows:self.tree.insert("","end",values=tuple(display_date(row[c]) if c in ("vigencia_desde","fecha") else row[c] for c in columns))
    def export(self,format_name):
        extension=f".{format_name}";filename=filedialog.asksaveasfilename(parent=self,defaultextension=extension,filetypes=((format_name.upper(),f"*{extension}"),),initialfile=f"Historial cambios categorías{extension}")
        if not filename:return
        method=self.app.report_service.export_table_excel if format_name=="xlsx" else self.app.report_service.export_table_pdf;method(Path(filename),"Historial de cambios de categorías",self.rows,"Monotributo");messagebox.showinfo("Exportación terminada",f"Se creó:\n{filename}",parent=self)


class CategoriesImportPreviewDialog(tk.Toplevel):
    def __init__(self,parent,app,preview:dict,callback) -> None:
        super().__init__(parent);self.app=app;self.preview=preview;self.callback=callback;self.title("Vista previa de categorías Monotributo ARCA");fit_window(self,1260,700);self.transient(parent.winfo_toplevel());self.grab_set()
        body=ttk.Frame(self,padding=14);body.pack(fill="both",expand=True);ttk.Label(body,text="Vista previa de categorías Monotributo ARCA",style="Title.TLabel").pack(anchor="w");ttk.Label(body,text=f"Vigencia detectada: {display_date(preview['vigencia'])} · Editá cualquier valor dudoso antes de confirmar.",style="Subtitle.TLabel").pack(anchor="w",pady=(2,8))
        holder=ttk.Frame(body);holder.pack(fill="both",expand=True);columns=("accion","categoria","ingresos","superficie","energia","alquileres","precio","imp_s","imp_v","sipa","obra","total_s","total_v","confianza")
        self.tree=ttk.Treeview(holder,columns=columns,show="headings");labels=("Acción","Cat.","Ingresos","Superficie","Energía","Alquileres","Precio","Imp. servicios","Imp. ventas","SIPA","Obra social","Total servicios","Total ventas","Confianza")
        for c,l in zip(columns,labels):self.tree.heading(c,text=l);self.tree.column(c,width=95,minwidth=65)
        MonotributoView._add_tree_scrollbars(holder,self.tree)
        for index in range(len(preview["records"])):self.redraw(index)
        controls=ttk.Frame(body);controls.pack(fill="x",pady=(9,0));ttk.Button(controls,text="Importar / no importar",command=self.toggle).pack(side="left");ttk.Button(controls,text="Editar / mapear seleccionado",command=self.edit).pack(side="left",padx=6);ttk.Button(controls,text="Reintentar lectura",command=self.retry).pack(side="left");ttk.Button(controls,text="Cancelar",command=self.destroy).pack(side="right");ttk.Button(controls,text="Confirmar importación",style="Primary.TButton",command=self.confirm).pack(side="right",padx=6)

    def redraw(self,index:int):
        r=self.preview["records"][index];values=(r["accion"],r["categoria"],money(r["tope_ingresos"]),r["tope_superficie"],r["tope_energia"],money(r["tope_alquileres"]),money(r["precio_unitario_maximo"]),money(r["impuesto_integrado_servicios"]),money(r["impuesto_integrado_ventas"]),money(r["aporte_sipa"]),money(r["aporte_obra_social"]),money(r["total_servicios"]),money(r["total_ventas"]),r["confianza"])
        if self.tree.exists(str(index)):self.tree.item(str(index),values=values)
        else:self.tree.insert("","end",iid=str(index),values=values)
    def toggle(self):
        s=self.tree.selection()
        if not s:return
        i=int(s[0]);r=self.preview["records"][i];r["accion"]="No importar" if r["accion"]=="Importar" else "Importar";self.redraw(i)
    def edit(self):
        s=self.tree.selection()
        if s:CategoryPreviewRowDialog(self,self.preview["records"][int(s[0])],lambda:self.redraw(int(s[0])))
    def retry(self):
        try:
            self.preview=self.app.monotributo_categories_service.preview_pdf(Path(self.preview["path"]));
            for item in self.tree.get_children():self.tree.delete(item)
            for index in range(len(self.preview["records"])):self.redraw(index)
        except Exception as error:messagebox.showerror("No se pudo releer",str(error),parent=self)
    def confirm(self):
        existing=self.app.database.query_one("SELECT id FROM categorias_monotributo WHERE vigencia_desde=? LIMIT 1",(self.preview["vigencia"],));action="replace"
        if existing:
            answer=messagebox.askyesnocancel("Versión existente","Ya existe esta vigencia.\nSí: reemplazar · No: omitir duplicados · Cancelar: volver",parent=self)
            if answer is None:return
            action="replace" if answer else "skip"
        try:
            result=self.app.monotributo_categories_service.import_preview(self.preview,action);self.callback();messagebox.showinfo("Categorías importadas",f"Importadas: {result['imported']}\nDuplicadas: {result['duplicates']}\nA revisar: {result['review']}",parent=self);self.destroy()
        except Exception as error:messagebox.showerror("No se pudo importar",str(error),parent=self)


class CategoryPreviewRowDialog(tk.Toplevel):
    def __init__(self,parent,row:dict,callback) -> None:
        super().__init__(parent);self.row=row;self.callback=callback;self.title(f"Editar categoría {row['categoria']}");fit_window(self,620,650);self.transient(parent);self.grab_set();scroll=ScrollableFrame(self,padding=16);scroll.pack(fill="both",expand=True);frame=scroll.content
        fields=(("categoria","Categoría"),("vigencia_desde","Vigencia AAAA-MM-DD"),("tope_ingresos","Ingresos brutos"),("tope_superficie","Superficie"),("tope_energia","Energía"),("tope_alquileres","Alquileres"),("precio_unitario_maximo","Precio unitario"),("impuesto_integrado_servicios","Impuesto servicios"),("impuesto_integrado_ventas","Impuesto ventas"),("aporte_sipa","SIPA"),("aporte_obra_social","Obra social"),("total_servicios","Total servicios"),("total_ventas","Total ventas"),("observaciones","Observaciones"));self.vars={}
        for i,(k,l) in enumerate(fields):self.vars[k]=tk.StringVar(value=str(row.get(k,"")));ttk.Label(frame,text=l).grid(row=i,column=0,sticky="w",pady=3);ttk.Entry(frame,textvariable=self.vars[k]).grid(row=i,column=1,sticky="ew",padx=8,pady=3)
        frame.columnconfigure(1,weight=1);ttk.Button(frame,text="Guardar",style="Primary.TButton",command=self.save).grid(row=len(fields),column=1,sticky="e",pady=8)
    def save(self):
        try:
            for key,var in self.vars.items():self.row[key]=var.get().strip() if key in ("categoria","vigencia_desde","observaciones") else float(var.get().replace(".","").replace(",",".") or 0)
            self.row["confianza"]="Alta";self.callback();self.destroy()
        except Exception as error:messagebox.showerror("Dato inválido",str(error),parent=self)


class ExistingCategoryDialog(CategoryPreviewRowDialog):
    def __init__(self,parent,app,row:dict,callback) -> None:
        self.app=app;self.category_id=int(row["id"]);self.external_callback=callback
        super().__init__(parent,row,self._persist)
        self.title(f"Modificar categoría {row['categoria']}")
    def _persist(self) -> None:
        self.app.monotributo_categories_service.update(self.category_id,self.row,reason="Modificación manual desde Monotributo")
        self.external_callback()


class ManualCategoryDialog(CategoryPreviewRowDialog):
    def __init__(self,parent,app,row:dict,callback) -> None:
        self.app=app;self.external_callback=callback;super().__init__(parent,row,self._persist);self.title("Agregar categoría manual")
    def _persist(self):self.app.monotributo_categories_service.save_manual(self.row);self.external_callback()


class ConvenioDialog(tk.Toplevel):
    def __init__(self,parent,app,client_id:int,period:str):
        super().__init__(parent);self.app=app;self.client_id=client_id;self.period=period;self.title("Jurisdicción de Convenio Multilateral");fit_window(self,560,400);self.transient(parent.winfo_toplevel());self.grab_set()
        self.vars={k:tk.StringVar() for k in ("jurisdiccion","coeficiente","alicuota","observaciones")};body=ttk.Frame(self,padding=18);body.pack(fill="both",expand=True)
        for row,(key,label) in enumerate((("jurisdiccion","Jurisdicción"),("coeficiente","Coeficiente"),("alicuota","Alícuota"),("observaciones","Observaciones"))):ttk.Label(body,text=label).grid(row=row,column=0,sticky="w",pady=5);ttk.Entry(body,textvariable=self.vars[key]).grid(row=row,column=1,sticky="ew",padx=8,pady=5)
        body.columnconfigure(1,weight=1);ttk.Button(body,text="Guardar jurisdicción",style="Primary.TButton",command=self.save).grid(row=5,column=1,sticky="e",pady=12)
    def save(self):
        try:self.app.iibb_service.add_convenio_jurisdiction(self.client_id,self.period,self.vars["jurisdiccion"].get(),float(self.vars["coeficiente"].get().replace(",",".")),float(self.vars["alicuota"].get().replace(",",".")),self.vars["observaciones"].get());messagebox.showinfo("Convenio Multilateral","Jurisdicción guardada.",parent=self);self.destroy()
        except Exception as error:messagebox.showerror("No se pudo guardar",str(error),parent=self)
