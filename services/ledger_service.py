from __future__ import annotations

import json
import re
from datetime import date, timedelta

from database import Database
from utils.formatters import normalize_date, normalize_period
from utils.validators import positive_number, required


def field(key: str, label: str, options: tuple[str, ...] = ()) -> tuple:
    return key, label, options


DOCUMENT_OPTIONS = (
    "DNI frente y dorso", "Constancia de CUIT", "Constancia de CBU", "Comprobante de domicilio",
    "Email tributario", "Teléfono actualizado", "Clave fiscal / acceso autorizado", "Poder o autorización",
    "Constancia de inscripción ARCA", "Constancia de inscripción IIBB", "Constancia municipal",
    "Últimas DDJJ presentadas", "Últimos pagos", "Deuda ARCA", "Deuda IIBB", "Planes de pago",
    "Intimaciones", "Fiscalizaciones", "Domicilio Fiscal Electrónico revisado", "Actividades declaradas",
    "Puntos de venta", "Comprobantes habilitados", "Facturas emitidas", "Facturas recibidas",
    "Notas de crédito emitidas", "Notas de crédito recibidas", "Notas de débito", "Recibos", "Remitos",
    "Presupuestos", "Comprobantes anulados", "Control de correlatividad", "Extractos bancarios",
    "Mercado Pago", "Mercado Libre", "Tarjetas de crédito", "Tarjetas de débito", "Billeteras virtuales",
    "Comprobantes de transferencias", "Movimientos de cuentas de terceros", "Resúmenes de préstamos",
    "Resúmenes de tarjetas", "Facturas de compra", "Listado de proveedores", "Contratos con proveedores",
    "Órdenes de compra", "Comprobantes de pago", "Deudas con proveedores", "Listado de clientes",
    "Contratos con clientes", "Comprobantes de cobro", "Reportes de marketplaces", "Reportes de Mercado Libre",
    "Reportes de Mercado Pago", "Reportes de Tienda Nube", "Reportes de otras plataformas",
    "Altas tempranas", "Bajas de empleados", "Recibos de sueldo", "F.931", "ART",
    "Seguro de vida obligatorio", "Convenio colectivo", "Sindicato", "Libro de sueldos digital",
    "Datos de empleados", "Casas particulares", "Bienes registrables", "Inmuebles", "Automotores", "Dólares",
    "Inversiones", "Criptomonedas", "Plazos fijos", "Cuentas bancarias", "Deudas", "Préstamos",
    "Jubilaciones", "Alquileres", "Deducciones personales", "Cargas de familia", "Habilitación municipal",
    "Contrato de alquiler", "Escritura o autorización de uso", "Plano", "Certificado de bomberos",
    "Bromatología", "Manipulación de alimentos", "Libro de inspecciones", "Tasas municipales",
    "Seguridad e higiene", "Publicidad y propaganda", "Contratos relevantes", "Papeles de trabajo anteriores",
    "Datos del contador anterior", "Informes anteriores", "Notas presentadas", "Respuestas de organismos", "Otro",
)

ARCA_COMMON_FIELDS = (
    field("arca_cuit", "CUIT"), field("estado_cuit", "Estado CUIT", ("Activo", "Limitado", "Inactivo", "Suspendido", "Baja", "A revisar")),
    field("fecha_inscripcion_arca", "Fecha de inscripción ARCA"), field("fecha_inicio_actividad", "Fecha de inicio de actividad"),
    field("actividad_principal_arca", "Actividad principal"), field("codigo_actividad_arca", "Código de actividad"),
    field("actividades_secundarias_arca", "Actividades secundarias"), field("domicilio_fiscal_electronico", "Domicilio fiscal electrónico", ("Adherido", "No adherido", "A revisar")),
    field("domicilio_fiscal_arca", "Domicilio fiscal"), field("dependencia", "Dependencia"),
    field("email_fiscal", "Email fiscal"), field("telefono_fiscal", "Teléfono"), field("arca_observaciones", "Observaciones"),
)

