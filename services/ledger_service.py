from __future__ import annotations

import json
from datetime import date, timedelta

from database import Database
from utils.formatters import normalize_date, normalize_period
from utils.validators import positive_number, required


def field(key: str, label: str, options: tuple[str, ...] = ()) -> tuple:
    return key, label, options


class LedgerService:
    """Legajo extensible: todas las áreas usan el mismo CRUD y trazabilidad."""

    SECTIONS = {
        "datos_complementarios": ("Datos Complementarios", (
            field("tipo_cliente", "Tipo de cliente", ("Persona humana", "Persona jurídica", "Sucesión indivisa", "Otro")),
            field("estado_cliente", "Estado del cliente", ("Activo", "En alta", "En regularización", "Pausado", "Baja", "Ex cliente", "Solo consulta", "Pendiente de documentación")),
            field("domicilio_real", "Domicilio real"), field("domicilio_legal", "Domicilio legal"), field("domicilio_fiscal", "Domicilio fiscal"), field("domicilio_explotacion", "Domicilio de explotación"),
            field("whatsapp", "WhatsApp"), field("contacto_principal", "Contacto principal"), field("cargo_vinculo", "Cargo / vínculo"),
            field("tipo_societario", "Tipo societario", ("SRL", "SA", "SAS", "Asociación civil", "Fundación", "Cooperativa", "Sociedad simple", "Sociedad de hecho", "Otro")),
            field("fecha_constitucion", "Fecha de constitución"), field("fecha_inscripcion", "Fecha de inscripción"),
            field("jurisdiccion_inscripcion", "Jurisdicción de inscripción", ("IGJ", "DPPJ Buenos Aires", "Registro Público Provincial", "Otra jurisdicción")), field("numero_inscripcion", "Número de inscripción"),
            field("fecha_cierre_ejercicio", "Fecha de cierre de ejercicio"), field("representante_legal", "Representante legal"), field("socios", "Socios / accionistas"), field("administradores", "Administradores / gerentes / directores"), field("apoderados", "Apoderados"),
            field("estado_societario", "Estado societario", ("Regular", "Pendiente", "Irregular", "En actualización", "Baja", "No corresponde")),
            field("observaciones", "Observaciones"),
        )),
        "servicio_presupuesto": ("Servicio y Presupuesto", (
            field("alta_estudio", "Alta inicial en el estudio"),
            field("tipo_servicio", "Tipo de servicio", ("Abono mensual", "Alta inicial", "Liquidación impositiva", "Monotributo", "IVA", "Ganancias", "Autónomos", "IIBB local", "Convenio Multilateral", "Sueldos", "Casas particulares", "Societario", "Habilitación municipal", "Bienes personales", "Facturación", "Conciliaciones", "Presentaciones anuales", "Trámite puntual", "Asesoramiento general", "Otro")),
            field("alcance", "Alcance del servicio"), field("exclusiones", "Exclusiones"), field("documentacion_requerida", "Documentación que debe enviar"),
            field("periodicidad", "Periodicidad", ("Mensual", "Bimestral", "Trimestral", "Semestral", "Anual", "Por operación", "A requerimiento", "No corresponde")),
            field("fecha_inicio", "Fecha de inicio"), field("estado_servicio", "Estado", ("Activo", "En preparación", "Pendiente de documentación", "Suspendido", "Finalizado", "Cancelado", "No corresponde")),
            field("fecha_presupuesto", "Fecha del presupuesto"), field("fecha_vencimiento", "Fecha de vencimiento del presupuesto / pago"), field("concepto", "Concepto presupuestado", ("Alta inicial", "Abono mensual", "Liquidación mensual", "Presentación anual", "Regularización fiscal", "Regularización impositiva", "Fiscalización", "Moratoria / plan de pago", "Alta ARCA", "Alta IIBB", "Alta municipal", "Alta empleador", "Sueldos", "Casas particulares", "Societario", "Certificación", "Informe", "Consulta", "Otro")), field("tipo_honorario", "Tipo de honorario", ("Fijo mensual", "Fijo por trámite", "Por hora", "Por presentación", "Por empleado", "Por impuesto", "Por paquete", "Bonificado", "Sin cargo", "Otro")),
            field("valor_presupuestado", "Valor presupuestado"), field("moneda", "Moneda", ("ARS", "USD", "Otro")),
            field("periodicidad_presupuesto", "Periodicidad del presupuesto", ("Único pago", "Mensual", "Bimestral", "Trimestral", "Semestral", "Anual", "Por evento", "Otro")),
            field("estado_presupuesto", "Estado presupuesto", ("Borrador", "Enviado", "Aceptado", "Rechazado", "Vencido", "Reemplazado", "Cancelado")), field("fecha_aceptacion", "Fecha de aceptación"), field("medio_aceptacion", "Medio de aceptación", ("WhatsApp", "Email", "Firma presencial", "Firma digital", "Verbal", "Otro")), field("condiciones_presupuesto", "Condiciones del presupuesto"), field("observaciones", "Observaciones"),
        )),
        "pagos": ("Honorarios", (
            field("fecha_emision", "Fecha de emisión"), field("periodo", "Período MM/AAAA"),
            field("concepto", "Concepto", ("Abono mensual", "Alta inicial", "Liquidación impositiva", "Monotributo", "IVA", "Ganancias", "IIBB", "Convenio Multilateral", "Autónomos", "Sueldos", "Casas particulares", "Presentación anual", "Bienes personales", "Regularización", "Plan de pagos", "Trámite puntual", "Consulta", "Otro")), field("importe_facturado", "Importe facturado"),
            field("importe_cobrado", "Importe cobrado"), field("saldo_pendiente", "Saldo pendiente"),
            field("moneda", "Moneda", ("ARS", "USD", "Otro")), field("estado_pago", "Estado de cobro", ("Pendiente", "Cobrado", "Cobro parcial", "Vencido", "Bonificado", "Anulado", "No corresponde")),
            field("fecha_vencimiento", "Fecha de vencimiento"), field("fecha_cobro", "Fecha de cobro"),
            field("medio_pago", "Medio de cobro", ("Efectivo", "Transferencia", "Mercado Pago", "Débito", "Crédito", "Cheque", "Cuenta DNI", "MODO", "Otro")),
            field("comprobante_emitido", "Comprobante emitido", ("Sí", "No", "Pendiente", "No corresponde")), field("tipo_comprobante", "Tipo de comprobante", ("Factura A", "Factura B", "Factura C", "Recibo", "Nota de crédito", "Comprobante interno", "No corresponde")), field("numero_comprobante", "Número de comprobante"), field("observaciones", "Observaciones"),
        )),
        "obligaciones": ("Valores Mensuales", (
            field("periodo", "Período MM/AAAA"), field("tipo_obligacion", "Tipo de obligación", ("Monotributo", "Responsable Inscripto", "IVA", "Ganancias", "Autónomos", "Bienes Personales", "IIBB Local", "Convenio Multilateral", "Régimen Simplificado IIBB", "Tasa Municipal", "Seguridad e Higiene", "Empleador / F.931", "Casas Particulares", "Abono del estudio", "Plan de pago", "Moratoria", "Otro")),
            field("organismo", "Organismo", ("ARCA", "ARBA", "AGIP", "COMARB", "Municipio", "Ministerio de Trabajo", "Estudio", "Banco", "Otro")), field("categoria", "Categoría / encuadre"),
            field("importe_mensual", "Importe mensual"), field("moneda", "Moneda", ("ARS", "USD", "Otro")),
            field("fecha_vencimiento", "Fecha de vencimiento"), field("estado", "Estado", ("Pendiente", "Pagado", "Vencido", "No corresponde", "Bonificado", "En plan", "A revisar")),
            field("fecha_pago", "Fecha de pago"), field("medio_pago", "Medio de pago", ("VEP", "Débito automático", "Transferencia", "Mercado Pago", "Efectivo", "Pago mis cuentas", "Homebanking", "Otro")), field("comprobante_link", "Comprobante / link"), field("observaciones", "Observaciones"),
        )),
        "relevamiento": ("Relevamiento", (
            field("actividad_principal", "Actividad principal real"), field("actividad_secundaria", "Actividad secundaria real"), field("actividades_declaradas", "Actividades declaradas"), field("fecha_inicio_real", "Fecha real de inicio"), field("fecha_inicio_fiscal", "Fecha fiscal de inicio"),
            field("forma_trabajo", "Forma de trabajo", ("Local físico", "Online", "Domicilio particular", "Depósito", "Fábrica", "Oficina", "Servicios a domicilio", "Marketplace", "Mixta", "Otro")),
            field("lugar_actividad", "Lugar donde desarrolla la actividad"), field("trabaja_online", "Trabaja online", ("Sí", "No", "Parcialmente", "No corresponde")), field("trabaja_local", "Trabaja en local", ("Sí", "No", "En trámite", "No corresponde")), field("trabaja_domicilio", "Trabaja desde domicilio", ("Sí", "No", "Parcialmente", "No corresponde")), field("posee_deposito", "Posee depósito", ("Sí", "No", "Tercero", "No corresponde")),
            field("presta_servicios", "Presta servicios", ("Sí", "No", "Mixto")), field("vende_bienes", "Vende bienes", ("Sí", "No", "Mixto")), field("fabrica", "Fabrica", ("Sí", "No", "Terceriza", "No corresponde")), field("revende", "Revende", ("Sí", "No", "No corresponde")), field("importa", "Importa", ("Sí", "No", "Planea hacerlo", "No corresponde")), field("exporta", "Exporta", ("Sí", "No", "Planea hacerlo", "No corresponde")),
            field("canales_venta", "Canales de venta (local, Instagram, WhatsApp, web, marketplaces, mayorista/minorista, transferencia/efectivo)"), field("tipo_clientes", "Tipo de clientes", ("Consumidor final", "Monotributistas", "Responsables inscriptos", "Empresas", "Estado", "Exterior", "Mixto", "Otro")), field("clientes_principales", "Clientes principales"), field("clientes_vinculados", "Clientes vinculados", ("Sí", "No", "A revisar", "No corresponde")), field("ventas_familiares", "Ventas a familiares", ("Sí", "No", "A revisar", "No corresponde")), field("ventas_empresas", "Ventas a empresas", ("Sí", "No", "A revisar")), field("ventas_consumidor_final", "Ventas a consumidor final", ("Sí", "No", "Principalmente", "Parcialmente")), field("ventas_estado", "Ventas al Estado", ("Sí", "No", "Planea hacerlo")), field("concentracion_clientes", "Concentración de clientes", ("Baja", "Media", "Alta", "A revisar")), field("forma_cobro", "Forma habitual de cobro", ("Efectivo", "Transferencia", "Mercado Pago", "Tarjeta", "Cheque", "Dólares", "Mixto", "Otro")), field("cuentas_propias", "Uso de cuentas propias", ("Sí", "No", "Parcialmente", "A revisar")), field("cuentas_terceros", "Uso de cuentas de terceros", ("No", "Sí", "Ocasional", "Frecuente", "A regularizar")), field("cobros_extranjera", "Cobros en moneda extranjera", ("Sí", "No", "Ocasional", "A revisar")),
            field("proveedores_principales", "Proveedores principales"), field("tipo_compras", "Tipo de compras", ("Mercadería", "Insumos", "Servicios", "Alquileres", "Honorarios", "Publicidad", "Logística", "Equipamiento", "Mixto", "Otro")), field("compras_factura", "Compras con factura", ("Todas", "La mayoría", "Algunas", "Ninguna", "A revisar")), field("compras_sin_factura", "Compras sin factura", ("No", "Sí", "Ocasional", "Frecuente", "A regularizar")), field("compras_exterior", "Compras al exterior", ("Sí", "No", "Planea hacerlo")), field("compras_efectivo", "Compras en efectivo", ("Sí", "No", "Ocasional", "Frecuente")), field("compras_extranjera", "Compras en moneda extranjera", ("Sí", "No", "Ocasional", "A revisar")), field("frecuencia_compras", "Frecuencia de compras", ("Diaria", "Semanal", "Quincenal", "Mensual", "Esporádica", "A demanda")), field("proveedores_vinculados", "Proveedores vinculados", ("Sí", "No", "A revisar", "No corresponde")), field("remitos", "Existencia de remitos", ("Sí", "No", "Parcialmente", "No corresponde")), field("ordenes_compra", "Existencia de órdenes de compra", ("Sí", "No", "Parcialmente", "No corresponde")), field("comprobantes_internos", "Existencia de comprobantes internos", ("Sí", "No", "Parcialmente", "No corresponde")), field("observaciones", "Observaciones"),
        )),
        "documentacion": ("Documentación", (
            field("tipo_registro", "Tipo de registro", ("Documento", "Acceso")),
            field("documento", "Documento", ("DNI", "Constancia de CUIT", "Constancia ARCA", "Constancia IIBB", "Constancia municipal", "Contrato social / estatuto", "Actas", "Poderes", "Constancia de CBU", "Comprobante de domicilio", "Contrato de alquiler", "Habilitación municipal", "Últimas DDJJ", "Últimos pagos", "Papeles de trabajo anteriores", "Datos del contador anterior", "Contratos relevantes", "Recibos de sueldo", "Bienes registrables", "Préstamos", "Deudas", "Extractos bancarios", "Mercado Pago", "Mercado Libre", "Tarjetas de crédito", "Facturas emitidas", "Facturas recibidas", "Comprobantes de pago", "Planes de pago", "Intimaciones", "Fiscalizaciones", "Otro")), field("estado", "Estado", ("Solicitado", "Recibido", "Pendiente", "Incompleto", "Vencido", "No corresponde", "Requiere actualización")),
            field("fecha_solicitud", "Fecha solicitud"), field("fecha_recepcion", "Fecha recepción"), field("obligatorio", "Obligatorio", ("Sí", "No", "Según caso", "No corresponde")), field("archivo_link", "Link o archivo"),
            field("plataforma", "Organismo / plataforma", ("ARCA", "ARBA", "AGIP", "COMARB", "Municipio", "Banco", "Mercado Pago", "Mercado Libre", "Sistema de facturación", "Sistema de gestión", "Email", "Otro")), field("usuario_acceso", "Usuario"), field("contrasena_referencia", "Contraseña / referencia segura"), field("estado_acceso", "Estado de acceso", ("Disponible", "Pendiente", "Incorrecto", "Bloqueado", "No corresponde", "A actualizar")), field("nivel_acceso", "Nivel de acceso"), field("fecha_control", "Fecha de control"), field("observaciones", "Observaciones"),
        )),
        "arca": ("ARCA", (
            field("estado_cuit", "Estado CUIT", ("Activo", "Limitado", "Inactivo", "Suspendido", "Baja", "A revisar")), field("domicilio_fiscal_electronico", "Domicilio fiscal electrónico", ("Adherido", "No adherido", "A revisar")),
            field("impuesto", "Impuesto / régimen", ("Monotributo", "IVA", "Ganancias personas humanas", "Ganancias sociedades", "Autónomos", "Bienes personales", "Empleador", "Seguridad social", "Regímenes de información", "Retenciones / percepciones", "Otros")), field("estado", "Estado", ("Activo", "Pendiente", "Baja", "No corresponde", "A revisar")), field("fecha_alta", "Fecha alta"),
            field("categoria_monotributo", "Categoría monotributo", ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "No corresponde", "A revisar")), field("riesgo_exclusion", "Riesgo de exclusión", ("Bajo", "Medio", "Alto", "Excluido", "A revisar", "No corresponde")), field("estado_monotributo", "Estado monotributo", ("Activo", "Baja", "Excluido", "Suspendido", "No corresponde", "A revisar")),
            field("factura_a", "Factura A", ("Autorizada", "No autorizada", "Factura M", "Sujeta a evaluación", "No corresponde")), field("libro_iva_digital", "Libro IVA Digital", ("Presentado", "Pendiente", "Vencido", "No corresponde", "A revisar")), field("estado_control", "Estado del control", ("OK", "Revisar", "Urgente", "Pendiente", "No corresponde")), field("deuda", "Deuda", ("Sin deuda detectada", "Con deuda", "En plan", "A revisar", "No corresponde")), field("ddjj_pendientes", "DDJJ pendientes", ("No", "Sí", "A revisar", "No corresponde")), field("notificaciones_dfe", "Notificaciones DFE", ("Sin pendientes", "Pendientes", "Urgentes", "A revisar")), field("ultimo_control", "Último control"), field("resultado_control", "Resultado"), field("proximo_paso", "Próximo paso"), field("observaciones", "Observaciones"),
            field("fecha_inscripcion_arca", "Fecha de inscripción ARCA"),field("mes_cierre", "Mes de cierre"),
            field("dependencia", "Dependencia"),field("region", "Región"),field("tipo_inscripcion", "Tipo de inscripción"),
            field("sistema_control", "Sistema de control"),field("segmento", "Segmento"),
            field("foto_registrada", "Foto registrada"),field("firma_registrada", "Firma registrada"),field("huella_registrada", "Huella registrada"),
        )),
        "contactos_arca": ("Contactos ARCA", (
            field("clase", "Clase", ("Email", "Teléfono")),field("valor", "Dirección / número"),
            field("tipo", "Tipo"),field("estado", "Estado"),field("fecha_actualizacion", "Fecha actualización"),
            field("principal", "Principal", ("Sí", "No")),field("observaciones", "Observaciones"),
        )),
        "domicilios_arca": ("Domicilios ARCA", (
            field("tipo", "Tipo de domicilio"),field("estado", "Estado"),field("direccion", "Dirección"),
            field("localidad", "Localidad"),field("codigo_postal", "Código postal"),field("provincia", "Provincia"),
            field("nomenclado", "Nomenclado"),field("fecha_baja", "Fecha baja"),field("fecha_actualizacion", "Fecha actualización"),
            field("coordenadas", "Coordenadas"),field("observaciones", "Observaciones"),
        )),
        "migratorios_arca": ("Datos Migratorios", (
            field("tipo_residencia", "Tipo de residencia"),field("vencimiento_migratorio", "Vencimiento migratorio"),
            field("documento_extranjero", "Documento extranjero"),field("fecha_actualizacion", "Fecha actualización"),
            field("observaciones", "Observaciones"),
        )),
        "iibb_legajo": ("IIBB", (
            field("jurisdiccion", "Jurisdicción", ("Buenos Aires", "CABA", "Catamarca", "Chaco", "Chubut", "Córdoba", "Corrientes", "Entre Ríos", "Formosa", "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones", "Neuquén", "Río Negro", "Salta", "San Juan", "San Luis", "Santa Cruz", "Santa Fe", "Santiago del Estero", "Tierra del Fuego", "Tucumán", "Otra")), field("regimen", "Régimen", ("Local", "Simplificado", "General", "Convenio Multilateral", "Exento", "No inscripto", "A revisar", "No corresponde")), field("actividad", "Actividad"), field("alicuota", "Alícuota"), field("estado", "Estado", ("Activo", "Baja", "En alta", "En regularización", "No inscripto", "No corresponde", "A revisar")), field("riesgo_fiscal", "Riesgo fiscal", ("Bajo", "Medio", "Alto", "Sin evaluar", "No corresponde")), field("estado_cm", "Estado Convenio Multilateral", ("Activo", "Pendiente de alta", "Baja", "En regularización", "No corresponde", "A revisar")), field("estado_control", "Estado del control", ("OK", "Revisar", "Urgente", "Pendiente", "No corresponde")), field("deuda", "Deuda", ("Sin deuda detectada", "Con deuda", "En plan", "A revisar", "No corresponde")), field("padrones", "Padrones", ("Controlado", "Pendiente", "A revisar", "No corresponde")), field("ultimo_control", "Último control"), field("observaciones", "Observaciones"),
        )),
        "municipal": ("Municipal", (
            field("municipio", "Municipio"), field("habilitacion", "Habilitación", ("Sí", "No", "En trámite", "No corresponde", "A revisar")), field("estado_tramite", "Estado del trámite", ("Vigente", "En trámite", "Pendiente de documentación", "Observado", "Vencido", "Baja", "No corresponde")), field("tramite", "Tasa municipal", ("Seguridad e Higiene", "Publicidad y propaganda", "Habilitación", "Inspección", "Bromatología", "Otra", "No corresponde")), field("numero_cuenta", "Número de cuenta"), field("deuda", "Deuda", ("Sin deuda detectada", "Con deuda", "En plan", "A revisar", "No corresponde")), field("estado", "Control", ("OK", "Revisar", "Urgente", "Pendiente", "No corresponde")), field("ultimo_control", "Último control"), field("vencimiento", "Vencimiento"), field("observaciones", "Observaciones"),
        )),
        "laboral": ("Laboral", (
            field("empleador", "Empleador", ("Sí", "No", "En alta", "No corresponde", "A revisar")), field("condicion", "Estado laboral", ("Sin empleados", "Con empleados activos", "Casas particulares", "En regularización", "Baja como empleador", "A revisar", "No corresponde")), field("empleados", "Cantidad empleados"), field("convenio", "Convenio colectivo"), field("art", "ART", ("Vigente", "Pendiente", "No tiene", "No corresponde", "A revisar")), field("libro_sueldos", "Libro de sueldos digital", ("Activo", "Pendiente", "No corresponde", "A revisar")), field("f931", "F.931", ("Presentado", "Pendiente", "Vencido", "No corresponde", "A revisar")), field("cargas_sociales", "Cargas sociales", ("Al día", "Con deuda", "En plan", "A revisar", "No corresponde")), field("estado", "Estado / control"), field("ultimo_control", "Último control"), field("observaciones", "Observaciones"),
        )),
        "societario": ("Societario Libros", (
            field("estado_societario", "Estado societario", ("Regular", "Pendiente", "Irregular", "En actualización", "Baja", "No corresponde", "A revisar")), field("libro", "Libro / registro", ("Libro Diario", "Inventario y Balances", "Actas", "Registro de socios", "Registro de acciones", "IVA Compras", "IVA Ventas", "Sueldos y Jornales", "Otro")), field("estado", "Estado", ("Rubricado", "Pendiente de rúbrica", "Digital", "No posee", "No corresponde", "A revisar")), field("ultima_registracion", "Última registración"), field("ultimo_periodo", "Último período"), field("periodo_pendiente", "Período pendiente"), field("observaciones", "Observaciones"),
        )),
        "bancos": ("Bancos", (
            field("tipo", "Tipo", ("Banco", "Billetera virtual", "Marketplace", "Posnet", "QR", "Tarjeta de crédito", "Tarjeta de débito", "Cuenta de tercero", "Otro")), field("entidad", "Entidad", ("Banco Galicia", "Banco Nación", "Banco Provincia", "Santander", "BBVA", "Macro", "Mercado Pago", "Mercado Libre", "MODO", "Getnet", "Payway", "Ualá", "Cuenta DNI", "Otro")), field("titularidad", "Titularidad", ("Propia", "De tercero", "Sociedad", "Familiar", "A revisar")), field("uso", "Uso", ("Actividad", "Personal", "Mixto", "No corresponde", "A revisar")), field("estado", "Estado", ("Activo", "Inactivo", "Baja", "Bloqueado", "A revisar")), field("extractos_solicitados", "Extractos solicitados", ("Sí", "No", "Pendiente", "No corresponde")), field("extractos_recibidos", "Extractos recibidos", ("Sí", "No", "Parcial", "No corresponde")), field("conciliacion", "Conciliación", ("Conciliado", "Pendiente", "Con diferencias", "No corresponde", "A revisar")), field("observaciones", "Observaciones"),
        )),
        "riesgos": ("Riesgos", (
            field("tipo_riesgo", "Tipo de riesgo", ("Fiscal", "Monotributo", "IVA", "Ganancias", "IIBB", "Municipal", "Laboral", "Societario", "Bancario", "Cuentas de terceros", "Ventas no facturadas", "Compras sin respaldo", "Inconsistencias ARCA / bancos / marketplaces", "Falta de documentación", "Actividad no declarada", "Jurisdicciones no inscriptas", "Otro")), field("nivel", "Nivel", ("Bajo", "Medio", "Alto", "Urgente", "Sin evaluar")), field("estado", "Estado", ("Detectado", "Informado al cliente", "En regularización", "Regularizado", "Cliente no acepta regularizar", "Pendiente de respuesta", "No corresponde")), field("recomendacion", "Recomendación profesional"), field("fecha_recomendacion", "Fecha recomendación"), field("medio_informado", "Medio informado", ("WhatsApp", "Email", "Reunión", "Llamada", "Nota", "Otro")), field("respuesta_cliente", "Respuesta cliente", ("Aceptó regularizar", "No aceptó regularizar", "Pendiente de respuesta", "Solicitó más información", "No corresponde")), field("observaciones", "Observaciones"),
        )),
        "eventos": ("Tareas Eventos", (
            field("fecha", "Fecha"), field("area", "Área", ("ARCA", "IIBB", "Municipal", "Laboral", "Societario", "Contable", "Bancos", "Facturación", "Documentación", "Pagos", "Presupuesto", "Riesgos", "Otro")), field("tipo_evento", "Tipo de evento", ("Alta", "Baja", "Modificación", "Control", "Presentación", "Pago", "Intimación", "Fiscalización", "Requerimiento", "Pedido de documentación", "Recepción de documentación", "Consulta", "Reunión", "Llamada", "WhatsApp", "Email", "Recomendación profesional", "Regularización", "Recordatorio", "Otro")), field("descripcion", "Descripción"), field("estado", "Estado", ("Pendiente", "En proceso", "Esperando cliente", "Esperando organismo", "Cumplimentada", "Vencida", "Cancelada", "No corresponde")), field("prioridad", "Prioridad", ("Baja", "Media", "Alta", "Urgente")), field("fecha_vencimiento", "Fecha vencimiento"), field("fecha_resolucion", "Fecha de resolución"), field("medio", "Medio"), field("documentacion_vinculada", "Documentación vinculada"), field("link", "Link"), field("proximo_paso", "Próximo paso"), field("alerta", "Alerta", ("Sí", "No")), field("observaciones", "Observaciones"),
        )),
        "vencimientos_legajo": ("Vencimientos", (
            field("organismo", "Organismo", ("ARCA", "ARBA", "AGIP", "COMARB", "Municipio", "IGJ", "DPPJ", "Ministerio de Trabajo", "Banco", "Estudio", "Otro")), field("impuesto_tramite", "Impuesto / trámite"), field("periodo", "Período"), field("fecha_vencimiento", "Fecha vencimiento"), field("tipo", "Tipo", ("Presentación", "Pago", "Renovación", "Recategorización", "Alta", "Baja", "Modificación", "Informe", "Control", "Reunión", "Respuesta a intimación", "Vencimiento de certificado", "Vencimiento contractual", "Otro")), field("estado", "Estado", ("Pendiente", "Cumplido", "Pagado", "Vencido", "No corresponde")), field("link", "Link al comprobante / presentación / carpeta"), field("particularidad", "Particularidad del cliente"), field("requiere_documentacion", "Requiere documentación", ("Sí", "No", "A revisar", "No corresponde")), field("documentacion_pendiente", "Documentación pendiente", ("Sí", "No", "Parcial", "No corresponde")), field("alerta", "Alerta", ("Sí", "No")), field("fecha_aviso", "Fecha de aviso al cliente"), field("medio_aviso", "Medio aviso", ("WhatsApp", "Email", "Llamada", "Presencial", "No avisado", "Otro")), field("observaciones", "Observaciones"),
        )),
        "baja_historial": ("Historial y Baja", (
            field("tipo_cambio", "Tipo de cambio", ("Alta", "Modificación de datos", "Cambio de condición fiscal", "Cambio de servicio", "Cambio de honorarios", "Cambio de estado", "Baja del cliente", "Reactivación", "Otro")), field("dato_modificado", "Dato modificado"), field("estado_anterior", "Estado anterior"), field("estado_nuevo", "Estado nuevo"), field("responsable", "Responsable"), field("motivo", "Motivo", ("Decisión del cliente", "Falta de pago", "Falta de documentación", "Finalización de trámite", "Cambio de contador", "Cese de actividad", "Incumplimiento del cliente", "Otro")), field("fecha_baja", "Fecha baja"), field("ultimo_periodo", "Último período trabajado"), field("documentacion_entregada", "Documentación entregada"), field("pendientes", "Deudas o pendientes"), field("tramites_curso", "Trámites en curso"), field("accesos_eliminados", "Claves devueltas o accesos eliminados"), field("comunicacion_enviada", "Comunicación enviada al cliente"), field("estado_final", "Estado final del legajo"), field("observaciones", "Observaciones"),
        )),
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def list_records(self, client_id: int, section: str) -> list[dict]:
        rows = self.database.query(
            "SELECT * FROM cliente_legajo_registros WHERE cliente_id=? AND seccion=? ORDER BY id DESC",
            (client_id, section),
        )
        result = []
        for row in rows:
            item = dict(row)
            item["datos"] = json.loads(item.pop("datos_json") or "{}")
            result.append(item)
        return result

    def get_record(self, record_id: int) -> dict | None:
        row = self.database.query_one(
            "SELECT * FROM cliente_legajo_registros WHERE id=?", (record_id,)
        )
        if not row:
            return None
        item = dict(row)
        item["datos"] = json.loads(item.pop("datos_json") or "{}")
        return item

    def save_record(
        self, client_id: int, section: str, data: dict, record_id: int | None = None
    ) -> int:
        if section not in self.SECTIONS:
            raise ValueError("La sección del legajo no existe.")
        responsible = str(data.get("responsable") or "NATALIA").strip()
        if section == "pagos":
            billed = positive_number(data.get("importe_facturado", 0), "Importe facturado", True)
            paid = positive_number(data.get("importe_cobrado", 0), "Importe cobrado", True)
            data["saldo_pendiente"] = str(max(round(billed - paid, 2), 0))
        amount = 0.0
        for key in ("importe_mensual", "importe_facturado", "valor_presupuestado"):
            if data.get(key):
                amount = positive_number(data[key], key.replace("_", " "), True)
                break
        saldo = float(data.get("saldo_pendiente") or 0)
        period = str(data.get("periodo") or "").strip().replace("/", "-")
        if period and len(period) == 7 and period[2] == "-":
            period = f"{period[3:]}-{period[:2]}"
        if period:
            period = normalize_period(period)
            data["periodo"] = period
        date_value = next((data.get(k) for k in ("fecha", "fecha_emision", "fecha_solicitud") if data.get(k)), None)
        due = next((data.get(k) for k in ("fecha_vencimiento", "vencimiento") if data.get(k)), None)
        for key in list(data):
            if key.startswith("fecha") and data[key]:
                data[key] = normalize_date(str(data[key]))
        if date_value:
            date_value = normalize_date(str(date_value))
        if due:
            due = normalize_date(str(due))
        description = str(data.get("descripcion") or data.get("concepto") or data.get("documento") or data.get("tipo_obligacion") or data.get("tipo_riesgo") or self.SECTIONS[section][0])
        if section == "servicio_presupuesto" and data.get("estado_presupuesto"):
            status = str(data["estado_presupuesto"])
        else:
            status = str(data.get("estado") or data.get("estado_pago") or data.get("estado_servicio") or "pendiente")
        before = self.get_record(record_id) if record_id else None
        with self.database.connection() as connection:
            if record_id:
                connection.execute(
                    """UPDATE cliente_legajo_registros SET fecha=?,periodo=?,descripcion=?,estado=?,importe=?,saldo=?,vencimiento=?,datos_json=?,responsable=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=? AND cliente_id=?""",
                    (date_value, period, description, status, amount, saldo, due, json.dumps(data, ensure_ascii=False), responsible, record_id, client_id),
                )
                result_id = record_id
                change = "Modificación"
            else:
                cursor = connection.execute(
                    """INSERT INTO cliente_legajo_registros(cliente_id,seccion,fecha,periodo,descripcion,estado,importe,saldo,vencimiento,datos_json,responsable) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (client_id, section, date_value, period, description, status, amount, saldo, due, json.dumps(data, ensure_ascii=False), responsible),
                )
                result_id = int(cursor.lastrowid)
                change = "Alta"
            connection.execute(
                """INSERT INTO cliente_historial(cliente_id,tipo_cambio,seccion,dato_modificado,estado_anterior,estado_nuevo,responsable) VALUES(?,?,?,?,?,?,?)""",
                (client_id, change, section, description, before["estado"] if before else "", status, responsible),
            )
        return result_id

    def delete_record(self, client_id: int, record_id: int) -> int:
        record = self.get_record(record_id)
        if not record or int(record["cliente_id"]) != client_id:
            return 0
        with self.database.connection() as connection:
            cursor = connection.execute("DELETE FROM cliente_legajo_registros WHERE id=? AND cliente_id=?", (record_id, client_id))
            connection.execute(
                """INSERT INTO cliente_historial(cliente_id,tipo_cambio,seccion,dato_modificado,estado_anterior,estado_nuevo,responsable) VALUES(?,?,?,?,?,'Eliminado','NATALIA')""",
                (client_id, "Eliminación", record["seccion"], record["descripcion"], record["estado"]),
            )
            return int(cursor.rowcount)

    def history(self, client_id: int) -> list[dict]:
        return [dict(row) for row in self.database.query(
            "SELECT * FROM cliente_historial WHERE cliente_id=? ORDER BY fecha DESC,id DESC", (client_id,)
        )]

    def summary(self, client_id: int) -> dict:
        client = self.database.query_one(
            """SELECT c.*,COALESCE(df.regimen_principal,'sin_definir') regimen_principal FROM clientes c LEFT JOIN datos_fiscales_cliente df ON df.cliente_id=c.id WHERE c.id=?""", (client_id,)
        )
        if not client:
            raise ValueError("El cliente no existe.")
        records = [dict(row) for row in self.database.query(
            "SELECT * FROM cliente_legajo_registros WHERE cliente_id=?", (client_id,)
        )]
        for record in records:
            record["datos"] = json.loads(record.get("datos_json") or "{}")

        def latest(section: str) -> dict:
            candidates = [record for record in records if record["seccion"] == section]
            return max(candidates, key=lambda value: value["id"], default={})

        def latest_value(section: str, *keys: str, default: str = "") -> str:
            data = latest(section).get("datos", {})
            return next((str(data.get(key) or "") for key in keys if data.get(key)), default)

        today = date.today().isoformat()
        soon = (date.today() + timedelta(days=30)).isoformat()
        pending_payments = [r for r in records if r["seccion"] == "pagos" and r["saldo"] > 0]
        all_payments = [r for r in records if r["seccion"] == "pagos"]
        overdue_payments = [r for r in pending_payments if r["vencimiento"] and r["vencimiento"] < today]
        pending_docs = [r for r in records if r["seccion"] == "documentacion" and r["estado"].casefold() not in ("recibido", "aprobado", "no corresponde")]
        risks = [r for r in records if r["seccion"] == "riesgos" and r["estado"].casefold() not in ("regularizado", "no corresponde")]
        obligations = [r for r in records if r["seccion"] == "obligaciones" and r["estado"].casefold() not in ("pagado", "no corresponde", "bonificado")]
        overdue_obligations = [r for r in obligations if r["vencimiento"] and r["vencimiento"] < today]
        ledger_tasks = [r for r in records if r["seccion"] == "eventos" and r["estado"].casefold() not in ("finalizado", "cancelado", "no corresponde")]
        overdue_ledger_tasks = [r for r in ledger_tasks if r["vencimiento"] and r["vencimiento"] < today]
        tasks = self.database.query_one("SELECT COUNT(*) n,SUM(CASE WHEN fecha_vencimiento<DATE('now') THEN 1 ELSE 0 END) vencidas FROM tareas WHERE cliente_id=? AND LOWER(estado) NOT IN ('finalizado','archivado','cobrado','cumplimentada','cancelada','no corresponde')", (client_id,))
        due = self.database.query_one("SELECT MIN(fecha_vencimiento) fecha FROM vencimientos WHERE cliente_id=? AND LOWER(estado) NOT IN ('pagado','cumplido','no corresponde') AND fecha_vencimiento BETWEEN ? AND ?", (client_id, today, soon))
        generic_due = min((r["vencimiento"] for r in records if r["vencimiento"] and r["estado"].casefold() not in ("pagado", "finalizado", "no corresponde")), default=None)
        completed_sections = len({r["seccion"] for r in records})
        state = "Completo" if completed_sections >= 10 and not pending_docs else "Incompleto"
        risk_values = [json.loads(r["datos_json"] or "{}").get("nivel", "") for r in risks]
        risk_level = "Alto" if any(value.casefold() in ("alto", "urgente") for value in risk_values) else ("Medio" if risks else "Bajo")
        service = latest_value("servicio_presupuesto", "tipo_servicio", "concepto", default="Sin definir")
        activity = latest_value("relevamiento", "actividad_principal", default=dict(client).get("actividad", ""))
        client_type = latest_value("datos_complementarios", "tipo_cliente", default=str(dict(client).get("tipo_persona", "")).replace("_", " ").title())
        client_state = latest_value("datos_complementarios", "estado_cliente", default=str(dict(client).get("estado", "")).title())
        responsible = latest_value("datos_complementarios", "responsable_interno") or latest_value("servicio_presupuesto", "responsable") or "NATALIA"
        controls = []
        for section in ("arca", "iibb_legajo", "municipal", "laboral", "bancos", "eventos"):
            value = latest_value(section, "ultimo_control", "fecha_control", "fecha")
            if value:
                controls.append(value)
        last_control = max(controls, default="—")
        last_contact = latest_value("eventos", "fecha", default="—")
        documentation_state = "Pendiente" if pending_docs else ("Completa" if any(r["seccion"] == "documentacion" for r in records) else "Sin cargar")
        payment_state = "Vencido" if overdue_payments else ("Pendiente" if pending_payments else "Al día")
        payment_dates = [str(r["datos"].get("fecha_cobro")) for r in all_payments if r["datos"].get("fecha_cobro")]
        next_payment_due = min((r["vencimiento"] for r in pending_payments if r["vencimiento"] and r["vencimiento"] >= today), default="—")

        def area_state(section: str) -> str:
            record = latest(section)
            if not record:
                return "A revisar"
            status = str(record.get("estado") or "").casefold()
            if "no corresponde" in status:
                return "No corresponde"
            if any(word in status for word in ("urgente", "vencido", "deuda", "alto", "bloqueado")):
                return "Urgente"
            if any(word in status for word in ("ok", "activo", "pagado", "recibido", "completo", "regularizado", "conciliado")):
                return "OK"
            return "Revisar"

        area_states = {
            "Datos": "Completo" if client["nombre_razon_social"] and client["cuit_cuil"] else "Incompleto",
            "Servicio": "Definido" if latest("servicio_presupuesto") else "Pendiente",
            "Relevamiento": "Completo" if activity else "Incompleto",
            "Documentación": documentation_state,
            "ARCA": area_state("arca"), "IIBB": area_state("iibb_legajo"),
            "Municipal": area_state("municipal"), "Laboral": area_state("laboral"),
            "Societario": area_state("societario"), "Bancos": area_state("bancos"),
            "Pagos": payment_state, "Riesgos": risk_level,
        }
        return {
            "client": dict(client), "estado_legajo": state,
            "tipo_cliente": client_type, "estado_cliente": client_state,
            "servicio_contratado": service, "actividad_principal": activity,
            "responsable_interno": responsible, "ultimo_control": last_control,
            "ultimo_contacto": last_contact, "estado_documentacion": documentation_state,
            "estado_pagos": payment_state,
            "pagos_pendientes": len(pending_payments), "pagos_vencidos": len(overdue_payments),
            "total_facturado": round(sum(float(r["importe"] or 0) for r in all_payments), 2),
            "total_cobrado": round(sum(float(r["importe"] or 0) - float(r["saldo"] or 0) for r in all_payments), 2),
            "ultimo_pago_recibido": max(payment_dates, default="—"), "proximo_pago_vencer": next_payment_due,
            "total_pendiente": round(sum(float(r["saldo"] or 0) for r in pending_payments), 2),
            "documentacion_pendiente": len(pending_docs), "tareas_pendientes": int(tasks["n"] or 0) + len(ledger_tasks),
            "tareas_vencidas": int(tasks["vencidas"] or 0) + len(overdue_ledger_tasks),
            "obligaciones_pendientes": len(obligations), "obligaciones_vencidas": len(overdue_obligations),
            "proximo_vencimiento": min([value for value in (due["fecha"] if due and due["fecha"] else None, generic_due) if value], default="—"),
            "riesgo_general": risk_level, "observacion_ejecutiva": dict(client).get("observaciones", ""),
            "estados_area": area_states,
            "ultima_actualizacion": max((r["actualizado_en"] for r in records), default=dict(client).get("actualizado_en", "")),
        }

    def master_index(self, search: str = "") -> list[dict]:
        conditions = "WHERE c.nombre_razon_social LIKE ? OR c.cuit_cuil LIKE ?" if search.strip() else ""
        params = (f"%{search.strip()}%",) * 2 if search.strip() else ()
        clients = self.database.query(f"SELECT c.id FROM clientes c {conditions} ORDER BY c.nombre_razon_social", params)
        return [self.summary(int(row["id"])) for row in clients]
