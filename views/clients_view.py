from __future__ import annotations

import tkinter as tk
import os
import re
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from models import Client, FiscalProfile, MonotributoProfile
from utils.formatters import display_date, normalize_date, number_ar
from utils.validators import positive_number
from services.iibb_service import ARGENTINA_JURISDICTIONS

from .common import ScrollableFrame, fit_window, selected_tree_id
from .date_widgets import DateEntry
from .ledger_view import BatchLedgerExportDialog, ClientLedgerDialog


class ClientsView(ttk.Frame):
    def __init__(self, parent, app, action: str | None = None) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        self.search = tk.StringVar()
        self.include_inactive = tk.BooleanVar(value=False)
        self.state_filter = tk.StringVar(value="Todos")
        self.regime_filter = tk.StringVar(value="Todos")
        self.risk_filter = tk.StringVar(value="Todos")
        self.payment_filter = tk.StringVar(value="Todos")
        self.documentation_filter = tk.StringVar(value="Todos")
        self.due_filter = tk.StringVar(value="Todos")
        self.checked_client_ids: set[int] = set()

        top = ttk.Frame(self)
        top.pack(fill="x")
        title = ttk.Frame(top)
        title.pack(side="left")
        ttk.Label(title, text="Clientes", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title,
            text="Alta, ficha fiscal, modificación y baja lógica.",
            style="Subtitle.TLabel",
        ).pack(anchor="w")
        ttk.Button(
            top,
            text="Crear cliente",
            style="Primary.TButton",
            command=self.new_client,
        ).pack(side="right", pady=8)
        ttk.Button(
            top, text="Importar Sistema Registral ARCA",
            command=self.import_registry_pdf,
        ).pack(side="right", padx=8, pady=8)

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=15)
        ttk.Label(filters, text="Buscar").pack(side="left")
        search_entry = ttk.Entry(filters, textvariable=self.search, width=35)
        search_entry.pack(side="left", padx=8)
        search_entry.bind("<Return>", lambda _event: self.refresh())
        ttk.Button(filters, text="Aplicar", command=self.refresh).pack(side="left")
        ttk.Checkbutton(
            filters,
            text="Mostrar inactivos",
            variable=self.include_inactive,
            command=self.refresh,
        ).pack(side="left", padx=16)
        advanced_filters = ttk.Frame(self)
        advanced_filters.pack(fill="x", pady=(0, 10))
        for label, variable, values in (
            ("Estado", self.state_filter, ("Todos", "Activo", "En alta", "En regularización", "Pausado", "Baja", "Ex cliente", "Solo consulta", "Pendiente de documentación", "Inactivo")),
            ("Régimen", self.regime_filter, ("Todos", *ClientForm.REGIMES)),
            ("Riesgo", self.risk_filter, ("Todos", "Bajo", "Medio", "Alto")),
            ("Pagos", self.payment_filter, ("Todos", "Al día", "Pendiente", "Vencido")),
            ("Documentación", self.documentation_filter, ("Todos", "Completa", "Pendiente", "Sin cargar")),
            ("Vencimientos", self.due_filter, ("Todos", "Próximos", "Sin próximos")),
        ):
            ttk.Label(advanced_filters, text=label).pack(side="left", padx=(8, 2))
            combo = ttk.Combobox(advanced_filters, textvariable=variable, values=values, state="readonly", width=13)
            combo.pack(side="left")
            combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        columns = (
            "seleccionar", "cuit", "tipo", "actividad", "regimen", "categoria", "estado",
            "servicio", "legajo", "pagos", "documentacion", "riesgo",
            "ultimo_control", "vencimiento", "observaciones",
        )
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="tree headings", selectmode="extended"
        )
        self.tree.heading("#0", text="Nombre / razón social")
        self.tree.column("#0", width=240)
        settings = (
            ("seleccionar", "Sel.", 48),
            ("cuit", "CUIT/CUIL", 110),
            ("tipo", "Persona", 110),
            ("actividad", "Actividad", 190),
            ("regimen", "Régimen", 140),
            ("categoria", "Categoría", 75),
            ("estado", "Estado", 80),
            ("servicio", "Servicio contratado", 155),
            ("legajo", "Estado legajo", 105),
            ("pagos", "Pagos", 95),
            ("documentacion", "Documentación", 110),
            ("riesgo", "Riesgo", 80),
            ("ultimo_control", "Último control", 105),
            ("vencimiento", "Próximo vencimiento", 120),
            ("observaciones", "Observaciones internas", 210),
        )
        for column, label, width in settings:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="center" if column in ("seleccionar", "cuit", "tipo", "categoria", "estado", "legajo", "pagos", "documentacion", "riesgo", "ultimo_control", "vencimiento") else "w")
        tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _event: self.edit_client())
        self.tree.bind("<Button-1>", self._toggle_checkbox, add="+")

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Editar / ficha fiscal", command=self.edit_client).pack(
            side="left"
        )
        ttk.Button(actions, text="Abrir legajo integral", command=self.open_ledger).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="Desactivar cliente", command=self.deactivate).pack(
            side="left", padx=8
        )
        ttk.Button(
            actions,
            text="Eliminar cliente y todos sus datos",
            command=self.delete_client,
        ).pack(side="left")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="right")
        exports = ttk.Frame(self)
        exports.pack(fill="x", pady=(6, 0))
        ttk.Button(
            exports, text="Exportar ficha rápida a Excel", command=self.export_client
        ).pack(side="left")
        ttk.Button(
            exports,
            text="Exportar clientes seleccionados (Excel / PDF)",
            command=self.export_selected_clients,
        ).pack(side="left", padx=8)
        ttk.Button(
            exports, text="Exportar índice visible Excel", command=lambda: self.export_index("xlsx")
        ).pack(side="left")
        ttk.Button(
            exports, text="Exportar índice visible PDF", command=lambda: self.export_index("pdf")
        ).pack(side="left", padx=8)

        self.refresh()
        if action == "new":
            self.after(80, self.new_client)
        elif action == "import_arca":
            self.after(80, self.import_registry_pdf)

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        clients = self.app.client_service.list_clients(
            "", self.include_inactive.get()
        )
        term = self.search.get().strip().casefold()
        for client in clients:
            summary = self.app.ledger_service.summary(int(client["id"]))
            if term and term not in " ".join((
                str(client["nombre_razon_social"]), str(client["cuit_cuil"]),
                str(client.get("rubro_display", "")), summary["tipo_cliente"],
                summary["estado_cliente"],
                summary["servicio_contratado"], summary["actividad_principal"],
            )).casefold():
                continue
            payment_state = "Vencido" if summary["pagos_vencidos"] else (
                "Pendiente" if summary["pagos_pendientes"] else "Al día"
            )
            if self.state_filter.get() != "Todos" and summary["estado_cliente"] != self.state_filter.get():
                continue
            if self.regime_filter.get() != "Todos" and client["regimen_principal"] != self.regime_filter.get():
                continue
            if self.risk_filter.get() != "Todos" and summary["riesgo_general"] != self.risk_filter.get():
                continue
            if self.payment_filter.get() != "Todos" and payment_state != self.payment_filter.get():
                continue
            if self.documentation_filter.get() != "Todos" and summary["estado_documentacion"] != self.documentation_filter.get():
                continue
            has_due = summary["proximo_vencimiento"] not in ("", "—", None)
            if self.due_filter.get() == "Próximos" and not has_due:
                continue
            if self.due_filter.get() == "Sin próximos" and has_due:
                continue
            self.tree.insert(
                "",
                "end",
                iid=str(client["id"]),
                text=client["nombre_razon_social"],
                values=(
                    "☑" if int(client["id"]) in self.checked_client_ids else "☐",
                    client["cuit_cuil"],
                    summary["tipo_cliente"],
                    client.get("rubro_display", ""),
                    client["regimen_principal"].replace("_", " ").title(),
                    client["categoria_actual"],
                    summary["estado_cliente"],
                    summary["servicio_contratado"],
                    summary["estado_legajo"],
                    payment_state,
                    summary["estado_documentacion"],
                    summary["riesgo_general"],
                    display_date(summary["ultimo_control"]),
                    display_date(summary["proximo_vencimiento"]),
                    summary["observacion_ejecutiva"],
                ),
            )

    def _toggle_checkbox(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        client_id = int(item)
        if client_id in self.checked_client_ids:
            self.checked_client_ids.remove(client_id)
            mark = "☐"
        else:
            self.checked_client_ids.add(client_id)
            mark = "☑"
        values = list(self.tree.item(item, "values"))
        values[0] = mark
        self.tree.item(item, values=values)

    def new_client(self) -> None:
        ClientForm(self, self.app, None, self.refresh)

    def import_registry_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self, title="Importar datos desde Sistema Registral ARCA",
            filetypes=(("Documento PDF", "*.pdf"),),
        )
        if not filename:
            return
        try:
            preview = self.app.arca_import_service.preview_registry_pdf(Path(filename))
            RegistryImportPreviewDialog(self, self.app, preview, self.refresh)
        except Exception as error:
            messagebox.showerror("No se pudo leer el PDF", str(error), parent=self)

    def open_arca_history(self) -> None:
        from .administrative_view import AccountingImportHistoryDialog
        AccountingImportHistoryDialog(self, self.app, "Sistema Registral ARCA")

    def open_ledger(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Seleccionar cliente", "Seleccioná un cliente de la lista.")
            return
        ClientLedgerDialog(self, self.app, int(selection[0]))

    def export_selected_clients(self) -> None:
        selection = self.tree.selection()
        visible = {int(item) for item in self.tree.get_children()}
        checked = sorted(self.checked_client_ids & visible)
        client_ids = checked or [int(item) for item in (selection or self.tree.get_children())]
        if not client_ids:
            messagebox.showinfo("Sin clientes", "No hay clientes visibles para exportar.")
            return
        BatchLedgerExportDialog(self, self.app, client_ids)

    def export_index(self, format_name: str) -> None:
        client_ids = [int(item) for item in self.tree.get_children()]
        if not client_ids:
            messagebox.showinfo("Sin clientes", "No hay clientes visibles para exportar.")
            return
        extension = f".{format_name}"
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar índice maestro visible",
            defaultextension=extension,
            initialfile=f"Indice_Maestro_Clientes_{date.today().isoformat()}{extension}",
            filetypes=((format_name.upper(), f"*{extension}"),),
        )
        if not filename:
            return
        try:
            method = (
                self.app.ledger_export_service.export_master_index_excel
                if format_name == "xlsx"
                else self.app.ledger_export_service.export_master_index_pdf
            )
            output = method(Path(filename), client_ids)
            messagebox.showinfo("Índice exportado", f"Se creó:\n{output}")
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error))

    def edit_client(self) -> None:
        client_id = selected_tree_id(self.tree)
        if client_id is None:
            messagebox.showinfo("Seleccionar cliente", "Seleccioná un cliente de la lista.")
            return
        ClientForm(self, self.app, client_id, self.refresh)

    def deactivate(self) -> None:
        client_id = selected_tree_id(self.tree)
        if client_id is None:
            messagebox.showinfo("Seleccionar cliente", "Seleccioná un cliente de la lista.")
            return
        name = self.tree.item(str(client_id), "text")
        if not messagebox.askyesno(
            "Confirmar baja lógica",
            f"¿Dar de baja a '{name}'? Los datos y comprobantes se conservarán.",
        ):
            return
        try:
            self.app.client_service.deactivate(client_id)
            self.refresh()
        except Exception as error:
            messagebox.showerror("No se pudo dar de baja", str(error))

    def delete_client(self) -> None:
        client_id = selected_tree_id(self.tree)
        if client_id is None:
            messagebox.showinfo("Seleccionar cliente", "Seleccioná un cliente de la lista.")
            return
        name = self.tree.item(str(client_id), "text")
        if not messagebox.askyesno(
            "Eliminar cliente permanentemente",
            f"¿Eliminar permanentemente a '{name}'?\n\n"
            "También se borrarán todas sus ventas, compras, importaciones, alertas, "
            "Ingresos Brutos, tareas, vencimientos y honorarios.\n\n"
            "Esta acción no se puede deshacer.",
            icon="warning",
        ):
            return
        try:
            deleted = self.app.client_service.delete_permanently(client_id)
            self.refresh()
            messagebox.showinfo(
                "Cliente eliminado",
                f"Se eliminó el cliente junto con {deleted['ventas']} venta(s) "
                f"y {deleted['compras']} compra(s).",
            )
        except Exception as error:
            messagebox.showerror("No se pudo eliminar", str(error))

    def export_client(self) -> None:
        client_id = selected_tree_id(self.tree)
        if client_id is None:
            messagebox.showinfo(
                "Seleccionar cliente", "Seleccioná el cliente que querés exportar."
            )
            return
        bundle = self.app.client_service.get_bundle(client_id)
        if not bundle:
            messagebox.showerror("Cliente inexistente", "No se encontró el cliente.")
            return
        client = bundle["client"]
        name = re.sub(
            r'[<>:"/\\|?*;]+', "_", client["nombre_razon_social"]
        ).strip(" ._")
        initial = f"Legajo_Cliente_{name}_{client['cuit_cuil']}.xlsx"
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar ficha del cliente",
            defaultextension=".xlsx",
            initialfile=initial,
            filetypes=(("Excel", "*.xlsx"),),
        )
        if not filename:
            return
        try:
            output = self.app.report_service.export_client_file(
                Path(filename), client_id
            )
            messagebox.showinfo("Ficha exportada", f"Se creó:\n{output}")
        except Exception as error:
            messagebox.showerror("No se pudo exportar", str(error))


