from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from utils.formatters import normalize_date
from .date_widgets import DateEntry
from .common import ScrollableFrame, fit_window


DEFINITIONS = {
    "documentacion": (
        "Documentación y tareas",
        (("periodo", "Período", "text"), ("tipo_documento", "Documento", "text"),
         ("estado", "Estado", ("Solicitada", "Recibida", "Incompleta", "Observada", "Aprobada")),
         ("fecha_solicitud", "Fecha solicitud", "date"), ("fecha_recepcion", "Fecha recepción", "date"),
         ("observaciones", "Observaciones", "text")),
    ),
    "tareas": (
        "Tareas y trabajos",
        (("modulo", "Módulo", "text"), ("periodo", "Período", "text"), ("titulo", "Título", "text"),
         ("descripcion", "Descripción", "text"), ("responsable", "Responsable", "text"),
         ("fecha_inicio", "Fecha inicio", "date"), ("fecha_vencimiento", "Vencimiento", "date"),
         ("fecha_finalizacion", "Finalización", "date"),
         ("estado", "Estado", ("pendiente", "esperando documentación", "en proceso", "para revisar", "finalizado", "facturado", "cobrado", "archivado")),
         ("prioridad", "Prioridad", ("baja", "media", "alta")), ("observaciones", "Observaciones", "text")),
    ),
    "vencimientos": (
        "Vencimientos",
        (("impuesto", "Impuesto", "text"), ("periodo", "Período", "text"),
         ("fecha_vencimiento", "Fecha vencimiento", "date"),
         ("estado", "Estado", ("pendiente", "presentado", "pagado", "vencido")),
         ("observaciones", "Observaciones", "text")),
    ),
    "honorarios": (
        "Honorarios",
        (("servicio", "Servicio", "text"), ("periodo", "Período", "text"),
         ("importe", "Importe", "text"),
         ("estado", "Estado", ("pendiente de facturar", "facturado", "pendiente de cobro", "cobrado parcial", "cobrado total", "vencido")),
         ("fecha_emision", "Fecha emisión", "date"), ("fecha_cobro", "Fecha cobro", "date"),
         ("medio_pago", "Medio de pago", "text"), ("saldo_pendiente", "Saldo pendiente", "text"),
         ("observaciones", "Observaciones", "text")),
    ),
}


class AdministrativeView(ttk.Frame):
    def __init__(self, parent, app, module: str) -> None:
        super().__init__(parent, padding=22)
        self.app, self.module = app, module
        title, _ = DEFINITIONS[module]
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=12)
        ttk.Button(toolbar, text="+ Agregar", style="Primary.TButton", command=self.add).pack(side="left")
        if module == "documentacion":
            ttk.Button(toolbar, text="Ver tareas", command=lambda: app.show_view("tareas")).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Actualizar", command=self.refresh).pack(side="right")
        self.tree = ttk.Treeview(self, show="headings")
        self.tree.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        rows = self.app.administrative_service.list(self.module)
        keys = list(rows[0].keys()) if rows else ["id", "cliente_nombre", "estado"]
        visible = [key for key in keys if key not in ("cliente_id", "descripcion", "observaciones")][:9]
        self.tree.configure(columns=visible)
        for key in visible:
            self.tree.heading(key, text=key.replace("_", " ").title())
            self.tree.column(key, width=125)
        for item in self.tree.get_children(): self.tree.delete(item)
        for row in rows:
            self.tree.insert("", "end", iid=str(row["id"]), values=[row.get(k, "") for k in visible])

    def add(self) -> None:
        RecordDialog(self, self.app, self.module, self.refresh)


class RecordDialog(tk.Toplevel):
    def __init__(self, parent, app, module: str, callback) -> None:
        super().__init__(parent); self.app=app; self.module=module; self.callback=callback
        self.title(DEFINITIONS[module][0]); fit_window(self,700,740); self.transient(parent.winfo_toplevel()); self.grab_set()
        footer=ttk.Frame(self,padding=(14,10));footer.pack(side="bottom",fill="x")
        ttk.Button(footer,text="Cancelar",command=self.destroy).pack(side="right")
        ttk.Button(footer,text="Guardar",style="Primary.TButton",command=self.save).pack(side="right",padx=8)
        scroll=ScrollableFrame(self,padding=18);scroll.pack(side="top",fill="both",expand=True);body=scroll.content
        self.clients={f"{c['nombre_razon_social']} · {c['cuit_cuil']}":c['id'] for c in app.client_service.list_clients()}
        self.vars={"cliente":tk.StringVar()}; ttk.Label(body,text="Cliente").grid(row=0,column=0,sticky="w",pady=4)
        ttk.Combobox(body,textvariable=self.vars["cliente"],values=tuple(self.clients),state="readonly").grid(row=0,column=1,sticky="ew",padx=8)
        if self.clients:self.vars["cliente"].set(next(iter(self.clients)))
        for row,(key,label,kind) in enumerate(DEFINITIONS[module][1],1):
            self.vars[key]=tk.StringVar(); ttk.Label(body,text=label).grid(row=row,column=0,sticky="w",pady=4)
            if kind=="date": DateEntry(body,self.vars[key]).grid(row=row,column=1,sticky="ew",padx=8)
            elif isinstance(kind,tuple): ttk.Combobox(body,textvariable=self.vars[key],values=kind,state="readonly").grid(row=row,column=1,sticky="ew",padx=8); self.vars[key].set(kind[0])
            else: ttk.Entry(body,textvariable=self.vars[key]).grid(row=row,column=1,sticky="ew",padx=8)
        body.columnconfigure(1,weight=1)

    def save(self) -> None:
        try:
            data={k:v.get().strip() for k,v in self.vars.items()}; data["cliente_id"]=self.clients.get(data.pop("cliente"))
            for key in [k for k in data if k.startswith("fecha_") and data[k]]: data[key]=normalize_date(data[key])
            self.app.administrative_service.create(self.module,data); self.callback(); self.destroy()
        except Exception as error: messagebox.showerror("No se pudo guardar",str(error),parent=self)
