from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from utils.formatters import display_date, money

from .ledger_view import ClientLedgerDialog


class RegimeView(ttk.Frame):
    def __init__(self, parent, app, title: str, regime: str) -> None:
        super().__init__(parent, padding=22)
        self.app=app;self.title_text=title;self.regime=regime;self.rows=[]
        ttk.Label(self,text=title,style="Title.TLabel").pack(anchor="w")
        ttk.Label(self,text="Clientes, movimientos, obligaciones y riesgos del régimen fiscal.",style="Subtitle.TLabel").pack(anchor="w",pady=(2,10))
        toolbar=ttk.Frame(self);toolbar.pack(fill="x",pady=(0,8))
        ttk.Button(toolbar,text="+ Registrar cliente",style="Primary.TButton",command=lambda:app.show_view("clientes",action="new")).pack(side="left")
        ttk.Button(toolbar,text="Abrir legajo integral",command=self.open_ledger).pack(side="left",padx=6)
        ttk.Button(toolbar,text="Exportar Excel",command=lambda:self.export("xlsx")).pack(side="left",padx=(12,4))
        ttk.Button(toolbar,text="Exportar PDF",command=lambda:self.export("pdf")).pack(side="left",padx=4)
        ttk.Button(toolbar,text="Imprimir",command=lambda:self.export("pdf",True)).pack(side="left",padx=4)
        ttk.Button(toolbar,text="Actualizar",command=self.refresh).pack(side="right")
        tk=__import__('tkinter');filters=ttk.Frame(self);filters.pack(fill="x",pady=(0,4));self.search=tk.StringVar();self.year=tk.StringVar(value=str(date.today().year));self.month=tk.StringVar();self.state_filter=tk.StringVar(value="Todos");self.risk_filter=tk.StringVar(value="Todos");self.responsible_filter=tk.StringVar()
        ttk.Label(filters,text="Buscar cliente").pack(side="left");ttk.Entry(filters,textvariable=self.search,width=30).pack(side="left",padx=6);ttk.Label(filters,text="Año calendario").pack(side="left",padx=(12,0));ttk.Entry(filters,textvariable=self.year,width=8).pack(side="left",padx=6);ttk.Button(filters,text="Aplicar",command=self.refresh).pack(side="left")
        self.count=__import__('tkinter').StringVar(value="0 clientes");ttk.Label(filters,textvariable=self.count,style="Subtitle.TLabel").pack(side="right")
        advanced=ttk.Frame(self);advanced.pack(fill="x",pady=(0,8));ttk.Label(advanced,text="Mes").pack(side="left");ttk.Entry(advanced,textvariable=self.month,width=6).pack(side="left",padx=5);ttk.Label(advanced,text="Estado").pack(side="left");ttk.Combobox(advanced,textvariable=self.state_filter,values=("Todos","activo","inactivo"),state="readonly",width=10).pack(side="left",padx=5);ttk.Label(advanced,text="Riesgo").pack(side="left");ttk.Combobox(advanced,textvariable=self.risk_filter,values=("Todos","Bajo","Medio","Alto","Urgente"),state="readonly",width=10).pack(side="left",padx=5);ttk.Label(advanced,text="Responsable").pack(side="left");ttk.Entry(advanced,textvariable=self.responsible_filter,width=16).pack(side="left",padx=5)
        holder=ttk.Frame(self);holder.pack(fill="both",expand=True)
        columns=("cuit","actividad","estado","alta","responsable","ultimo_control","vencimiento","riesgo","ventas_periodo","compras_periodo","ventas_anio","compras_anio","ventas_12","compras_12","iva_debito","iva_credito","pendientes")
        self.tree=ttk.Treeview(holder,columns=columns,show="tree headings",selectmode="browse");self.tree.heading("#0",text="Nombre / razón social");self.tree.column("#0",width=230)
        labels=("CUIT/CUIL","Actividad","Estado","Fecha alta","Responsable","Último control","Próximo vencimiento","Riesgo","Ventas período","Compras período","Ventas año","Compras año","Ventas 12 meses","Compras 12 meses","IVA débito est.","IVA crédito est.","Pendientes")
        widths=(105,170,80,90,100,100,115,80,115,115,115,115,120,120,115,115,90)
        for col,label,width in zip(columns,labels,widths):self.tree.heading(col,text=label);self.tree.column(col,width=width,minwidth=65)
        sy=ttk.Scrollbar(holder,orient="vertical",command=self.tree.yview);sx=ttk.Scrollbar(holder,orient="horizontal",command=self.tree.xview);self.tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);self.tree.grid(row=0,column=0,sticky="nsew");sy.grid(row=0,column=1,sticky="ns");sx.grid(row=1,column=0,sticky="ew");holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1);self.tree.bind("<Double-1>",lambda _event:self.open_ledger());self.refresh()

    def _clients(self) -> list[dict]:
        if self.regime == "responsable_inscripto": return self.app.dashboard_service.clients_by_category("responsables")
        term=self.regime.replace("_"," ").casefold()
        return [row for row in self.app.dashboard_service.clients_by_category("activos") if term in str(row.get("condicion_fiscal","")).replace("_"," ").casefold()]

    def refresh(self) -> None:
        try:year=int(self.year.get())
        except ValueError:messagebox.showerror("Año inválido","Ingresá un año con cuatro dígitos.",parent=self);return
        month=self.month.get().strip().zfill(2) if self.month.get().strip() else f"{date.today().month:02d}"
        if not month.isdigit() or not 1 <= int(month) <= 12:messagebox.showerror("Mes inválido","Ingresá un mes entre 1 y 12.",parent=self);return
        term=self.search.get().casefold().strip();clients=[row for row in self._clients() if (not term or term in f"{row['nombre_razon_social']} {row['cuit_cuil']}".casefold()) and (self.state_filter.get()=="Todos" or row.get("estado")==self.state_filter.get())]
        self.rows=[]
        for client in clients:
            client_id=int(client["cliente_id"])
            metrics=self.app.database.query_one(
                """SELECT
                   COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal=?),0) ventas_periodo,
                   COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal=?),0) compras_periodo,
                   COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_ventas WHERE cliente_id=? AND periodo_fiscal LIKE ?),0) ventas_anio,
                   COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_compras WHERE cliente_id=? AND periodo_fiscal LIKE ?),0) compras_anio,
                   COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_ventas WHERE cliente_id=? AND fecha>=date('now','start of month','-11 months')),0) ventas_12,
                   COALESCE((SELECT SUM(importe_neto_fiscal) FROM comprobantes_compras WHERE cliente_id=? AND fecha>=date('now','start of month','-11 months')),0) compras_12,
                   (SELECT COUNT(*) FROM vencimientos WHERE cliente_id=? AND estado NOT IN ('pagado','presentado')) pendientes""",
                (client_id,f"{year:04d}-{month}",client_id,f"{year:04d}-{month}",client_id,f"{year:04d}-%",client_id,f"{year:04d}-%",client_id,client_id,client_id),
            )
            ledger=self.app.ledger_service.summary(client_id);sales=float(metrics["ventas_anio"] or 0);purchases=float(metrics["compras_anio"] or 0)
            row={**client,"ventas_periodo":float(metrics["ventas_periodo"] or 0),"compras_periodo":float(metrics["compras_periodo"] or 0),"ventas_anio":sales,"compras_anio":purchases,"ventas_12":float(metrics["ventas_12"] or 0),"compras_12":float(metrics["compras_12"] or 0),"iva_debito":sales*.21,"iva_credito":purchases*.21,"pendientes":int(metrics["pendientes"] or 0),"ultimo_control":ledger.get("ultimo_control",""),"fecha_alta":ledger.get("fecha_alta_estudio","")}
            if self.risk_filter.get()!="Todos" and row.get("riesgo_general")!=self.risk_filter.get():continue
            if self.responsible_filter.get().strip().casefold() not in str(row.get("responsable_interno","")).casefold():continue
            self.rows.append(row)
        for item in self.tree.get_children():self.tree.delete(item)
        for row in self.rows:
            self.tree.insert("","end",iid=str(row["cliente_id"]),text=row["nombre_razon_social"],values=(row["cuit_cuil"],row.get("actividad",""),row.get("estado",""),display_date(row.get("fecha_alta")),row.get("responsable_interno",""),display_date(row.get("ultimo_control")),display_date(row.get("proximo_vencimiento")),row.get("riesgo_general",""),money(row["ventas_periodo"]),money(row["compras_periodo"]),money(row["ventas_anio"]),money(row["compras_anio"]),money(row["ventas_12"]),money(row["compras_12"]),money(row["iva_debito"]),money(row["iva_credito"]),row["pendientes"]))
        self.count.set(f"{len(self.rows)} clientes")

    def open_ledger(self) -> None:
        selected=self.tree.selection()
        if not selected:messagebox.showinfo("Seleccionar cliente","Seleccioná un cliente.",parent=self);return
        ClientLedgerDialog(self,self.app,int(selected[0]))

    def export(self,format_name:str,print_after:bool=False) -> None:
        extension=".xlsx" if format_name=="xlsx" else ".pdf";filename=filedialog.asksaveasfilename(parent=self,defaultextension=extension,filetypes=(("Excel","*.xlsx"),) if format_name=="xlsx" else (("PDF","*.pdf"),),initialfile=f"{self.title_text} {self.year.get()}{extension}")
        if not filename:return
        try:
            rows=[{key:value for key,value in row.items() if key not in ("cliente_id",)} for row in self.rows];method=self.app.report_service.export_table_excel if format_name=="xlsx" else self.app.report_service.export_table_pdf;method(Path(filename),self.title_text,rows,f"Año {self.year.get()}")
            if print_after:
                try:os.startfile(filename,"print")
                except OSError:messagebox.showinfo("PDF listo",f"Abrí e imprimí:\n{filename}",parent=self)
            else:messagebox.showinfo("Exportación terminada",f"Se creó:\n{filename}",parent=self)
        except Exception as error:messagebox.showerror("No se pudo exportar",str(error),parent=self)