class RegistryImportPreviewDialog(tk.Toplevel):
    MAIN_FIELDS = (
        ("cuit_cuil", "CUIT / CUIL"), ("nombre_razon_social", "Nombre / razón social"),
        ("dni", "DNI"), ("fecha_nacimiento", "Fecha de nacimiento"),
        ("nacionalidad", "Nacionalidad / país"), ("email", "Email"),
        ("telefono", "Teléfono"), ("fecha_inscripcion", "Fecha de inscripción"),
        ("dependencia", "Dependencia"), ("region", "Región"),
        ("tipo_inscripcion", "Tipo de inscripción"), ("mes_cierre", "Mes de cierre"),
        ("sistema_control", "Sistema de control"), ("segmento", "Segmento"),
        ("impuestos_activos", "Registra impuestos activos"),
        ("tipo_documento", "Tipo de documento"), ("genero", "Género"),
        ("sucesion_indivisa", "Sucesión indivisa"), ("apellido_materno", "Apellido materno"),
        ("apellido_casada", "Apellido de casada"), ("dfe", "Domicilio Fiscal Electrónico"),
    )

    def __init__(self, parent, app, preview: dict, callback) -> None:
        super().__init__(parent);self.app=app;self.preview=preview;self.callback=callback
        self.title("Vista previa de Sistema Registral ARCA");fit_window(self,1050,780);self.transient(parent.winfo_toplevel());self.grab_set()
        footer=ttk.Frame(self,padding=12);footer.pack(side="bottom",fill="x")
        ttk.Button(footer,text="Exportar detectado Excel",command=lambda:self.export_detected("xlsx")).pack(side="left")
        ttk.Button(footer,text="Exportar detectado PDF",command=lambda:self.export_detected("pdf")).pack(side="left",padx=6)
        ttk.Button(footer,text="Imprimir resumen",command=lambda:self.export_detected("pdf",True)).pack(side="left")
        ttk.Button(footer,text="Cancelar",command=self.destroy).pack(side="right")
        ttk.Button(footer,text="Confirmar importación",style="Primary.TButton",command=self.confirm).pack(side="right",padx=8)
        scroll=ScrollableFrame(self,padding=16);scroll.pack(fill="both",expand=True);body=scroll.content
        ttk.Label(body,text="Datos detectados en Sistema Registral",style="Title.TLabel").grid(row=0,column=0,columnspan=3,sticky="w")
        existing = f"Se actualizará: {preview['existing_client_name']}" if preview.get("existing_client_id") else "Se creará un cliente nuevo si confirma."
        ttk.Label(body,text=f"Confianza: {preview['confidence']} · {existing}",style="Subtitle.TLabel").grid(row=1,column=0,columnspan=3,sticky="w",pady=(2,10))
        self.vars={}
        for row,(key,label) in enumerate(self.MAIN_FIELDS,2):
            self.vars[key]=tk.StringVar(value=preview["fields"].get(key,""));ttk.Label(body,text=label).grid(row=row,column=0,sticky="w",pady=3);ttk.Entry(body,textvariable=self.vars[key]).grid(row=row,column=1,sticky="ew",padx=8,pady=3);ttk.Label(body,text="Editable antes de guardar").grid(row=row,column=2,sticky="w")
        offset=2+len(self.MAIN_FIELDS)
        for index,(label,value) in enumerate((("Domicilios detectados",len(preview["domicilios"])),("Emails detectados",len(preview["emails"])),("Impuestos detectados",len(preview["impuestos"])),("Actividades detectadas",len(preview["actividades"]))),offset):
            ttk.Label(body,text=label,font=("Segoe UI",9,"bold")).grid(row=index,column=0,sticky="w",pady=4);ttk.Label(body,text=str(value)).grid(row=index,column=1,sticky="w",padx=8)
        self.structured_actions={}
        sections=(("contactos","Emails y teléfonos"),("domicilios","Domicilios registrados"),("caracterizaciones","Caracterizaciones"),("impuestos","Impuestos inscriptos"),("actividades","Actividades económicas"))
        section_row=offset+4
        for section_key,title in sections:
            rows=preview.get(section_key,[])
            box=ttk.LabelFrame(body,text=title,padding=8);box.grid(row=section_row,column=0,columnspan=3,sticky="ew",pady=5);section_row+=1
            if not rows:ttk.Label(box,text="Sin datos detectados").pack(anchor="w");continue
            for index,item in enumerate(rows):
                line=ttk.Frame(box);line.pack(fill="x",pady=2);enabled=tk.BooleanVar(value=True);self.structured_actions[(section_key,index)]=enabled
                ttk.Checkbutton(line,text="Importar",variable=enabled).pack(side="left")
                summary=" · ".join(str(value) for key,value in item.items() if key not in ("accion","raw") and value)[:180]
                ttk.Label(line,text=summary,wraplength=720).pack(side="left",fill="x",expand=True,padx=8)
                ttk.Button(line,text="Editar",command=lambda sk=section_key,i=index:RegistryStructuredRowDialog(self,preview[sk][i])).pack(side="right")
        extra=ttk.LabelFrame(body,text="Datos digitales y migratorios",padding=8);extra.grid(row=section_row,column=0,columnspan=3,sticky="ew",pady=5)
        for label,key in (("Datos digitales","datos_digitales"),("Datos migratorios / extranjeros","datos_migratorios")):
            line=ttk.Frame(extra);line.pack(fill="x",pady=2);ttk.Label(line,text=label,font=("Segoe UI",9,"bold")).pack(side="left");ttk.Label(line,text=" · ".join(f"{k}: {v}" for k,v in preview.get(key,{}).items() if v),wraplength=650).pack(side="left",fill="x",expand=True,padx=8);ttk.Button(line,text="Editar",command=lambda k=key:RegistryStructuredRowDialog(self,preview[k])).pack(side="right")
        body.columnconfigure(1,weight=1)

    def confirm(self) -> None:
        self.preview["fields"].update({key:value.get().strip() for key,value in self.vars.items()})
        for (section,index),enabled in self.structured_actions.items():
            self.preview[section][index]["accion"]="Importar" if enabled.get() else "No importar"
        replace=False
        if self.preview.get("existing_client_id"):
            answer=messagebox.askyesnocancel("Datos existentes","El CUIT ya existe.\nSí: reemplazar campos con datos detectados.\nNo: completar solamente campos vacíos.\nCancelar: volver.",parent=self)
            if answer is None:return
            replace=bool(answer)
        try:
            result=self.app.arca_import_service.import_registry_pdf(self.preview,replace=replace);self.callback();messagebox.showinfo("Importación terminada",f"Cliente ID: {result['client_id']}\nCampos actualizados: {result['updated']}\nCampos reemplazados: {result['replaced']}",parent=self);self.destroy()
        except Exception as error:messagebox.showerror("No se pudo importar",str(error),parent=self)

    def export_detected(self,format_name:str,print_after:bool=False) -> None:
        extension=f".{format_name}";filename=filedialog.asksaveasfilename(parent=self,defaultextension=extension,filetypes=((format_name.upper(),f"*{extension}"),),initialfile=f"Sistema Registral {self.preview['fields'].get('cuit_cuil','')}{extension}")
        if not filename:return
        rows=[{"seccion":"Datos principales","campo":key.replace("_"," ").title(),"valor":value,"confianza":self.preview["confidence"]} for key,value in self.preview["fields"].items() if value]
        for section in ("contactos","domicilios","caracterizaciones","impuestos","actividades"):
            for index,item in enumerate(self.preview.get(section,[]),1):rows.append({"seccion":section.replace("_"," ").title(),"campo":f"Registro {index}","valor":" · ".join(f"{key}: {value}" for key,value in item.items() if value and key!="accion"),"confianza":self.preview["confidence"]})
        for section in ("datos_digitales","datos_migratorios"):
            for key,value in self.preview.get(section,{}).items():
                if value:rows.append({"seccion":section.replace("_"," ").title(),"campo":key.replace("_"," ").title(),"valor":value,"confianza":self.preview["confidence"]})
        try:
            method=self.app.report_service.export_table_excel if format_name=="xlsx" else self.app.report_service.export_table_pdf;method(Path(filename),"Datos detectados - Sistema Registral ARCA",rows,self.preview["path"])
            if print_after:
                try:os.startfile(filename,"print")
                except (AttributeError,OSError):messagebox.showinfo("PDF listo",f"Abrí e imprimí:\n{filename}",parent=self)
            else:messagebox.showinfo("Exportación terminada",f"Se creó:\n{filename}",parent=self)
        except Exception as error:messagebox.showerror("No se pudo exportar",str(error),parent=self)


