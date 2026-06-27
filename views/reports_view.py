from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class ReportsView(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=22); self.app=app
        ttk.Label(self,text="Reportes",style="Title.TLabel").pack(anchor="w")
        ttk.Label(self,text="Exportaciones Excel operativas de todas las áreas.",style="Subtitle.TLabel").pack(anchor="w",pady=(2,18))
        box=ttk.LabelFrame(self,text="Generar reporte",padding=18); box.pack(fill="x")
        self.report_map={label:key for key,label in app.report_service.REPORTS.items()}; self.report=tk.StringVar(value=next(iter(self.report_map)))
        clients=app.client_service.list_clients(include_inactive=True); self.client_map={"Todos":None,**{f"{c['nombre_razon_social']} · {c['cuit_cuil']}":c['id'] for c in clients}}; self.client=tk.StringVar(value="Todos")
        ttk.Label(box,text="Reporte").grid(row=0,column=0,sticky="w",pady=6); ttk.Combobox(box,textvariable=self.report,values=tuple(self.report_map),state="readonly",width=48).grid(row=0,column=1,sticky="ew",padx=10)
        ttk.Label(box,text="Cliente").grid(row=1,column=0,sticky="w",pady=6); ttk.Combobox(box,textvariable=self.client,values=tuple(self.client_map),state="readonly",width=48).grid(row=1,column=1,sticky="ew",padx=10)
        ttk.Button(box,text="Exportar a Excel",style="Primary.TButton",command=self.export).grid(row=2,column=1,sticky="e",pady=12); box.columnconfigure(1,weight=1)

    def export(self) -> None:
        filename=filedialog.asksaveasfilename(parent=self,defaultextension=".xlsx",filetypes=(("Excel","*.xlsx"),),initialfile=self.report.get()+".xlsx")
        if not filename:return
        try:
            self.app.report_service.export_named(self.report_map[self.report.get()],Path(filename),self.client_map[self.client.get()]); messagebox.showinfo("Reporte creado",f"Se creó:\n{filename}")
        except Exception as error: messagebox.showerror("No se pudo exportar",str(error))
