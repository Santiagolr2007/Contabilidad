from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from models import Client, FiscalProfile, MonotributoProfile
from utils.formatters import normalize_date
from utils.validators import positive_number

from .common import ScrollableFrame, fit_window, selected_tree_id
from .date_widgets import DateEntry


class ClientsView(ttk.Frame):
    def __init__(self, parent, app, action: str | None = None) -> None:
        super().__init__(parent, padding=22)
        self.app = app
        self.search = tk.StringVar()
        self.include_inactive = tk.BooleanVar(value=False)

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

        columns = ("cuit", "tipo", "actividad", "regimen", "categoria", "estado")
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Nombre / razón social")
        self.tree.column("#0", width=240)
        settings = (
            ("cuit", "CUIT/CUIL", 110),
            ("tipo", "Persona", 110),
            ("actividad", "Actividad", 190),
            ("regimen", "Régimen", 140),
            ("categoria", "Categoría", 75),
            ("estado", "Estado", 80),
        )
        for column, label, width in settings:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width)
        tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _event: self.edit_client())

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Editar / ficha fiscal", command=self.edit_client).pack(
            side="left"
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

        self.refresh()
        if action == "new":
            self.after(80, self.new_client)

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        clients = self.app.client_service.list_clients(
            self.search.get(), self.include_inactive.get()
        )
        for client in clients:
            self.tree.insert(
                "",
                "end",
                iid=str(client["id"]),
                text=client["nombre_razon_social"],
                values=(
                    client["cuit_cuil"],
                    client["tipo_persona"].replace("_", " ").title(),
                    client.get("rubro_display", ""),
                    client["regimen_principal"].replace("_", " ").title(),
                    client["categoria_actual"],
                    client["estado"].title(),
                ),
            )

    def new_client(self) -> None:
        ClientForm(self, self.app, None, self.refresh)

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

    def _build_iibb(self, frame) -> None:
        ttk.Label(
            frame,
            text="Completá esta sección si el cliente está inscripto en Ingresos Brutos.",
            style="Subtitle.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._field(
            frame, 1, "Jurisdicción", "iibb_jurisdiccion",
            help_text="Provincia u organismo: por ejemplo ARBA, AGIP o Santa Fe."
        )
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
            "fecha_nacimiento": client.get("fecha_nacimiento", "") or "",
            "nacionalidad": client.get("nacionalidad", ""),
            "estado_civil": client.get("estado_civil", ""),
            "telefono": client.get("telefono", ""),
            "email": client.get("email", ""),
            "instagram": client.get("instagram", ""),
            "domicilio": client.get("domicilio", ""),
            "rubro": client.get("rubro", client.get("actividad", "")),
            "fecha_alta_estudio": client.get("fecha_alta_estudio", "") or "",
            "estado": client.get("estado", "activo"),
            "observaciones": client.get("observaciones", ""),
            "regimen": fiscal.get("regimen_principal", "sin_definir"),
            "condicion_iva": fiscal.get("condicion_iva", ""),
            "observaciones_fiscales": fiscal.get("observaciones", ""),
            "categoria": mono.get("categoria_actual", "A"),
            "mono_actividad": mono.get("actividad_fiscal", mono.get("actividad", "Servicios")),
            "mono_codigo_actividad": mono.get("codigo_actividad", ""),
            "mono_denominacion": mono.get("denominacion", ""),
            "mono_fecha_alta": mono.get("fecha_alta", "") or "",
            "mono_fecha_baja": mono.get("fecha_baja_monotributo", "") or "",
            "mono_estado": mono.get("estado", "activo"),
            "mono_observaciones": mono.get("observaciones_fiscales", ""),
            "iibb_jurisdiccion": iibb.get("jurisdiccion", ""),
            "iibb_regimen": iibb.get("regimen_principal", "Régimen simplificado"),
            "iibb_actividad": iibb.get("actividad", ""),
            "iibb_alicuota": iibb.get("alicuota", 0.035),
            "iibb_fecha_alta": iibb.get("fecha_alta", "") or "",
            "iibb_fecha_baja": iibb.get("fecha_baja", "") or "",
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
