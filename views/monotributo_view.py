from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from utils.formatters import money, percentage

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
        items=(("Actividad fiscal",client.get("actividad_fiscal") or "—"),("Denominación",client.get("denominacion") or "—"),("Categoría actual",client.get("categoria_actual") or "—"),("Categoría sugerida",data["suggested_category"]),("Alta monotributo",client.get("fecha_alta") or "—"),("Ingresos últimos 12 meses",money(data["sales"].get("ultimos_12",0))),("Ventas año",money(data["sales"].get("anio",0))),("Compras año",money(data["purchases"].get("anio",0))),("Estado pago mensual",client.get("estado_pago_mensual") or "pendiente"),("Estado recategorización",client.get("estado_recategorizacion") or "pendiente"),("Riesgo exclusión",client.get("riesgo_exclusion") or "normal"),("Observaciones",client.get("observaciones_fiscales") or "—"))
        for row,(label,value) in enumerate(items):
            ttk.Label(frame,text=label,font=("Segoe UI",9,"bold")).grid(row=row,column=0,sticky="w",pady=5); ttk.Label(frame,text=value).grid(row=row,column=1,sticky="w",padx=15)

    def _add_iibb_tab(self, client_id: int) -> None:
        scroll=ScrollableFrame(self.details,padding=12);self.details.add(scroll,text="IIBB");frame=scroll.content
        profile=self.app.iibb_service.get_profile(client_id); vars={k:tk.StringVar(value=str(v or "")) for k,v in profile.items()}
        period=tk.StringVar(value=__import__('datetime').date.today().strftime("%Y-%m")); extras={k:tk.StringVar(value="0") for k in ("retenciones","percepciones","saldo","fijo")};extras.update({"presentacion":tk.StringVar(value="pendiente"),"pago":tk.StringVar(value="pendiente"),"vencimiento":tk.StringVar(value="")})
        fields=(("Jurisdicción","jurisdiccion"),("Régimen", "regimen_principal"),("Actividad","actividad"),("Alícuota decimal","alicuota"),("Fecha alta","fecha_alta"),("Fecha baja","fecha_baja"),("Estado","estado"),("Observaciones","observaciones"))
        for row,(label,key) in enumerate(fields):
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky="w",pady=3)
            if key=="regimen_principal": widget=ttk.Combobox(frame,textvariable=vars[key],values=("Régimen simplificado","Régimen general/local","Convenio Multilateral","ARBA - REG SIMP","ARBA REG GENERAL","AGIP REG SIMP","AGIP REG GENERAL","CONVENIO MULTILATERAL"),state="readonly")
            else: widget=ttk.Entry(frame,textvariable=vars[key])
            widget.grid(row=row,column=1,sticky="ew",padx=8,pady=3)
        offset=len(fields)
        for index,(label,var) in enumerate((("Período",period),("Retenciones",extras["retenciones"]),("Percepciones",extras["percepciones"]),("Saldo a favor",extras["saldo"]),("Importe fijo simplificado",extras["fijo"]),("Estado presentación",extras["presentacion"]),("Estado pago",extras["pago"]),("Fecha vencimiento",extras["vencimiento"]))):
            ttk.Label(frame,text=label).grid(row=index,column=2,sticky="w",padx=(20,0),pady=3); ttk.Entry(frame,textvariable=var).grid(row=index,column=3,sticky="ew",padx=8,pady=3)
        def calculate():
            try:
                self.app.iibb_service.save_profile(client_id,{k:v.get() for k,v in vars.items()}); result=self.app.iibb_service.calculate_and_save(client_id,period.get(),float(extras["retenciones"].get()),float(extras["percepciones"].get()),float(extras["saldo"].get()),float(extras["fijo"].get()),presentation_status=extras["presentacion"].get(),payment_status=extras["pago"].get(),due_date=extras["vencimiento"].get()); messagebox.showinfo("Ingresos Brutos",f"Base: {money(result['base'])}\nImpuesto: {money(result['determined'])}\nSaldo a pagar: {money(result['payable'])}")
            except Exception as error: messagebox.showerror("No se pudo calcular",str(error))
        ttk.Button(frame,text="Guardar y calcular",style="Primary.TButton",command=calculate).grid(row=offset,column=3,sticky="e",pady=10)
        ttk.Button(frame,text="Agregar jurisdicción Convenio Multilateral",command=lambda:ConvenioDialog(frame,self.app,client_id,period.get())).grid(row=offset+1,column=3,sticky="e",pady=4); frame.columnconfigure(1,weight=1); frame.columnconfigure(3,weight=1)

    def _add_recat_tab(self, client_id: int) -> None:
        scroll=ScrollableFrame(self.details,padding=14);self.details.add(scroll,text="Recateg.");frame=scroll.content
        calc=self.app.recategorization_service.calculate(client_id)
        for row,(label,key) in enumerate((("Cliente","cliente"),("Actividad fiscal","actividad_fiscal"),("Denominación","denominacion"),("Período desde","periodo_desde"),("Período hasta","periodo_hasta"),("Ventas 12 meses","ventas"),("Categoría actual","categoria_actual"),("Categoría sugerida","categoria_sugerida"),("Diferencia al tope","diferencia_tope"),("Estado","estado"))):
            value=money(calc[key]) if key in ("ventas","diferencia_tope") else calc[key]; ttk.Label(frame,text=label,font=("Segoe UI",9,"bold")).grid(row=row,column=0,sticky="w",pady=3); ttk.Label(frame,text=value).grid(row=row,column=1,sticky="w",padx=10)
        extras={k:tk.StringVar(value="0") for k in ("alquileres","energia","superficie","precio_unitario_maximo")}
        for index,(key,var) in enumerate(extras.items()): ttk.Label(frame,text=key.replace("_"," ").title()).grid(row=index,column=2,sticky="w",padx=(25,0)); ttk.Entry(frame,textvariable=var).grid(row=index,column=3,padx=8,pady=3)
        def save():
            try:self.app.recategorization_service.save(client_id,{k:float(v.get()) for k,v in extras.items()});messagebox.showinfo("Recategorización","Análisis guardado.")
            except Exception as error:messagebox.showerror("No se pudo guardar",str(error))
        ttk.Button(frame,text="Guardar análisis",style="Primary.TButton",command=save).grid(row=5,column=3,sticky="e",pady=8)

    def _add_alerts_tab(self, client_id: int) -> None:
        frame=ttk.Frame(self.details,padding=10); self.details.add(frame,text="Alertas")
        ttk.Button(frame,text="Recalcular alertas",command=lambda:self._refresh_alerts(client_id)).pack(anchor="e",pady=(0,6))
        tree=ttk.Treeview(frame,columns=("periodo","tipo","descripcion","gravedad","estado"),show="headings")
        for col in ("periodo","tipo","descripcion","gravedad","estado"):tree.heading(col,text=col.title());tree.column(col,width=150)
        tree.pack(fill="both",expand=True)
        for row in self.app.database.query("SELECT * FROM alertas_fiscales WHERE cliente_id=? ORDER BY fecha_creacion DESC",(client_id,)):tree.insert("","end",values=(row["periodo"],row["tipo_alerta"],row["descripcion"],row["gravedad"],row["estado"]))

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
        columns = ("periodo", "facturas", "nc", "nd", "neto", "cantidad")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
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
        tree.pack(fill="both", expand=True)
        make_tree_sortable(tree, {"cantidad", "total", "participacion"})
        for row in rows:
            tree.insert(
                "",
                "end",
                values=(
                    row["periodo"],
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
        columns = ("puesto", "nombre", "documento", "cantidad", "total", "participacion")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        settings = (
            ("puesto", "Puesto", 60),
            ("nombre", "Nombre", 240),
            ("documento", "CUIT/DNI", 110),
            ("cantidad", "Comprobantes", 90),
            ("total", "Total", 130),
            ("participacion", "% total", 80),
        )
        for column, label, width in settings:
            tree.heading(column, text=label)
            tree.column(column, width=width)
        tree.pack(fill="both", expand=True)
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


class ConvenioDialog(tk.Toplevel):
    def __init__(self,parent,app,client_id:int,period:str):
        super().__init__(parent);self.app=app;self.client_id=client_id;self.period=period;self.title("Jurisdicción de Convenio Multilateral");fit_window(self,560,400);self.transient(parent.winfo_toplevel());self.grab_set()
        self.vars={k:tk.StringVar() for k in ("jurisdiccion","coeficiente","alicuota","observaciones")};body=ttk.Frame(self,padding=18);body.pack(fill="both",expand=True)
        for row,(key,label) in enumerate((("jurisdiccion","Jurisdicción"),("coeficiente","Coeficiente"),("alicuota","Alícuota"),("observaciones","Observaciones"))):ttk.Label(body,text=label).grid(row=row,column=0,sticky="w",pady=5);ttk.Entry(body,textvariable=self.vars[key]).grid(row=row,column=1,sticky="ew",padx=8,pady=5)
        body.columnconfigure(1,weight=1);ttk.Button(body,text="Guardar jurisdicción",style="Primary.TButton",command=self.save).grid(row=5,column=1,sticky="e",pady=12)
    def save(self):
        try:self.app.iibb_service.add_convenio_jurisdiction(self.client_id,self.period,self.vars["jurisdiccion"].get(),float(self.vars["coeficiente"].get().replace(",",".")),float(self.vars["alicuota"].get().replace(",",".")),self.vars["observaciones"].get());messagebox.showinfo("Convenio Multilateral","Jurisdicción guardada.",parent=self);self.destroy()
        except Exception as error:messagebox.showerror("No se pudo guardar",str(error),parent=self)
