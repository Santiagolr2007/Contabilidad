from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


class ConfigView(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        ttk.Label(self, text="Configuración", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Los límites y alícuotas se guardan en SQLite; no están fijados en el código.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        general = ttk.Frame(notebook, padding=10)
        categories = ttk.Frame(notebook, padding=10)
        notebook.add(general, text="Parámetros generales")
        notebook.add(categories, text="Categorías de monotributo")

        columns = ("valor", "tipo", "descripcion")
        self.tree = ttk.Treeview(general, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Clave")
        self.tree.heading("valor", text="Valor")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("descripcion", text="Descripción")
        self.tree.column("#0", width=230)
        self.tree.column("valor", width=110)
        self.tree.column("tipo", width=80)
        self.tree.column("descripcion", width=520)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _event: self.edit())
        ttk.Button(
            general,
            text="Editar valor seleccionado",
            style="Primary.TButton",
            command=self.edit,
        ).pack(anchor="e", pady=(10, 0))

        category_columns = ("tope", "desde", "hasta", "observaciones")
        self.category_tree = ttk.Treeview(
            categories, columns=category_columns, show="tree headings"
        )
        self.category_tree.heading("#0", text="Categoría")
        self.category_tree.heading("tope", text="Tope de ingresos")
        self.category_tree.heading("desde", text="Vigencia desde")
        self.category_tree.heading("hasta", text="Vigencia hasta")
        self.category_tree.heading("observaciones", text="Observaciones")
        self.category_tree.column("#0", width=80)
        self.category_tree.column("tope", width=150)
        self.category_tree.column("desde", width=110)
        self.category_tree.column("hasta", width=110)
        self.category_tree.column("observaciones", width=480)
        self.category_tree.pack(fill="both", expand=True)
        self.category_tree.bind("<Double-1>", lambda _event: self.edit_category())
        ttk.Button(
            categories,
            text="Editar tope seleccionado",
            style="Primary.TButton",
            command=self.edit_category,
        ).pack(anchor="e", pady=(10, 0))
        self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for item in self.app.config_service.list_all():
            self.tree.insert(
                "",
                "end",
                iid=item["clave"],
                text=item["clave"],
                values=(item["valor"], item["tipo"], item["descripcion"]),
            )
        for item in self.category_tree.get_children():
            self.category_tree.delete(item)
        for item in self.app.config_service.list_categories():
            self.category_tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                text=item["categoria"],
                values=(
                    item["tope_ingresos"],
                    item["vigencia_desde"],
                    item["vigencia_hasta"],
                    item["observaciones"],
                ),
            )

    def edit(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Seleccionar opción", "Seleccioná una configuración.")
            return
        key = selection[0]
        current = self.tree.item(key, "values")[0]
        value = simpledialog.askstring(
            "Editar configuración",
            f"Nuevo valor para {key}:",
            initialvalue=current,
            parent=self,
        )
        if value is None:
            return
        try:
            self.app.config_service.update(key, value)
            self.refresh()
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error))

    def edit_category(self) -> None:
        selection = self.category_tree.selection()
        if not selection:
            messagebox.showinfo("Seleccionar categoría", "Seleccioná una categoría.")
            return
        category_id = int(selection[0])
        category = self.category_tree.item(selection[0], "text")
        current = self.category_tree.item(selection[0], "values")[0]
        value = simpledialog.askstring(
            "Editar tope de categoría",
            f"Nuevo tope de ingresos para categoría {category}:",
            initialvalue=current,
            parent=self,
        )
        if value is None:
            return
        try:
            self.app.config_service.update_category_limit(category_id, value)
            self.refresh()
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error))
