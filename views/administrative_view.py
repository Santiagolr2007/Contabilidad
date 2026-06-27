from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from utils.formatters import normalize_date

from .common import ScrollableFrame, fit_window, selected_tree_id
from .date_widgets import DateEntry


DEFINITIONS = {
    "documentacion": (
        "Documentación y tareas",
        (
            ("periodo", "Período", "text"),
            ("tipo_documento", "Documento", "text"),
            ("estado", "Estado", ("Solicitada", "Recibida", "Incompleta", "Observada", "Aprobada")),
            ("fecha_solicitud", "Fecha solicitud", "date"),
            ("fecha_recepcion", "Fecha recepción", "date"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "tareas": (
        "Tareas y trabajos",
        (
            ("modulo", "Módulo", "text"),
            ("periodo", "Período", "text"),
            ("titulo", "Título", "text"),
            ("descripcion", "Descripción", "text"),
            ("responsable", "Responsable", "text"),
            ("fecha_inicio", "Fecha inicio", "date"),
            ("fecha_vencimiento", "Vencimiento", "date"),
            ("fecha_finalizacion", "Finalización", "date"),
            ("estado", "Estado", ("pendiente", "esperando documentación", "en proceso", "para revisar", "finalizado", "facturado", "cobrado", "archivado")),
            ("prioridad", "Prioridad", ("baja", "media", "alta")),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "vencimientos": (
        "Vencimientos",
        (
            ("impuesto", "Impuesto", "text"),
            ("periodo", "Período", "text"),
            ("fecha_vencimiento", "Fecha vencimiento", "date"),
            ("estado", "Estado", ("pendiente", "presentado", "pagado", "vencido")),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
    "honorarios": (
        "Honorarios",
        (
            ("servicio", "Servicio", "text"),
            ("periodo", "Período", "text"),
            ("importe", "Importe", "text"),
            ("estado", "Estado", ("pendiente de facturar", "facturado", "pendiente de cobro", "cobrado parcial", "cobrado total", "vencido")),
            ("fecha_emision", "Fecha emisión", "date"),
            ("fecha_cobro", "Fecha cobro", "date"),
            ("medio_pago", "Medio de pago", "text"),
            ("saldo_pendiente", "Saldo pendiente", "text"),
            ("observaciones", "Observaciones", "text"),
        ),
    ),
}


class AdministrativeView(ttk.Frame):
    def __init__(self, parent, app, module: str) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        self.module = module
        title, _ = DEFINITIONS[module]
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=12)
        ttk.Button(
            toolbar, text="+ Agregar", style="Primary.TButton", command=self.add
        ).pack(side="left")
        if module == "documentacion":
            ttk.Button(
                toolbar,
                text="Ver tareas",
                command=lambda: app.show_view("tareas"),
            ).pack(side="left", padx=8)
        if module in ("tareas", "honorarios"):
            ttk.Button(toolbar, text="Modificar", command=self.edit).pack(
                side="left", padx=(8, 0)
            )
            ttk.Button(toolbar, text="Eliminar", command=self.delete).pack(
                side="left", padx=(8, 0)
            )
        ttk.Button(toolbar, text="Actualizar", command=self.refresh).pack(side="right")

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, show="headings")
        yscroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        if module in ("tareas", "honorarios"):
            self.tree.bind("<Double-1>", lambda _event: self.edit())
        self.refresh()

    def refresh(self) -> None:
        rows = self.app.administrative_service.list(self.module)
        keys = list(rows[0].keys()) if rows else ["id", "cliente_nombre", "estado"]
        visible = [
            key for key in keys if key not in ("cliente_id", "descripcion", "observaciones")
        ][:9]
        self.tree.configure(columns=visible)
        for key in visible:
            self.tree.heading(key, text=key.replace("_", " ").title())
            self.tree.column(key, width=125)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert(
                "", "end", iid=str(row["id"]), values=[row.get(key, "") for key in visible]
            )

    def add(self) -> None:
        RecordDialog(self, self.app, self.module, self.refresh)

    def edit(self) -> None:
        record_id = selected_tree_id(self.tree)
        if record_id is None:
            messagebox.showinfo("Seleccionar registro", "Seleccioná un registro de la tabla.")
            return
        RecordDialog(self, self.app, self.module, self.refresh, record_id)

    def delete(self) -> None:
        record_id = selected_tree_id(self.tree)
        if record_id is None:
            messagebox.showinfo("Seleccionar registro", "Seleccioná un registro de la tabla.")
            return
        noun = "la tarea" if self.module == "tareas" else "el honorario"
        if not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Está seguro que desea eliminar {noun}? Esta acción no se puede deshacer.",
            parent=self,
        ):
            return
        try:
            deleted = self.app.administrative_service.delete(self.module, record_id)
            self.refresh()
            if not deleted:
                messagebox.showwarning(
                    "Registro inexistente", "El registro ya había sido eliminado.", parent=self
                )
        except Exception as error:
            messagebox.showerror("No se pudo eliminar", str(error), parent=self)


class RecordDialog(tk.Toplevel):
    def __init__(
        self, parent, app, module: str, callback, record_id: int | None = None
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.module = module
        self.callback = callback
        self.record_id = record_id
        self.title(("Modificar " if record_id else "Agregar ") + DEFINITIONS[module][0])
        fit_window(self, 700, 740)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        footer = ttk.Frame(self, padding=(14, 10))
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            footer, text="Guardar cambios" if record_id else "Guardar",
            style="Primary.TButton", command=self.save,
        ).pack(side="right", padx=8)
        scroll = ScrollableFrame(self, padding=18)
        scroll.pack(side="top", fill="both", expand=True)
        body = scroll.content
        clients = app.client_service.list_clients(include_inactive=True)
        self.clients = {
            f"{client['nombre_razon_social']} · {client['cuit_cuil']}": client["id"]
            for client in clients
        }
        if module in ("tareas", "vencimientos"):
            self.clients = {"General": None, **self.clients}
        self.vars = {"cliente": tk.StringVar()}
        ttk.Label(body, text="Cliente").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(
            body,
            textvariable=self.vars["cliente"],
            values=tuple(self.clients),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=8)
        if self.clients:
            self.vars["cliente"].set(next(iter(self.clients)))
        for row, (key, label, kind) in enumerate(DEFINITIONS[module][1], 1):
            self.vars[key] = tk.StringVar()
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if kind == "date":
                DateEntry(body, self.vars[key]).grid(
                    row=row, column=1, sticky="ew", padx=8
                )
            elif isinstance(kind, tuple):
                ttk.Combobox(
                    body, textvariable=self.vars[key], values=kind, state="readonly"
                ).grid(row=row, column=1, sticky="ew", padx=8)
                self.vars[key].set(kind[0])
            else:
                ttk.Entry(body, textvariable=self.vars[key]).grid(
                    row=row, column=1, sticky="ew", padx=8
                )
        body.columnconfigure(1, weight=1)
        if record_id:
            self._load()

    def _load(self) -> None:
        record = self.app.administrative_service.get(self.module, self.record_id)
        if not record:
            messagebox.showerror("Registro inexistente", "El registro ya no existe.", parent=self)
            self.destroy()
            return
        client_label = next(
            (label for label, value in self.clients.items() if value == record.get("cliente_id")),
            next(iter(self.clients), ""),
        )
        self.vars["cliente"].set(client_label)
        for key, _label, _kind in DEFINITIONS[self.module][1]:
            self.vars[key].set(str(record.get(key) or ""))

    def save(self) -> None:
        try:
            data = {key: variable.get().strip() for key, variable in self.vars.items()}
            data["cliente_id"] = self.clients.get(data.pop("cliente"))
            for key in [key for key in data if key.startswith("fecha_") and data[key]]:
                data[key] = normalize_date(data[key])
            if self.record_id:
                self.app.administrative_service.update(
                    self.module, self.record_id, data
                )
            else:
                self.app.administrative_service.create(self.module, data)
            self.callback()
            self.destroy()
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error), parent=self)