class RegistryStructuredRowDialog(tk.Toplevel):
    def __init__(self,parent,row:dict) -> None:
        super().__init__(parent);self.row=row;self.title("Editar dato detectado");fit_window(self,680,580);self.transient(parent);self.grab_set();scroll=ScrollableFrame(self,padding=16);scroll.pack(fill="both",expand=True);frame=scroll.content;self.vars={}
        editable=[key for key in row if key not in ("accion","raw")]
        for index,key in enumerate(editable):self.vars[key]=tk.StringVar(value=str(row.get(key,"")));ttk.Label(frame,text=key.replace("_"," ").title()).grid(row=index,column=0,sticky="w",pady=3);ttk.Entry(frame,textvariable=self.vars[key]).grid(row=index,column=1,sticky="ew",padx=8,pady=3)
        frame.columnconfigure(1,weight=1);ttk.Button(frame,text="Guardar cambios",style="Primary.TButton",command=self.save).grid(row=len(editable),column=1,sticky="e",pady=10)
    def save(self):
        self.row.update({key:value.get().strip() for key,value in self.vars.items()});self.destroy()


class ClientForm(tk.Toplevel):
    REGIMES = (
        "sin_definir",
        "monotributista",
        "responsable_inscripto",
        "ganancias",
        "bienes_personales",
        "casas_particulares",
    )

    def __init__(self, parent, app, client_id: int | None, on_saved) -> None:
        super().__init__(parent)
        self.app = app
        self.client_id = client_id
        self.on_saved = on_saved
        self.title("Ficha del cliente" if client_id else "Nuevo cliente")
        fit_window(self, 1050, 800)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.bind("<Control-s>", lambda _event: self.save())

        # La barra se empaqueta primero y queda siempre visible al pie.
        footer = ttk.Frame(self, padding=(16, 10, 16, 14))
        footer.pack(side="bottom", fill="x")
        ttk.Separator(footer, orient="horizontal").pack(fill="x", pady=(0, 10))
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            footer,
            text="Confirmar cliente y cambios",
            style="Primary.TButton",
            command=self.save,
        ).pack(side="right", padx=8)
        ttk.Label(
            footer,
            text="También podés guardar con Ctrl+S",
            style="Subtitle.TLabel",
        ).pack(side="left")

        self.vars: dict[str, tk.StringVar] = {}
        notebook = ttk.Notebook(self)
        notebook.pack(side="top", fill="both", expand=True, padx=16, pady=(16, 0))
        general_scroll = ScrollableFrame(notebook, padding=18)
        fiscal_scroll = ScrollableFrame(notebook, padding=18)
        mono_scroll = ScrollableFrame(notebook, padding=18)
        iibb_scroll = ScrollableFrame(notebook, padding=18)
        alerts_scroll = ScrollableFrame(notebook, padding=18)
        notebook.add(general_scroll, text="Datos generales")
        notebook.add(fiscal_scroll, text="Regímenes")
        notebook.add(mono_scroll, text="Monotributo")
        notebook.add(iibb_scroll, text="Ingresos Brutos")
        notebook.add(alerts_scroll, text="Alertas")

        self._build_general(general_scroll.content)
        self._build_fiscal(fiscal_scroll.content)
        self._build_monotributo(mono_scroll.content)
        self._build_iibb(iibb_scroll.content)
        self._build_alerts(alerts_scroll.content)

        if client_id:
            self._load()

    def _field(
        self, parent, row: int, label: str, key: str, width: int = 35,
        help_text: str = "",
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        variable = self.vars.setdefault(key, tk.StringVar())
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=5)
        if help_text:
            ttk.Label(
                parent, text=help_text, style="Subtitle.TLabel",
                wraplength=250, justify="left",
            ).grid(row=row, column=2, sticky="w", padx=(12, 0), pady=5)
        parent.columnconfigure(1, weight=1)
        return entry

    def _combo(
        self, parent, row: int, label: str, key: str, values,
        help_text: str = "",
    ) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        variable = self.vars.setdefault(key, tk.StringVar())
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=5)
        if help_text:
            ttk.Label(
                parent, text=help_text, style="Subtitle.TLabel",
                wraplength=250, justify="left",
            ).grid(row=row, column=2, sticky="w", padx=(12, 0), pady=5)
        parent.columnconfigure(1, weight=1)
        return combo

    def _date_field(
        self, parent, row: int, label: str, key: str, help_text: str = ""
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        variable = self.vars.setdefault(key, tk.StringVar())
        DateEntry(parent, variable).grid(
            row=row, column=1, sticky="ew", padx=(12, 0), pady=5
        )
        if help_text:
            ttk.Label(
                parent, text=help_text, style="Subtitle.TLabel",
                wraplength=250, justify="left",
            ).grid(row=row, column=2, sticky="w", padx=(12, 0), pady=5)

    def _build_general(self, frame) -> None:
        self._field(frame, 0, "Nombre o razón social *", "nombre")
        self._field(frame, 1, "CUIT/CUIL *", "cuit")
        self._field(frame, 2, "DNI", "dni")
        self._date_field(frame, 3, "Fecha de nacimiento", "fecha_nacimiento")
        self._field(frame, 4, "Nacionalidad", "nacionalidad")
        self._field(frame, 5, "Estado civil", "estado_civil")
        self._combo(
            frame, 6, "Tipo de persona", "tipo_persona", ("persona_humana", "sociedad")
        )
        self._field(frame, 7, "Teléfono", "telefono")
        self._field(frame, 8, "Email", "email")
        self._field(frame, 9, "Instagram / IG", "instagram")
        self._field(frame, 10, "Domicilio", "domicilio")
        self._field(frame, 11, "Rubro", "rubro")
        self._date_field(frame, 12, "Alta en el estudio", "fecha_alta_estudio")
        self._combo(frame, 13, "Estado", "estado", ("activo", "inactivo"))
        self._field(frame, 14, "Observaciones", "observaciones")
        self.vars["tipo_persona"].set("persona_humana")
        self.vars["estado"].set("activo")

    def _build_fiscal(self, frame) -> None:
        self._combo(frame, 0, "Régimen principal", "regimen", self.REGIMES)
        self._field(frame, 1, "Condición frente al IVA", "condicion_iva")
        self._field(frame, 2, "Observaciones", "observaciones_fiscales")
        self.vars["regimen"].set("sin_definir")

    def _build_monotributo(self, frame) -> None:
        ttk.Label(
            frame,
            text="Estos datos se guardan cuando el régimen principal es monotributista.",
            style="Subtitle.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self._combo(
            frame, 1, "Actividad fiscal", "mono_actividad",
            ("Venta de cosas", "Servicios", "Exportación de servicios"),
            "Actividad declarada en Monotributo. Elegí una de las tres opciones."
        )
        self._field(
            frame, 2, "Denominación", "mono_denominacion",
            help_text="Descripción de la actividad tal como figura en la constancia fiscal."
        )
        self._combo(
            frame, 3, "Categoría actual", "categoria", tuple("ABCDEFGHIJK"),
            "Categoría vigente del cliente, desde A hasta K."
        )
        self._date_field(
            frame, 4, "Fecha de alta", "mono_fecha_alta",
            "Fecha de inicio en Monotributo. Puede quedar vacía si no se conoce."
        )
        self._date_field(
            frame, 5, "Fecha de baja", "mono_fecha_baja",
            "Completar únicamente si el cliente fue dado de baja."
        )
        self._combo(
            frame, 6, "Estado", "mono_estado", ("activo", "inactivo"),
            "Indica si actualmente mantiene activo el Monotributo."
        )
        self._field(
            frame, 7, "Observaciones", "mono_observaciones",
            help_text="Pagos pendientes, recategorizaciones u otra información fiscal relevante."
        )
        self.vars["categoria"].set("A")
        self.vars["mono_actividad"].set("Servicios")
        self.vars["mono_estado"].set("activo")
        activity_code = self._field(
            frame,
            8,
            "Código de actividad",
            "mono_codigo_actividad",
            help_text="Código numérico de la actividad declarada ante ARCA.",
        )
        activity_code.configure(
            validate="key",
            validatecommand=(
                self.register(lambda value: not value or value.isdigit()),
                "%P",
            ),
        )
        self._combo(frame, 9, "Tipo de actividad para el cálculo", "mono_tipo_actividad", ("Servicios", "Venta de cosas muebles"))
        self._combo(frame, 10, "Aporta SIPA", "mono_aporta_sipa", ("Sí", "No", "Exceptuado", "A revisar"))
        self._combo(frame, 11, "Aporta obra social", "mono_aporta_obra_social", ("Sí", "No", "Exceptuado", "A revisar"))
        self._field(frame, 12, "Cantidad de adherentes de obra social", "mono_adherentes")
        self._combo(frame, 13, "Condición especial", "mono_condicion_especial", ("Sin condición especial", "Jubilado", "Relación de dependencia", "Locador de inmuebles", "Menor de 18 años", "Trabajador independiente promovido", "Registro de efectores", "Actividad primaria exceptuada", "Otro", "A revisar"))
        self.vars["mono_tipo_actividad"].set("Servicios");self.vars["mono_aporta_sipa"].set("Sí");self.vars["mono_aporta_obra_social"].set("Sí");self.vars["mono_adherentes"].set("0");self.vars["mono_condicion_especial"].set("Sin condición especial")

    def _build_iibb(self, frame) -> None:
        ttk.Label(
            frame,
            text="Completá esta sección si el cliente está inscripto en Ingresos Brutos.",
            style="Subtitle.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._field(
            frame, 1, "Jurisdicciones seleccionadas", "iibb_jurisdiccion",
            help_text="Podés seleccionar varias provincias y asignar un porcentaje a cada una."
        ).configure(state="readonly")
        ttk.Button(frame, text="Administrar jurisdicciones y porcentajes", command=self.open_iibb_jurisdictions).grid(row=1, column=3, padx=8)
        self._combo(
            frame, 2, "Régimen de Ingresos Brutos", "iibb_regimen",
            ("Régimen simplificado", "Régimen general/local", "Convenio Multilateral",
             "ARBA - REG SIMP", "ARBA REG GENERAL", "AGIP REG SIMP", "AGIP REG GENERAL"),
            "Seleccioná el régimen con el que se liquida el impuesto."
        )
        self._field(
            frame, 3, "Actividad", "iibb_actividad",
            help_text="Actividad declarada específicamente en Ingresos Brutos."
        )
        self._field(
            frame, 4, "Alícuota decimal", "iibb_alicuota",
            help_text="Ejemplo: 0,035 equivale a una alícuota del 3,5 %."
        )
        self._date_field(
            frame, 5, "Fecha de alta", "iibb_fecha_alta",
            "Fecha de inscripción en Ingresos Brutos."
        )
        self._date_field(
            frame, 6, "Fecha de baja", "iibb_fecha_baja",
            "Completar solamente si la inscripción terminó."
        )
        self._combo(
            frame, 7, "Estado", "iibb_estado", ("activo", "inactivo"),
            "Estado actual de la inscripción."
        )
        self._field(
            frame, 8, "Observaciones", "iibb_observaciones",
            help_text="Coeficientes, saldos a favor o aclaraciones de la jurisdicción."
        )
        self.vars["iibb_regimen"].set("Régimen simplificado")
        self.vars["iibb_alicuota"].set("0.035")
        self.vars["iibb_estado"].set("activo")

    def open_iibb_jurisdictions(self) -> None:
        if not self.client_id:
            messagebox.showinfo(
                "Guardar cliente",
                "Primero confirmá el cliente. Luego podrás cargar sus jurisdicciones y porcentajes.",
                parent=self,
            )
            return
        IibbJurisdictionsDialog(self, self.app, self.client_id, self._refresh_iibb_jurisdictions)

    def _refresh_iibb_jurisdictions(self) -> None:
        if not self.client_id: return
        rows = self.app.iibb_service.list_jurisdictions(self.client_id)
        self.vars["iibb_jurisdiccion"].set(", ".join(row["jurisdiccion"] for row in rows))

    def _build_alerts(self, frame) -> None:
        ttk.Label(
            frame,
            text="Estos valores se aplican únicamente a este cliente.",
            style="Subtitle.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        defaults = {
            "alerta_limite": self.app.config_service.get_float(
                "monotributo_alerta_porcentaje", 0.80
            ) * 100,
            "alerta_monto": self.app.config_service.get_float(
                "monto_comprobante_significativo", 500_000
            ),
            "alerta_concentracion": self.app.config_service.get_float(
                "concentracion_porcentaje", 0.30
            ) * 100,
            "alerta_compras_ventas": self.app.config_service.get_float(
                "compras_ventas_alerta", 0.80
            ) * 100,
            "alerta_facturas_dia": self.app.config_service.get_float(
                "muchas_facturas_dia", 10
            ),
            "alerta_facturas_contraparte": self.app.config_service.get_float(
                "muchas_facturas_cliente", 10
            ),
        }
        fields = (
            ("Porcentaje del límite de Monotributo (%)", "alerta_limite", "Ejemplo: 80."),
            ("Importe mínimo de factura elevada", "alerta_monto", "Ejemplo: 500000."),
            ("Concentración por contraparte (%)", "alerta_concentracion", "Ejemplo: 30."),
            ("Compras sobre ventas (%)", "alerta_compras_ventas", "Ejemplo: 80."),
            ("Cantidad de facturas en un día", "alerta_facturas_dia", "Número entero."),
            ("Cantidad de facturas por contraparte", "alerta_facturas_contraparte", "Número entero."),
        )
        for row, (label, key, help_text) in enumerate(fields, start=1):
            self._field(frame, row, label, key, help_text=help_text)
            self.vars[key].set(str(defaults[key]))

    def _load(self) -> None:
        bundle = self.app.client_service.get_bundle(self.client_id)
        if not bundle:
            messagebox.showerror("Cliente inexistente", "No se encontró la ficha solicitada.")
            self.destroy()
            return
        client, fiscal, mono = bundle["client"], bundle["fiscal"], bundle["monotributo"]
        iibb = self.app.iibb_service.get_profile(self.client_id)
        alerts = self.app.config_service.get_client_alerts(self.client_id)
        mapping = {
            "nombre": client.get("nombre_razon_social", ""),
            "cuit": client.get("cuit_cuil", ""),
            "tipo_persona": client.get("tipo_persona", "persona_humana"),
            "dni": client.get("dni", ""),
            "fecha_nacimiento": display_date(client.get("fecha_nacimiento", "") or ""),
            "nacionalidad": client.get("nacionalidad", ""),
            "estado_civil": client.get("estado_civil", ""),
            "telefono": client.get("telefono", ""),
            "email": client.get("email", ""),
            "instagram": client.get("instagram", ""),
            "domicilio": client.get("domicilio", ""),
            "rubro": client.get("rubro", client.get("actividad", "")),
            "fecha_alta_estudio": display_date(client.get("fecha_alta_estudio", "") or ""),
            "estado": client.get("estado", "activo"),
            "observaciones": client.get("observaciones", ""),
            "regimen": fiscal.get("regimen_principal", "sin_definir"),
            "condicion_iva": fiscal.get("condicion_iva", ""),
            "observaciones_fiscales": fiscal.get("observaciones", ""),
            "categoria": mono.get("categoria_actual", "A"),
            "mono_actividad": mono.get("actividad_fiscal", mono.get("actividad", "Servicios")),
            "mono_codigo_actividad": mono.get("codigo_actividad", ""),
            "mono_denominacion": mono.get("denominacion", ""),
            "mono_fecha_alta": display_date(mono.get("fecha_alta", "") or ""),
            "mono_fecha_baja": display_date(mono.get("fecha_baja_monotributo", "") or ""),
            "mono_estado": mono.get("estado", "activo"),
            "mono_observaciones": mono.get("observaciones_fiscales", ""),
            "mono_tipo_actividad": mono.get("tipo_actividad", "Servicios"),
            "mono_aporta_sipa": mono.get("aporta_sipa", "Sí"),
            "mono_aporta_obra_social": mono.get("aporta_obra_social", "Sí"),
            "mono_adherentes": mono.get("adherentes_obra_social", 0),
            "mono_condicion_especial": mono.get("condicion_especial", "Sin condición especial"),
            "iibb_jurisdiccion": iibb.get("jurisdiccion", ""),
            "iibb_regimen": iibb.get("regimen_principal", "Régimen simplificado"),
            "iibb_actividad": iibb.get("actividad", ""),
            "iibb_alicuota": iibb.get("alicuota", 0.035),
            "iibb_fecha_alta": display_date(iibb.get("fecha_alta", "") or ""),
            "iibb_fecha_baja": display_date(iibb.get("fecha_baja", "") or ""),
            "iibb_estado": iibb.get("estado", "activo"),
            "iibb_observaciones": iibb.get("observaciones", ""),
            "alerta_limite": alerts["monotributo_alerta_porcentaje"] * 100,
            "alerta_monto": alerts["monto_comprobante_significativo"],
            "alerta_concentracion": alerts["concentracion_porcentaje"] * 100,
            "alerta_compras_ventas": alerts["compras_ventas_alerta"] * 100,
            "alerta_facturas_dia": alerts["muchas_facturas_dia"],
            "alerta_facturas_contraparte": alerts["muchas_facturas_cliente"],
        }
        for key, value in mapping.items():
            self.vars[key].set(value)
        self._refresh_iibb_jurisdictions()

    def save(self) -> None:
        try:
            activity_code = self.vars["mono_codigo_actividad"].get().strip()
            if activity_code and not activity_code.isdigit():
                raise ValueError("El código de actividad debe contener solamente números.")
            fiscal_date = ""
            mono_date = self.vars["mono_fecha_alta"].get().strip()
            birth_date = self.vars["fecha_nacimiento"].get().strip()
            study_date = self.vars["fecha_alta_estudio"].get().strip()
            mono_end = self.vars["mono_fecha_baja"].get().strip()
            if birth_date:
                birth_date = normalize_date(birth_date)
            if study_date:
                study_date = normalize_date(study_date)
            if mono_date:
                mono_date = normalize_date(mono_date)
            if mono_end:
                mono_end = normalize_date(mono_end)
            client = Client(
                id=self.client_id,
                nombre_razon_social=self.vars["nombre"].get(),
                cuit_cuil=self.vars["cuit"].get(),
                tipo_persona=self.vars["tipo_persona"].get(),
                dni=self.vars["dni"].get(),
                fecha_nacimiento=birth_date,
                nacionalidad=self.vars["nacionalidad"].get(),
                estado_civil=self.vars["estado_civil"].get(),
                telefono=self.vars["telefono"].get(),
                email=self.vars["email"].get(),
                instagram=self.vars["instagram"].get(),
                domicilio=self.vars["domicilio"].get(),
                rubro=self.vars["rubro"].get(),
                fecha_alta_estudio=study_date,
                estado=self.vars["estado"].get(),
                observaciones=self.vars["observaciones"].get(),
            )
            fiscal = FiscalProfile(
                regimen_principal=self.vars["regimen"].get(),
                condicion_iva=self.vars["condicion_iva"].get(),
                fecha_alta=fiscal_date,
                observaciones=self.vars["observaciones_fiscales"].get(),
            )
            mono = MonotributoProfile(
                categoria_actual=self.vars["categoria"].get(),
                actividad_fiscal=self.vars["mono_actividad"].get(),
                codigo_actividad=activity_code,
                denominacion=self.vars["mono_denominacion"].get(),
                fecha_alta=mono_date,
                fecha_baja=mono_end,
                estado=self.vars["mono_estado"].get(),
                observaciones_fiscales=self.vars["mono_observaciones"].get(),
                tipo_actividad=self.vars["mono_tipo_actividad"].get(),
                aporta_sipa=self.vars["mono_aporta_sipa"].get(),
                aporta_obra_social=self.vars["mono_aporta_obra_social"].get(),
                adherentes_obra_social=int(positive_number(self.vars["mono_adherentes"].get() or 0, "Adherentes", True)),
                condicion_especial=self.vars["mono_condicion_especial"].get(),
            )
            client_id = self.app.client_service.save(client, fiscal, mono)
            iibb_start = self.vars["iibb_fecha_alta"].get().strip()
            iibb_end = self.vars["iibb_fecha_baja"].get().strip()
            self.app.iibb_service.save_profile(client_id, {
                "jurisdiccion": self.vars["iibb_jurisdiccion"].get(),
                "regimen_principal": self.vars["iibb_regimen"].get(),
                "actividad": self.vars["iibb_actividad"].get(),
                "alicuota": float(self.vars["iibb_alicuota"].get().replace(",", ".")),
                "fecha_alta": normalize_date(iibb_start) if iibb_start else "",
                "fecha_baja": normalize_date(iibb_end) if iibb_end else "",
                "estado": self.vars["iibb_estado"].get(),
                "observaciones": self.vars["iibb_observaciones"].get(),
            })
            percentage_values = {
                "monotributo_alerta_porcentaje": positive_number(
                    self.vars["alerta_limite"].get(), "Porcentaje del límite", True
                ) / 100,
                "concentracion_porcentaje": positive_number(
                    self.vars["alerta_concentracion"].get(), "Concentración", True
                ) / 100,
                "compras_ventas_alerta": positive_number(
                    self.vars["alerta_compras_ventas"].get(), "Compras sobre ventas", True
                ) / 100,
            }
            if any(value > 1 for value in percentage_values.values()):
                raise ValueError("Los porcentajes de alerta deben estar entre 0 y 100 %.")
            daily_count = positive_number(
                self.vars["alerta_facturas_dia"].get(), "Facturas por día"
            )
            counterparty_count = positive_number(
                self.vars["alerta_facturas_contraparte"].get(),
                "Facturas por contraparte",
            )
            if not daily_count.is_integer() or not counterparty_count.is_integer():
                raise ValueError("Las cantidades de facturas deben ser números enteros.")
            self.app.config_service.save_client_alerts(
                client_id,
                {
                    **percentage_values,
                    "monto_comprobante_significativo": positive_number(
                        self.vars["alerta_monto"].get(), "Importe mínimo", True
                    ),
                    "muchas_facturas_dia": daily_count,
                    "muchas_facturas_cliente": counterparty_count,
                },
            )
            self.app.alert_service.refresh(client_id)
            self.on_saved()
            self.destroy()
        except Exception as error:
            messagebox.showerror("No se pudo guardar", str(error), parent=self)


class IibbJurisdictionsDialog(tk.Toplevel):
    REGIMES = ("Local", "Convenio Multilateral", "Régimen Simplificado", "Régimen General", "Exento", "No corresponde", "A revisar")
    STATES = ("Activo", "Pendiente de alta", "Baja", "En regularización", "A revisar", "No corresponde")

    def __init__(self, parent, app, client_id: int, callback) -> None:
        super().__init__(parent)
        self.app, self.client_id, self.callback = app, client_id, callback
        self.title("Jurisdicciones / Porcentaje de distribución")
        fit_window(self, 980, 650); self.transient(parent.winfo_toplevel()); self.grab_set()
        form = ttk.LabelFrame(self, text="Agregar o modificar jurisdicción", padding=12)
        form.pack(fill="x", padx=12, pady=12)
        self.vars = {key: tk.StringVar() for key in ("jurisdiccion", "porcentaje", "regimen", "fecha_alta", "estado", "observaciones")}
        fields = (
            ("Jurisdicción", "jurisdiccion", ARGENTINA_JURISDICTIONS),
            ("Porcentaje", "porcentaje", None), ("Régimen", "regimen", self.REGIMES),
            ("Fecha de alta", "fecha_alta", "date"), ("Estado", "estado", self.STATES),
            ("Observaciones", "observaciones", None),
        )
        for index, (label, key, kind) in enumerate(fields):
            row, column = divmod(index, 3); base = column * 2
            ttk.Label(form, text=label).grid(row=row, column=base, sticky="w", padx=(0, 4), pady=4)
            if kind == "date": widget = DateEntry(form, self.vars[key])
            elif isinstance(kind, tuple): widget = ttk.Combobox(form, textvariable=self.vars[key], values=kind, state="readonly")
            else: widget = ttk.Entry(form, textvariable=self.vars[key])
            widget.grid(row=row, column=base+1, sticky="ew", padx=(0, 10), pady=4); form.columnconfigure(base+1, weight=1)
        self.vars["regimen"].set("Convenio Multilateral"); self.vars["estado"].set("Activo"); self.vars["porcentaje"].set("0,00")
        ttk.Button(form, text="Guardar jurisdicción", style="Primary.TButton", command=self.save).grid(row=2, column=5, sticky="e", pady=6)
        container = ttk.Frame(self, padding=(12,0,12,12)); container.pack(fill="both", expand=True)
        columns = ("jurisdiccion", "porcentaje", "regimen", "fecha_alta", "estado", "observaciones")
        self.tree = ttk.Treeview(container, columns=columns, show="headings")
        for key in columns:
            self.tree.heading(key, text=key.replace("_", " ").title()); self.tree.column(key, width=140, anchor="center" if key in ("porcentaje", "fecha_alta", "estado") else "w")
        y = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=y.set)
        self.tree.grid(row=0,column=0,sticky="nsew"); y.grid(row=0,column=1,sticky="ns"); container.rowconfigure(0,weight=1); container.columnconfigure(0,weight=1)
        footer = ttk.Frame(container); footer.grid(row=1,column=0,sticky="ew",pady=8)
        self.total_label = ttk.Label(footer, style="Subtitle.TLabel"); self.total_label.pack(side="left")
        ttk.Button(footer, text="Eliminar seleccionada", command=self.delete).pack(side="right")
        ttk.Button(footer, text="Cerrar", command=self.close).pack(side="right", padx=6)
        self.tree.bind("<Double-1>", lambda _event: self.load_selected()); self.refresh()

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for row in self.app.iibb_service.list_jurisdictions(self.client_id):
            self.tree.insert("", "end", iid=row["jurisdiccion"], values=(row["jurisdiccion"], f"{number_ar(row['porcentaje'])}%", row["regimen"], display_date(row["fecha_alta"]), row["estado"], row["observaciones"]))
        total = self.app.iibb_service.jurisdiction_total(self.client_id)
        warning = " · Advertencia: la suma no es 100,00 %" if abs(total - 100) > .01 else " · Distribución completa"
        self.total_label.configure(text=f"Total: {number_ar(total)}%{warning}")

    def load_selected(self):
        selected = self.tree.selection()
        if not selected: return
        row = next(item for item in self.app.iibb_service.list_jurisdictions(self.client_id) if item["jurisdiccion"] == selected[0])
        for key in self.vars: self.vars[key].set(display_date(row[key]) if key == "fecha_alta" else row.get(key, ""))

    def save(self):
        try:
            data = {key: var.get().strip() for key,var in self.vars.items()}
            if data["fecha_alta"]: data["fecha_alta"] = normalize_date(data["fecha_alta"])
            self.app.iibb_service.save_jurisdiction(self.client_id, data); self.refresh(); self.callback()
        except Exception as error: messagebox.showerror("No se pudo guardar", str(error), parent=self)

    def delete(self):
        selected = self.tree.selection()
        if selected and messagebox.askyesno("Confirmar", "¿Eliminar la jurisdicción seleccionada?", parent=self):
            self.app.iibb_service.delete_jurisdiction(self.client_id, selected[0]); self.refresh(); self.callback()

    def close(self): self.callback(); self.destroy()