ARCA_MONOTRIBUTO_FIELDS = (
    field("mono_estado_arca", "Estado del monotributo", ("Activo", "Baja", "Excluido", "Suspendido", "A revisar")),
    field("mono_fecha_alta_arca", "Fecha de alta en monotributo"), field("mono_categoria_arca", "Categoría actual", tuple("ABCDEFGHIJK")),
    field("mono_ultima_recategorizacion", "Fecha de última recategorización"), field("mono_actividad_arca", "Actividad monotributista"),
    field("mono_tipo_actividad_arca", "Tipo de actividad"), field("mono_obra_social_arca", "Obra social"),
    field("mono_aportes_arca", "Aportes jubilatorios"), field("mono_adherentes_arca", "Adherentes obra social"),
    field("mono_deuda_arca", "Deuda monotributo"), field("mono_meses_impagos", "Meses impagos"),
    field("mono_baja_automatica", "Baja automática", ("Sí", "No", "A revisar")), field("mono_exclusion", "Exclusión", ("Sí", "No", "A revisar")),
    field("mono_motivo_exclusion", "Motivo de exclusión"), field("mono_fecha_exclusion", "Fecha de exclusión"),
    field("mono_riesgo_exclusion", "Riesgo de exclusión", ("Bajo", "Medio", "Alto", "Urgente", "A revisar")),
    field("mono_ingresos_12", "Ingresos últimos 12 meses"), field("mono_superficie", "Superficie afectada"),
    field("mono_energia", "Energía eléctrica"), field("mono_alquileres", "Alquileres devengados"),
    field("mono_precio_unitario", "Precio unitario máximo"), field("mono_categoria_sugerida", "Categoría sugerida"),
    field("mono_diferencia_limite", "Diferencia hasta límite"), field("mono_porcentaje_limite", "Porcentaje usado del límite"),
    field("mono_control_facturacion", "Facturación emitida", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_control_significativas", "Facturas significativas", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_control_usd", "Facturas en USD", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_notas_credito", "Notas de crédito", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_correlatividad", "Control de correlatividad", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_ventas_cliente", "Ventas por cliente", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_compras", "Compras", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_proveedores", "Proveedores principales", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_control_mercado_libre", "Actividad en Mercado Libre", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_control_mercado_pago", "Actividad en Mercado Pago", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_riesgos_detectados", "Riesgos detectados", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("mono_observaciones_arca", "Observaciones Monotributo"),
)

ARCA_RESPONSABLE_FIELDS = (
    field("ri_alta_iva_arca", "Alta en IVA", ("Sí", "No", "En trámite", "Baja", "A revisar")), field("ri_fecha_alta_iva_arca", "Fecha de alta en IVA"),
    field("ri_estado_iva_arca", "Estado IVA", ("OK", "Pendiente", "Revisar", "Urgente", "No corresponde")),
    field("ri_libro_iva_arca", "Libro IVA Digital", ("Activo", "Presentado", "Pendiente", "Vencido", "A revisar")),
    field("ri_iva_presentado_arca", "Último período presentado"), field("ri_iva_controlado_arca", "Último período controlado"),
    field("ri_debito_arca", "Débito fiscal"), field("ri_credito_arca", "Crédito fiscal"), field("ri_saldo_tecnico_arca", "Saldo técnico"),
    field("ri_saldo_libre_arca", "Saldo de libre disponibilidad"), field("ri_retenciones_iva_arca", "Retenciones IVA"), field("ri_percepciones_iva_arca", "Percepciones IVA"),
    field("ri_observaciones_iva_arca", "Observaciones IVA"),
    field("ri_alta_ganancias_arca", "Alta en Ganancias", ("Sí", "No", "En trámite", "Baja", "A revisar")), field("ri_fecha_ganancias_arca", "Fecha de alta en Ganancias"),
    field("ri_tipo_ganancias_arca", "Tipo de Ganancias"), field("ri_ultima_ddjj_arca", "Última DDJJ presentada"), field("ri_anticipos_arca", "Anticipos"),
    field("ri_ddjj_ganancias_arca", "DDJJ presentada", ("Presentada", "Pendiente", "Vencida", "A revisar", "No corresponde")),
    field("ri_deducciones_arca", "Deducciones"), field("ri_cargas_familia_arca", "Cargas de familia"),
    field("ri_observaciones_ganancias_arca", "Observaciones Ganancias"),
    field("ri_alta_autonomos_arca", "Alta en Autónomos", ("Sí", "No", "En trámite", "Baja", "A revisar")), field("ri_fecha_autonomos_arca", "Fecha de alta en Autónomos"),
    field("ri_categoria_autonomos_arca", "Categoría Autónomos"), field("ri_tabla_autonomos_arca", "Tabla Autónomos"), field("ri_condicion_autonomos_arca", "Condición Autónomos"),
    field("ri_dependencia_autonomos_arca", "Relación de dependencia simultánea"), field("ri_pluriactividad_arca", "Reducción por pluriactividad"),
    field("ri_ultimo_autonomos_arca", "Último período pagado"), field("ri_deuda_autonomos_arca", "Deuda Autónomos"),
    field("ri_observaciones_autonomos_arca", "Observaciones Autónomos"),
    field("ri_comprobantes_arca", "Comprobantes habilitados"), field("ri_factura_a_arca", "Factura A autorizada"), field("ri_factura_m_arca", "Factura M"), field("ri_factura_e_arca", "Factura E"),
    field("ri_puntos_venta_arca", "Puntos de venta"), field("ri_sistema_facturacion_arca", "Sistema de facturación"), field("ri_correlatividad_arca", "Control de correlatividad"),
    field("ri_comprobantes_usd_arca", "Comprobantes en USD"), field("ri_observaciones_facturacion_arca", "Observaciones Facturación"),
    field("ri_ddjj_pendientes_arca", "DDJJ pendientes"), field("ri_deuda_arca", "Deuda ARCA"), field("ri_planes_arca", "Planes de pago"),
    field("ri_presentaciones_digitales_arca", "Presentaciones digitales"), field("ri_fiscalizaciones_arca", "Fiscalizaciones"), field("ri_intimaciones_arca", "Intimaciones"), field("ri_embargos_arca", "Embargos"),
    field("ri_notificaciones_arca", "Notificaciones DFE"), field("ri_mis_comprobantes_arca", "Mis Comprobantes"), field("ri_nuestra_parte_arca", "Nuestra Parte"), field("ri_riesgo_arca", "Riesgo fiscal", ("Bajo", "Medio", "Alto", "Urgente", "Sin evaluar")),
    field("ri_observaciones_controles_arca", "Observaciones Controles"),
    field("ri_observaciones_arca", "Observaciones Responsable Inscripto"),
)

ARCA_GANANCIAS_FIELDS = (
    field("gan_tipo_contribuyente_arca", "Tipo de contribuyente", ("Ganancias Personas Humanas", "Ganancias Sociedades", "Otro", "A revisar", "No corresponde")), field("gan_fecha_alta_arca", "Fecha de alta"),
    field("gan_ultima_ddjj_arca", "Última DDJJ presentada"), field("gan_anio_fiscal_arca", "Año fiscal"), field("gan_anticipos_arca", "Anticipos"),
    field("gan_deducciones_arca", "Deducciones personales"), field("gan_cargas_arca", "Cargas de familia"), field("gan_sueldos_arca", "Sueldos"),
    field("gan_jubilaciones_arca", "Jubilaciones"), field("gan_alquileres_arca", "Alquileres"), field("gan_intereses_arca", "Intereses"),
    field("gan_inversiones_arca", "Inversiones"), field("gan_bienes_arca", "Bienes"), field("gan_deudas_arca", "Deudas"),
    field("gan_resultado_arca", "Resultado estimado"), field("gan_papeles_arca", "Papeles de trabajo"), field("gan_estado_arca", "Estado", ("Presentado", "Pendiente", "Vencido", "A revisar", "No corresponde")), field("gan_observaciones_arca", "Observaciones Ganancias"),
)

ARCA_BIENES_FIELDS = (
    field("bp_inscripto_arca", "Inscripto en Bienes Personales"), field("bp_fecha_alta_arca", "Fecha de alta"), field("bp_ultima_ddjj_arca", "Última DDJJ presentada"),
    field("bp_anio_fiscal_arca", "Año fiscal"), field("bp_inmuebles_arca", "Bienes inmuebles"), field("bp_automotores_arca", "Automotores"),
    field("bp_cuentas_arca", "Cuentas bancarias"), field("bp_dolares_arca", "Dólares"), field("bp_inversiones_arca", "Inversiones"),
    field("bp_cripto_arca", "Criptomonedas"), field("bp_exterior_arca", "Bienes del exterior"), field("bp_deudas_arca", "Deudas"),
    field("bp_minimo_arca", "Mínimo no imponible"), field("bp_casa_arca", "Casa habitación"), field("bp_resultado_arca", "Resultado estimado"),
    field("bp_papeles_arca", "Papeles de trabajo"), field("bp_estado_arca", "Estado", ("Presentado", "Pendiente", "Vencido", "A revisar", "No corresponde")), field("bp_observaciones_arca", "Observaciones Bienes Personales"),
)


class LedgerService:
    """Legajo extensible: todas las áreas usan el mismo CRUD y trazabilidad."""

    # Las secciones retiradas pueden seguir existiendo en bases antiguas, pero no
    # forman parte del flujo activo ni de las exportaciones del legajo.
    VISIBLE_SECTIONS = (
        "servicio_presupuesto",
        "pagos",
        "relevamiento",
        "documentacion",
        "arca",
        "iibb_legajo",
        "municipal",
        "laboral",
        "bancos",
        "riesgos",
        "eventos",
        "vencimientos_legajo",
    )

    SECTIONS = {
        "datos_complementarios": ("Datos del Cliente", (
            field("tipo_cliente", "Tipo de cliente", ("Persona humana", "Persona jurídica", "Sucesión indivisa", "Otro")),
            field("estado_cliente", "Estado del cliente", ("Activo", "En alta", "En regularización", "Pausado", "Baja", "Ex cliente", "Solo consulta", "Pendiente de documentación")),
            field("domicilio_real", "Domicilio real"), field("domicilio_fiscal", "Domicilio fiscal"), field("domicilio_explotacion", "Domicilio de explotación"),
            field("telefono", "Teléfono"), field("whatsapp", "WhatsApp"), field("email", "Email"),
            field("contacto_principal", "Contacto principal"), field("contacto_documentacion", "Contacto para documentación"),
            field("contacto_pagos", "Contacto para pagos"),
            field("observaciones", "Observaciones"),
        )),
        "servicio_presupuesto": ("Servicio y Presupuesto", (
            field("numero_presupuesto", "Número de presupuesto"),
            field("descripcion", "Descripción"), field("periodo", "Período MM/AAAA"),
            field("alta_estudio", "Alta inicial en el estudio"),
            field("tipo_servicio", "Tipo de servicio", ("Abono mensual", "Alta inicial", "Liquidación impositiva", "Monotributo", "IVA", "Ganancias", "Autónomos", "IIBB local", "Convenio Multilateral", "Sueldos", "Casas particulares", "Societario", "Habilitación municipal", "Bienes personales", "Facturación", "Conciliaciones", "Presentaciones anuales", "Trámite puntual", "Asesoramiento general", "Otro")),
            field("alcance", "Alcance del servicio"), field("exclusiones", "Exclusiones"), field("documentacion_requerida", "Documentación que debe enviar"),
            field("periodicidad", "Periodicidad", ("Mensual", "Bimestral", "Trimestral", "Semestral", "Anual", "Por operación", "A requerimiento", "No corresponde")),
            field("fecha_inicio", "Fecha de inicio"), field("estado_servicio", "Estado", ("Activo", "En preparación", "Pendiente de documentación", "Suspendido", "Finalizado", "Cancelado", "No corresponde")),
            field("fecha_presupuesto", "Fecha del presupuesto"), field("fecha_vencimiento", "Fecha de vencimiento del presupuesto / pago"), field("concepto", "Concepto presupuestado", ("Alta inicial", "Abono mensual", "Liquidación mensual", "Presentación anual", "Regularización fiscal", "Regularización impositiva", "Fiscalización", "Moratoria / plan de pago", "Alta ARCA", "Alta IIBB", "Alta municipal", "Alta empleador", "Sueldos", "Casas particulares", "Societario", "Certificación", "Informe", "Consulta", "Otro")), field("tipo_honorario", "Tipo de honorario", ("Fijo mensual", "Fijo por trámite", "Por hora", "Por presentación", "Por empleado", "Por impuesto", "Por paquete", "Bonificado", "Sin cargo", "Otro")),
            field("valor_presupuestado", "Valor presupuestado"), field("moneda", "Moneda", ("ARS", "USD", "Otro")),
            field("periodicidad_presupuesto", "Periodicidad del presupuesto", ("Único pago", "Mensual", "Bimestral", "Trimestral", "Semestral", "Anual", "Por evento", "Otro")),
            field("saldo_pendiente", "Saldo"),
            field("estado_presupuesto", "Estado presupuesto", ("Borrador", "Enviado", "Aceptado", "Rechazado", "Vencido", "Reemplazado", "Cancelado", "Cobrado", "Cobro parcial", "Pendiente")), field("fecha_aceptacion", "Fecha de aceptación"), field("medio_aceptacion", "Medio de aceptación", ("WhatsApp", "Email", "Firma presencial", "Firma digital", "Verbal", "Otro")), field("condiciones_presupuesto", "Condiciones del presupuesto"), field("observaciones", "Observaciones"),
        )),
        "pagos": ("Honorarios", (
            field("numero_presupuesto", "Número de presupuesto"), field("fecha_emision", "Fecha de emisión"), field("periodo", "Período MM/AAAA"),
            field("concepto", "Concepto", ("Abono mensual", "Alta inicial", "Liquidación impositiva", "Monotributo", "IVA", "Ganancias", "IIBB", "Convenio Multilateral", "Autónomos", "Sueldos", "Casas particulares", "Presentación anual", "Bienes personales", "Regularización", "Plan de pagos", "Trámite puntual", "Consulta", "Otro")), field("importe_facturado", "Importe facturado"),
            field("importe_cobrado", "Importe cobrado"), field("saldo_pendiente", "Saldo pendiente"),
            field("moneda", "Moneda", ("ARS", "USD", "Otro")), field("estado_pago", "Estado de cobro", ("Pendiente", "Cobrado", "Cobro parcial", "Vencido", "Bonificado", "Anulado", "Sin presupuesto asociado", "No corresponde")),
            field("fecha_vencimiento", "Fecha de vencimiento"), field("fecha_cobro", "Fecha de cobro"),
            field("medio_pago", "Medio de cobro", ("Efectivo", "Transferencia", "Mercado Pago", "Débito", "Crédito", "Cheque", "Cuenta DNI", "MODO", "Otro")),
            field("comprobante_emitido", "Comprobante emitido", ("Sí", "No", "Pendiente", "No corresponde")), field("tipo_comprobante", "Tipo de comprobante", ("Factura A", "Factura B", "Factura C", "Recibo", "Nota de crédito", "Comprobante interno", "No corresponde")), field("numero_comprobante", "Número de comprobante"), field("observaciones", "Observaciones"),
        )),
        "relevamiento": ("Relevamiento", (
            field("actividad_principal", "Actividad principal real"), field("actividad_secundaria", "Actividad secundaria real"), field("actividades_declaradas", "Actividades declaradas"), field("fecha_inicio_real", "Fecha real de inicio"), field("fecha_inicio_fiscal", "Fecha fiscal de inicio"),
            field("forma_trabajo", "Forma de trabajo", ("Local físico", "Online", "Domicilio particular", "Depósito", "Fábrica", "Oficina", "Servicios a domicilio", "Marketplace", "Mixta", "Otro")),
            field("lugar_actividad", "Lugar donde desarrolla la actividad"), field("trabaja_online", "Trabaja online", ("Sí", "No", "Parcialmente", "No corresponde")), field("trabaja_local", "Trabaja en local", ("Sí", "No", "En trámite", "No corresponde")), field("trabaja_domicilio", "Trabaja desde domicilio", ("Sí", "No", "Parcialmente", "No corresponde")), field("posee_deposito", "Posee depósito", ("Sí", "No", "Tercero", "No corresponde")),
            field("presta_servicios", "Presta servicios", ("Sí", "No", "Mixto")), field("vende_bienes", "Vende bienes", ("Sí", "No", "Mixto")), field("fabrica", "Fabrica", ("Sí", "No", "Terceriza", "No corresponde")), field("revende", "Revende", ("Sí", "No", "No corresponde")), field("importa", "Importa", ("Sí", "No", "Planea hacerlo", "No corresponde")), field("exporta", "Exporta", ("Sí", "No", "Planea hacerlo", "No corresponde")),
            field("canales_venta", "Canales de venta (local, Instagram, WhatsApp, web, marketplaces, mayorista/minorista, transferencia/efectivo)"), field("tipo_clientes", "Tipo de clientes", ("Consumidor final", "Monotributistas", "Responsables inscriptos", "Empresas", "Estado", "Exterior", "Mixto", "Otro")), field("clientes_principales", "Clientes principales"), field("clientes_vinculados", "Clientes vinculados", ("Sí", "No", "A revisar", "No corresponde")), field("ventas_familiares", "Ventas a familiares", ("Sí", "No", "A revisar", "No corresponde")), field("ventas_empresas", "Ventas a empresas", ("Sí", "No", "A revisar")), field("ventas_consumidor_final", "Ventas a consumidor final", ("Sí", "No", "Principalmente", "Parcialmente")), field("ventas_estado", "Ventas al Estado", ("Sí", "No", "Planea hacerlo")), field("concentracion_clientes", "Concentración de clientes", ("Baja", "Media", "Alta", "A revisar")), field("forma_cobro", "Forma habitual de cobro", ("Efectivo", "Transferencia", "Mercado Pago", "Tarjeta", "Cheque", "Dólares", "Mixto", "Otro")), field("cuentas_propias", "Uso de cuentas propias", ("Sí", "No", "Parcialmente", "A revisar")), field("cuentas_terceros", "Uso de cuentas de terceros", ("No", "Sí", "Ocasional", "Frecuente", "A regularizar")), field("cobros_extranjera", "Cobros en moneda extranjera", ("Sí", "No", "Ocasional", "A revisar")),
            field("proveedores_principales", "Proveedores principales"), field("tipo_compras", "Tipo de compras", ("Mercadería", "Insumos", "Servicios", "Alquileres", "Honorarios", "Publicidad", "Logística", "Equipamiento", "Mixto", "Otro")), field("compras_factura", "Compras con factura", ("Todas", "La mayoría", "Algunas", "Ninguna", "A revisar")), field("compras_sin_factura", "Compras sin factura", ("No", "Sí", "Ocasional", "Frecuente", "A regularizar")), field("compras_exterior", "Compras al exterior", ("Sí", "No", "Planea hacerlo")), field("compras_efectivo", "Compras en efectivo", ("Sí", "No", "Ocasional", "Frecuente")), field("compras_extranjera", "Compras en moneda extranjera", ("Sí", "No", "Ocasional", "A revisar")), field("frecuencia_compras", "Frecuencia de compras", ("Diaria", "Semanal", "Quincenal", "Mensual", "Esporádica", "A demanda")), field("proveedores_vinculados", "Proveedores vinculados", ("Sí", "No", "A revisar", "No corresponde")), field("remitos", "Existencia de remitos", ("Sí", "No", "Parcialmente", "No corresponde")), field("ordenes_compra", "Existencia de órdenes de compra", ("Sí", "No", "Parcialmente", "No corresponde")), field("comprobantes_internos", "Existencia de comprobantes internos", ("Sí", "No", "Parcialmente", "No corresponde")),
            field("codigo_actividad", "Código de actividad"), field("rubro", "Rubro"),
            field("temporada_alta", "Temporada alta"), field("temporada_baja", "Temporada baja"),
            field("canales_venta_detalle", "Canales de venta", ("multi", "Local físico", "Instagram", "WhatsApp", "Página web", "Mercado Libre", "Mercado Pago", "Tienda Nube", "Pedidos Ya", "Rappi", "Mayorista", "Minorista", "Distribuidores", "Ventas por transferencia", "Ventas en efectivo", "Otros marketplaces", "Otro")),
            field("ventas_exterior", "Ventas al exterior", ("Sí", "No", "Planea hacerlo", "A revisar")),
            field("tiene_empleados", "Tiene empleados", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("familiares_colaboran", "Familiares que colaboran", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("profesionales_contratados", "Profesionales contratados", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("terceros_contratados", "Terceros contratados", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("cadetes_repartidores", "Cadetes / repartidores", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("vehiculos_afectados", "Vehículos afectados", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("maquinaria", "Maquinaria", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("herramientas", "Herramientas", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("equipos", "Equipos", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("inmuebles_afectados", "Inmuebles afectados", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("locales", "Locales", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("depositos", "Depósitos", ("Sí", "No", "Parcial", "A revisar", "No corresponde")),
            field("horarios_atencion", "Horarios de atención"),
            field("operaciones_corto", "Operaciones previstas a corto plazo"), field("operaciones_mediano", "Operaciones previstas a mediano plazo"), field("operaciones_largo", "Operaciones previstas a largo plazo"),
            field("inversiones_previstas", "Inversiones previstas"), field("origen_fondos", "Origen de fondos"), field("financiacion_prevista", "Financiación prevista"),
            field("posible_empleados", "Posible contratación de empleados", ("Sí", "No", "A revisar", "No corresponde")),
            field("posible_cambio_regimen", "Posible cambio de régimen", ("Sí", "No", "A revisar", "No corresponde")),
            field("posible_local", "Posible apertura de local", ("Sí", "No", "A revisar", "No corresponde")),
            field("posible_provincias", "Posible venta en otras provincias", ("Sí", "No", "A revisar", "No corresponde")),
            field("posible_exterior", "Posible venta al exterior", ("Sí", "No", "A revisar", "No corresponde")),
            field("riesgos_detectados", "Riesgos detectados", ("multi", "Mezcla gastos personales con actividad", "Usa cuentas personales para el negocio", "Usa cuentas de terceros", "Tiene ventas sin factura", "Tiene compras sin factura", "Movimientos bancarios superiores a facturación", "Gastos altos con baja facturación", "Diferencias entre ARCA, bancos, Mercado Pago o Mercado Libre", "Deudas fiscales", "Intimaciones", "Fiscalizaciones", "Embargos", "Planes caídos", "Actividad no declarada", "Jurisdicciones no inscriptas", "Otro")),
            field("observaciones", "Observaciones"),
        )),
        "documentacion": ("Documentación", (
            field("tipo_registro", "Tipo de registro", ("Documento", "Acceso")),
            field("documento", "Documento", DOCUMENT_OPTIONS), field("estado", "Estado", ("Solicitado", "Recibido", "Pendiente", "Incompleto", "Vencido", "No corresponde", "Requiere actualización")),
            field("fecha_solicitud", "Fecha solicitud"), field("fecha_recepcion", "Fecha recepción"), field("obligatorio", "Obligatorio", ("Sí", "No", "Según caso", "No corresponde")), field("archivo_link", "Link o archivo"),
            field("plataforma", "Organismo / plataforma", ("ARCA", "ARBA", "AGIP", "COMARB", "Municipio", "Banco", "Mercado Pago", "Mercado Libre", "Sistema de facturación", "Sistema de gestión", "Email", "Otro")), field("usuario_acceso", "Usuario"), field("contrasena_referencia", "Contraseña / referencia segura"), field("estado_acceso", "Estado de acceso", ("Disponible", "Pendiente", "Incorrecto", "Bloqueado", "No corresponde", "A actualizar")), field("nivel_acceso", "Nivel de acceso"), field("fecha_control", "Fecha de control"), field("observaciones", "Observaciones"),
        )),
        "arca": ("ARCA", ARCA_COMMON_FIELDS),
        "iibb_legajo": ("IIBB", (
            field("jurisdiccion", "Jurisdicción", ("Buenos Aires", "CABA", "Catamarca", "Chaco", "Chubut", "Córdoba", "Corrientes", "Entre Ríos", "Formosa", "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones", "Neuquén", "Río Negro", "Salta", "San Juan", "San Luis", "Santa Cruz", "Santa Fe", "Santiago del Estero", "Tierra del Fuego", "Tucumán", "Otra")), field("regimen", "Régimen", ("Local", "Simplificado", "General", "Convenio Multilateral", "Exento", "No inscripto", "A revisar", "No corresponde")), field("actividad", "Actividad"), field("alicuota", "Alícuota"), field("estado", "Estado", ("Activo", "Baja", "En alta", "En regularización", "No inscripto", "No corresponde", "A revisar")), field("riesgo_fiscal", "Riesgo fiscal", ("Bajo", "Medio", "Alto", "Sin evaluar", "No corresponde")), field("estado_cm", "Estado Convenio Multilateral", ("Activo", "Pendiente de alta", "Baja", "En regularización", "No corresponde", "A revisar")), field("estado_control", "Estado del control", ("OK", "Revisar", "Urgente", "Pendiente", "No corresponde")), field("deuda", "Deuda", ("Sin deuda detectada", "Con deuda", "En plan", "A revisar", "No corresponde")), field("padrones", "Padrones", ("Controlado", "Pendiente", "A revisar", "No corresponde")), field("ultimo_control", "Último control"), field("observaciones", "Observaciones"),
        )),
        "municipal": ("Municipal", (
            field("municipio", "Municipio"), field("habilitacion", "Habilitación", ("Sí", "No", "En trámite", "No corresponde", "A revisar")), field("estado_tramite", "Estado del trámite", ("Vigente", "En trámite", "Pendiente de documentación", "Observado", "Vencido", "Baja", "No corresponde")), field("tramite", "Tasa municipal", ("Seguridad e Higiene", "Publicidad y propaganda", "Habilitación", "Inspección", "Bromatología", "Otra", "No corresponde")), field("numero_cuenta", "Número de cuenta"), field("deuda", "Deuda", ("Sin deuda detectada", "Con deuda", "En plan", "A revisar", "No corresponde")), field("estado", "Control", ("OK", "Revisar", "Urgente", "Pendiente", "No corresponde")), field("ultimo_control", "Último control"), field("vencimiento", "Vencimiento"), field("observaciones", "Observaciones"),
        )),
        "laboral": ("Laboral", (
            field("empleador", "Empleador", ("Sí", "No", "En alta", "No corresponde", "A revisar")), field("condicion", "Estado laboral", ("Sin empleados", "Con empleados activos", "Casas particulares", "En regularización", "Baja como empleador", "A revisar", "No corresponde")), field("empleados", "Cantidad empleados"), field("convenio", "Convenio colectivo"), field("art", "ART", ("Vigente", "Pendiente", "No tiene", "No corresponde", "A revisar")), field("libro_sueldos", "Libro de sueldos digital", ("Activo", "Pendiente", "No corresponde", "A revisar")), field("f931", "F.931", ("Presentado", "Pendiente", "Vencido", "No corresponde", "A revisar")), field("cargas_sociales", "Cargas sociales", ("Al día", "Con deuda", "En plan", "A revisar", "No corresponde")), field("estado", "Estado / control"), field("ultimo_control", "Último control"), field("observaciones", "Observaciones"),
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
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def section_fields(self, client_id: int, section: str) -> tuple:
        if section != "arca":
            return self.SECTIONS[section][1]
        row = self.database.query_one(
            """SELECT COALESCE(d.regimen_principal,'') regimen,
                      COALESCE(d.condicion_iva,'') iva
               FROM clientes c LEFT JOIN datos_fiscales_cliente d ON d.cliente_id=c.id
               WHERE c.id=?""",
            (client_id,),
        )
        text = " ".join((str(row["regimen"] or ""), str(row["iva"] or ""))).casefold() if row else ""
        obligations = " ".join(
            str(item["codigo"] or "").casefold()
            for item in self.database.query(
                """SELECT o.codigo FROM cliente_obligaciones co
                   JOIN obligaciones_fiscales o ON o.id=co.obligacion_id
                   WHERE co.cliente_id=? AND LOWER(co.estado)='activa'""",
                (client_id,),
            )
        )
        manual = {
            str(item["campo"]): str(item["valor"] or "").casefold()
            for item in self.database.query(
                """SELECT campo,valor FROM cliente_legajo_campos
                   WHERE cliente_id=? AND seccion='responsable_inscripto'""",
                (client_id,),
            )
        }
        fields = list(ARCA_COMMON_FIELDS)
        if "mono" in text:
            fields.extend(ARCA_MONOTRIBUTO_FIELDS)
        if "responsable" in text or "iva" in text or "iva" in obligations or manual.get("ri_inscripto") in ("sí", "si", "en trámite"):
            fields.extend(ARCA_RESPONSABLE_FIELDS)
        if "ganancia" in text or "ganancias" in obligations or manual.get("gan_inscripto") in ("sí", "si", "en trámite"):
            fields.extend(ARCA_GANANCIAS_FIELDS)
        if "bienes" in text or "bienes" in obligations:
            fields.extend(ARCA_BIENES_FIELDS)
        return tuple(fields)

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
        budget_number = str(data.get("numero_presupuesto") or "").strip()
        budget_number = "Sin presupuesto asociado" if budget_number.casefold() == "sin presupuesto asociado" else budget_number.upper()
        if section == "servicio_presupuesto":
            if not budget_number:
                used = {
                    int(match.group(1))
                    for row in self.database.query(
                        """SELECT numero_presupuesto FROM cliente_legajo_registros
                           WHERE numero_presupuesto<>'' AND seccion='servicio_presupuesto'"""
                    )
                    if (match := re.fullmatch(r"EAP-(\d+)", str(row["numero_presupuesto"] or "").upper()))
                }
                number = 10
                while number in used:
                    number += 1
                budget_number = f"EAP-{number:04d}"
            if not re.fullmatch(r"EAP-\d{4,}", budget_number):
                raise ValueError("El número de presupuesto debe tener formato EAP-0010.")
            duplicate = self.database.query_one(
                """SELECT id FROM cliente_legajo_registros
                   WHERE seccion='servicio_presupuesto'
                   AND numero_presupuesto=? AND id<>?""",
                (budget_number, int(record_id or 0)),
            )
            if duplicate:
                raise ValueError("Ya existe otro presupuesto con ese número.")
            data["numero_presupuesto"] = budget_number
            if not data.get("saldo_pendiente"):
                data["saldo_pendiente"] = data.get("valor_presupuestado") or "0"
        elif section == "pagos":
            if not budget_number:
                budget_number = "Sin presupuesto asociado"
            if budget_number.casefold() != "sin presupuesto asociado":
                budget = self.database.query_one(
                    """SELECT id FROM cliente_legajo_registros
                       WHERE cliente_id=? AND seccion='servicio_presupuesto'
                       AND numero_presupuesto=?""",
                    (client_id, budget_number),
                )
                if not budget:
                    raise ValueError("El presupuesto seleccionado no pertenece al cliente.")
            data["numero_presupuesto"] = budget_number
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
        saldo = positive_number(data.get("saldo_pendiente") or 0, "Saldo", True)
        period = str(data.get("periodo") or "").strip().replace("/", "-")
        if period and len(period) == 7 and period[2] == "-":
            period = f"{period[3:]}-{period[:2]}"
        if period:
            period = normalize_period(period)
            data["periodo"] = period
        date_value = next((data.get(k) for k in ("fecha", "fecha_emision", "fecha_solicitud") if data.get(k)), None)
        due = next((data.get(k) for k in ("fecha_vencimiento", "vencimiento") if data.get(k)), None)
        for key in list(data):
            if "fecha" in key and data[key]:
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
                    """UPDATE cliente_legajo_registros SET fecha=?,periodo=?,descripcion=?,estado=?,importe=?,saldo=?,vencimiento=?,datos_json=?,responsable=?,numero_presupuesto=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=? AND cliente_id=?""",
                    (date_value, period, description, status, amount, saldo, due, json.dumps(data, ensure_ascii=False), responsible, budget_number if section in ("servicio_presupuesto", "pagos") else "", record_id, client_id),
                )
                result_id = record_id
                change = "Modificación"
            else:
                cursor = connection.execute(
                    """INSERT INTO cliente_legajo_registros(cliente_id,seccion,fecha,periodo,descripcion,estado,importe,saldo,vencimiento,datos_json,responsable,numero_presupuesto) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (client_id, section, date_value, period, description, status, amount, saldo, due, json.dumps(data, ensure_ascii=False), responsible, budget_number if section in ("servicio_presupuesto", "pagos") else ""),
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
        ledger_tasks = [r for r in records if r["seccion"] == "eventos" and r["estado"].casefold() not in ("finalizado", "cancelado", "no corresponde")]
        overdue_ledger_tasks = [r for r in ledger_tasks if r["vencimiento"] and r["vencimiento"] < today]
        tasks = self.database.query_one("SELECT COUNT(*) n,SUM(CASE WHEN fecha_vencimiento<DATE('now') THEN 1 ELSE 0 END) vencidas FROM tareas WHERE cliente_id=? AND LOWER(estado) NOT IN ('finalizado','archivado','cobrado','cumplimentada','cancelada','no corresponde')", (client_id,))
        due = self.database.query_one("SELECT MIN(fecha_vencimiento) fecha FROM vencimientos WHERE cliente_id=? AND LOWER(estado) NOT IN ('pagado','cumplido','no corresponde') AND fecha_vencimiento BETWEEN ? AND ?", (client_id, today, soon))
        generic_due = min((r["vencimiento"] for r in records if r["seccion"] in self.VISIBLE_SECTIONS and r["vencimiento"] and r["estado"].casefold() not in ("pagado", "finalizado", "no corresponde")), default=None)
        completed_sections = len({r["seccion"] for r in records if r["seccion"] in self.VISIBLE_SECTIONS})
        state = "Completo" if completed_sections >= 8 and not pending_docs else "Incompleto"
        risk_values = [json.loads(r["datos_json"] or "{}").get("nivel", "") for r in risks]
        risk_level = "Alto" if any(value.casefold() in ("alto", "urgente") for value in risk_values) else ("Medio" if risks else "Bajo")
        service = latest_value("servicio_presupuesto", "tipo_servicio", "concepto", default="Sin definir")
        activity = latest_value("relevamiento", "actividad_principal", default=dict(client).get("actividad", ""))
        client_type = latest_value("datos_complementarios", "tipo_cliente", default=str(dict(client).get("tipo_persona_detalle") or dict(client).get("tipo_persona", "")).replace("_", " ").title())
        client_state = latest_value("datos_complementarios", "estado_cliente", default=str(dict(client).get("estado_detalle") or dict(client).get("estado", "")).title())
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
            "Bancos": area_state("bancos"),
            "Pagos": payment_state, "Riesgos": risk_level,
        }
        return {
            "client": dict(client), "estado_legajo": state,
            "tipo_cliente": client_type, "estado_cliente": client_state,
            "servicio_contratado": service, "actividad_principal": activity,
            "ultimo_control": last_control,
            "ultimo_contacto": last_contact, "estado_documentacion": documentation_state,
            "estado_pagos": payment_state,
            "pagos_pendientes": len(pending_payments), "pagos_vencidos": len(overdue_payments),
            "total_facturado": round(sum(float(r["importe"] or 0) for r in all_payments), 2),
            "total_cobrado": round(sum(float(r["importe"] or 0) - float(r["saldo"] or 0) for r in all_payments), 2),
            "ultimo_pago_recibido": max(payment_dates, default="—"), "proximo_pago_vencer": next_payment_due,
            "total_pendiente": round(sum(float(r["saldo"] or 0) for r in pending_payments), 2),
            "documentacion_pendiente": len(pending_docs), "tareas_pendientes": int(tasks["n"] or 0) + len(ledger_tasks),
            "tareas_vencidas": int(tasks["vencidas"] or 0) + len(overdue_ledger_tasks),
            "proximo_vencimiento": min([value for value in (due["fecha"] if due and due["fecha"] else None, generic_due) if value], default="—"),
            "riesgo_general": risk_level, "observacion_ejecutiva": dict(client).get("observaciones", ""),
            "estados_area": area_states,
        }

    def master_index(self, search: str = "") -> list[dict]:
        conditions = "WHERE c.nombre_razon_social LIKE ? OR c.cuit_cuil LIKE ?" if search.strip() else ""
        params = (f"%{search.strip()}%",) * 2 if search.strip() else ()
        clients = self.database.query(f"SELECT c.id FROM clientes c {conditions} ORDER BY c.nombre_razon_social", params)
        return [self.summary(int(row["id"])) for row in clients]
