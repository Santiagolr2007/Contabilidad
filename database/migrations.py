from __future__ import annotations

import json
import re
import sqlite3


CLIENT_COLUMNS = {
    "legajo": "TEXT DEFAULT ''",
    "codigo_actividad": "TEXT DEFAULT ''",
    "tipo_persona_detalle": "TEXT DEFAULT ''",
    "estado_detalle": "TEXT DEFAULT ''",
    "dni": "TEXT DEFAULT ''",
    "fecha_nacimiento": "TEXT",
    "nacionalidad": "TEXT DEFAULT ''",
    "estado_civil": "TEXT DEFAULT ''",
    "instagram": "TEXT DEFAULT ''",
    "rubro": "TEXT DEFAULT ''",
    "fecha_alta_estudio": "TEXT",
}

MONO_COLUMNS = {
    "actividad_fiscal": "TEXT DEFAULT ''",
    "codigo_actividad": "TEXT DEFAULT ''",
    "denominacion": "TEXT DEFAULT ''",
    "fecha_baja_monotributo": "TEXT",
}

VOUCHER_COLUMNS = {
    "numero_hasta": "TEXT DEFAULT ''",
    "codigo_autorizacion": "TEXT DEFAULT ''",
    "tipo_doc_contraparte": "TEXT DEFAULT ''",
    "tipo_doc_receptor": "TEXT DEFAULT ''",
    "nro_doc_receptor": "TEXT DEFAULT ''",
    "concepto": "TEXT DEFAULT ''",
    "nombre_archivo_origen": "TEXT DEFAULT ''",
    "fecha_importacion": "TEXT",
    "tipo_archivo": "TEXT DEFAULT ''",
    "usuario_importacion": "TEXT DEFAULT ''",
    "id_importacion": "INTEGER",
}


def _add_columns(
    connection: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    existing = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if not existing:
        return
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def migrate_database(connection: sqlite3.Connection) -> None:
    _add_columns(connection, "clientes", CLIENT_COLUMNS)
    _add_columns(connection, "monotributo_cliente", MONO_COLUMNS)
    _add_columns(connection, "comprobantes_ventas", VOUCHER_COLUMNS)
    _add_columns(connection, "comprobantes_compras", VOUCHER_COLUMNS)
    _add_columns(
        connection,
        "vencimientos",
        {
            "organismo": "TEXT DEFAULT ''",
            "tipo_vencimiento": "TEXT DEFAULT ''",
            "responsable": "TEXT DEFAULT 'NATALIA'",
            "fecha_cumplimiento": "TEXT",
        },
    )
    _add_columns(
        connection,
        "tareas",
        {
            "medio": "TEXT DEFAULT ''",
            "documentacion_vinculada": "TEXT DEFAULT ''",
            "proximo_paso": "TEXT DEFAULT ''",
            "fecha_cumplimiento": "TEXT",
        },
    )
    _add_columns(
        connection,
        "honorarios",
        {
            "numero_presupuesto": "TEXT DEFAULT ''",
            "tipo_registro": "TEXT DEFAULT 'Honorario'",
            "fecha_vencimiento": "TEXT",
            "importe_pagado": "REAL DEFAULT 0",
            "numero_comprobante": "TEXT DEFAULT ''",
            "actualizado_en": "TEXT",
            "comprobante_emitido": "TEXT DEFAULT ''",
            "tipo_comprobante": "TEXT DEFAULT ''",
            "condiciones_presupuesto": "TEXT DEFAULT ''",
        },
    )
    _add_columns(
        connection,
        "documentacion",
        {
            "obligatorio": "TEXT DEFAULT 'Según caso'",
            "archivo_link": "TEXT DEFAULT ''",
        },
    )
    _add_columns(
        connection,
        "cliente_legajo_registros",
        {
            "numero_presupuesto": "TEXT DEFAULT ''",
        },
    )
    _add_columns(
        connection,
        "iibb_monotributo",
        {
            "regimen_principal": "TEXT DEFAULT ''",
            "importe_fijo": "REAL DEFAULT 0",
            "fecha_vencimiento": "TEXT",
        },
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS ingresos_brutos_cliente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL UNIQUE,
            regimen_principal TEXT NOT NULL DEFAULT 'ARBA - REG SIMP',
            alicuota REAL NOT NULL DEFAULT 0,
            fecha_alta TEXT,
            fecha_baja TEXT,
            estado TEXT NOT NULL DEFAULT 'activo',
            observaciones TEXT DEFAULT '',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tipos_comprobante (
            codigo INTEGER PRIMARY KEY,
            descripcion TEXT NOT NULL,
            clase TEXT NOT NULL,
            signo_fiscal INTEGER NOT NULL CHECK(signo_fiscal IN (-1, 1)),
            activo INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS importaciones_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            archivo TEXT NOT NULL,
            formato TEXT NOT NULL,
            filas_leidas INTEGER NOT NULL DEFAULT 0,
            filas_importadas INTEGER NOT NULL DEFAULT 0,
            filas_duplicadas INTEGER NOT NULL DEFAULT 0,
            filas_error INTEGER NOT NULL DEFAULT 0,
            fecha_importacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            observaciones TEXT DEFAULT '',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS iibb_convenio_jurisdicciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            periodo TEXT NOT NULL,
            jurisdiccion TEXT NOT NULL,
            coeficiente REAL NOT NULL DEFAULT 0,
            base_asignada REAL NOT NULL DEFAULT 0,
            alicuota REAL NOT NULL DEFAULT 0,
            impuesto_determinado REAL NOT NULL DEFAULT 0,
            observaciones TEXT DEFAULT '',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS configuracion_alertas_cliente (
            cliente_id INTEGER NOT NULL,
            clave TEXT NOT NULL,
            valor TEXT NOT NULL,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(cliente_id, clave),
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_config_alertas_cliente
            ON configuracion_alertas_cliente(cliente_id);

        CREATE TABLE IF NOT EXISTS cliente_legajo_campos (
            cliente_id INTEGER NOT NULL,
            seccion TEXT NOT NULL,
            campo TEXT NOT NULL,
            valor TEXT DEFAULT '',
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            responsable TEXT NOT NULL DEFAULT 'NATALIA',
            PRIMARY KEY(cliente_id, seccion, campo),
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cliente_legajo_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            seccion TEXT NOT NULL,
            fecha TEXT,
            periodo TEXT,
            descripcion TEXT DEFAULT '',
            estado TEXT DEFAULT 'pendiente',
            importe REAL NOT NULL DEFAULT 0,
            saldo REAL NOT NULL DEFAULT 0,
            vencimiento TEXT,
            datos_json TEXT NOT NULL DEFAULT '{}',
            responsable TEXT NOT NULL DEFAULT 'NATALIA',
            numero_presupuesto TEXT DEFAULT '',
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cliente_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            tipo_cambio TEXT NOT NULL,
            seccion TEXT DEFAULT '',
            dato_modificado TEXT DEFAULT '',
            estado_anterior TEXT DEFAULT '',
            estado_nuevo TEXT DEFAULT '',
            responsable TEXT NOT NULL DEFAULT 'NATALIA',
            motivo TEXT DEFAULT '',
            observaciones TEXT DEFAULT '',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_legajo_registros_cliente_seccion
            ON cliente_legajo_registros(cliente_id, seccion);
        CREATE INDEX IF NOT EXISTS idx_legajo_registros_vencimiento
            ON cliente_legajo_registros(vencimiento, estado);
        CREATE INDEX IF NOT EXISTS idx_historial_cliente_fecha
            ON cliente_historial(cliente_id, fecha);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_legajo_unico
            ON clientes(legajo) WHERE legajo <> '';
        DROP INDEX IF EXISTS idx_presupuesto_legajo_unico;
        CREATE UNIQUE INDEX idx_presupuesto_legajo_unico
            ON cliente_legajo_registros(numero_presupuesto)
            WHERE numero_presupuesto <> '' AND seccion = 'servicio_presupuesto';

        CREATE TABLE IF NOT EXISTS iibb_jurisdicciones_cliente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            jurisdiccion TEXT NOT NULL,
            porcentaje REAL NOT NULL DEFAULT 0,
            regimen TEXT NOT NULL DEFAULT 'A revisar',
            fecha_alta TEXT,
            estado TEXT NOT NULL DEFAULT 'Activo',
            observaciones TEXT DEFAULT '',
            UNIQUE(cliente_id, jurisdiccion),
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS movimientos_mercado_pago (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            periodo TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            tipo_movimiento TEXT NOT NULL DEFAULT 'A revisar',
            operacion TEXT DEFAULT '',
            contraparte TEXT DEFAULT '',
            contraparte_documento TEXT DEFAULT '',
            medio_pago TEXT DEFAULT '',
            id_operacion TEXT DEFAULT '',
            id_movimiento TEXT DEFAULT '',
            referencia TEXT DEFAULT '',
            moneda TEXT NOT NULL DEFAULT 'ARS',
            importe_bruto REAL NOT NULL DEFAULT 0,
            comisiones REAL NOT NULL DEFAULT 0,
            retenciones REAL NOT NULL DEFAULT 0,
            percepciones REAL NOT NULL DEFAULT 0,
            impuestos REAL NOT NULL DEFAULT 0,
            importe_neto REAL NOT NULL DEFAULT 0,
            saldo REAL NOT NULL DEFAULT 0,
            ingreso_egreso TEXT NOT NULL DEFAULT 'Ingreso',
            estado TEXT DEFAULT '',
            clasificacion_manual TEXT DEFAULT '',
            observaciones TEXT DEFAULT '',
            nombre_archivo_origen TEXT DEFAULT '',
            id_importacion INTEGER,
            fecha_importacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_plataformas(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS operaciones_mercado_libre (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            periodo TEXT NOT NULL,
            tipo_operacion TEXT NOT NULL DEFAULT 'Venta',
            tipo_comprobante TEXT DEFAULT '',
            numero_comprobante TEXT DEFAULT '',
            estado TEXT DEFAULT '',
            contraparte TEXT DEFAULT '',
            contraparte_documento TEXT DEFAULT '',
            producto TEXT DEFAULT '',
            cantidad REAL NOT NULL DEFAULT 0,
            precio_unitario REAL NOT NULL DEFAULT 0,
            importe_bruto REAL NOT NULL DEFAULT 0,
            descuentos REAL NOT NULL DEFAULT 0,
            comisiones REAL NOT NULL DEFAULT 0,
            envios REAL NOT NULL DEFAULT 0,
            retenciones REAL NOT NULL DEFAULT 0,
            percepciones REAL NOT NULL DEFAULT 0,
            importe_neto REAL NOT NULL DEFAULT 0,
            moneda TEXT NOT NULL DEFAULT 'ARS',
            id_operacion TEXT DEFAULT '',
            id_venta TEXT DEFAULT '',
            id_publicacion TEXT DEFAULT '',
            medio_cobro TEXT DEFAULT '',
            observaciones TEXT DEFAULT '',
            nombre_archivo_origen TEXT DEFAULT '',
            id_importacion INTEGER,
            fecha_importacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_plataformas(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS historial_importaciones_plataformas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            fuente TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            fecha_importacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL DEFAULT 'NATALIA',
            importados INTEGER NOT NULL DEFAULT 0,
            duplicados INTEGER NOT NULL DEFAULT 0,
            revisar INTEGER NOT NULL DEFAULT 0,
            rechazados INTEGER NOT NULL DEFAULT 0,
            periodo_detectado TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'Importado correctamente',
            observaciones TEXT DEFAULT '',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_mp_cliente_fecha
            ON movimientos_mercado_pago(cliente_id, fecha);
        CREATE INDEX IF NOT EXISTS idx_mp_operacion
            ON movimientos_mercado_pago(cliente_id, id_operacion);
        CREATE INDEX IF NOT EXISTS idx_ml_cliente_fecha
            ON operaciones_mercado_libre(cliente_id, fecha);
        CREATE INDEX IF NOT EXISTS idx_ml_operacion
            ON operaciones_mercado_libre(cliente_id, id_operacion, id_venta);
        """
    )
    _backfill_internal_numbers(connection)
    _add_columns(
        connection,
        "ingresos_brutos_cliente",
        {
            "jurisdiccion": "TEXT DEFAULT ''",
            "actividad": "TEXT DEFAULT ''",
        },
    )
    _add_columns(
        connection,
        "monotributo_cliente",
        {
            "estado_pago_mensual": "TEXT DEFAULT 'pendiente'",
            "estado_recategorizacion": "TEXT DEFAULT 'pendiente'",
            "riesgo_exclusion": "TEXT DEFAULT 'normal'",
            "tipo_actividad": "TEXT DEFAULT 'Servicios'",
            "aporta_sipa": "TEXT DEFAULT 'Sí'",
            "aporta_obra_social": "TEXT DEFAULT 'Sí'",
            "adherentes_obra_social": "INTEGER DEFAULT 0",
            "condicion_especial": "TEXT DEFAULT 'Sin condición especial'",
        },
    )
    _add_columns(
        connection,
        "categorias_monotributo",
        {
            "impuesto_integrado_servicios": "REAL DEFAULT 0",
            "impuesto_integrado_ventas": "REAL DEFAULT 0",
            "aporte_sipa": "REAL DEFAULT 0",
            "aporte_obra_social": "REAL DEFAULT 0",
            "total_servicios": "REAL DEFAULT 0",
            "total_ventas": "REAL DEFAULT 0",
            "estado": "TEXT DEFAULT 'Vigente'",
            "fuente": "TEXT DEFAULT 'Carga manual'",
            "archivo_origen": "TEXT DEFAULT ''",
            "fecha_importacion": "TEXT",
            "referencias": "TEXT DEFAULT ''",
        },
    )
    _add_columns(
        connection,
        "vencimientos",
        {
            "importe": "REAL DEFAULT 0",
            "saldo": "REAL DEFAULT 0",
            "fecha_presentacion": "TEXT",
            "fecha_pago": "TEXT",
            "origen": "TEXT DEFAULT 'manual'",
            "id_importacion": "INTEGER",
            "actualizado_en": "TEXT",
            "posible_duplicado": "INTEGER DEFAULT 0",
        },
    )
    _add_columns(
        connection,
        "historial_importaciones_plataformas",
        {
            "filas_leidas": "INTEGER DEFAULT 0",
            "fila_encabezado": "INTEGER",
            "hoja_detectada": "TEXT DEFAULT ''",
            "columnas_originales": "TEXT DEFAULT ''",
            "resumen_json": "TEXT DEFAULT '{}'",
        },
    )
    _add_columns(
        connection,
        "movimientos_mercado_pago",
        {
            "estado_revision": "TEXT DEFAULT ''",
            "posible_duplicado": "INTEGER DEFAULT 0",
            "datos_originales_json": "TEXT DEFAULT '{}'",
        },
    )
    _add_columns(
        connection,
        "operaciones_mercado_libre",
        {
            "sku": "TEXT DEFAULT ''",
            "variante": "TEXT DEFAULT ''",
            "ingresos_envio": "REAL DEFAULT 0",
            "costo_fijo": "REAL DEFAULT 0",
            "costo_cuotas": "REAL DEFAULT 0",
            "costo_envio": "REAL DEFAULT 0",
            "impuestos": "REAL DEFAULT 0",
            "anulaciones_reembolsos": "REAL DEFAULT 0",
            "resultado_neto": "REAL DEFAULT 0",
            "condicion_fiscal_comprador": "TEXT DEFAULT ''",
            "direccion_facturacion": "TEXT DEFAULT ''",
            "domicilio_entrega": "TEXT DEFAULT ''",
            "ciudad": "TEXT DEFAULT ''",
            "provincia": "TEXT DEFAULT ''",
            "codigo_postal": "TEXT DEFAULT ''",
            "pais": "TEXT DEFAULT ''",
            "reclamo_abierto": "TEXT DEFAULT ''",
            "reclamo_cerrado": "TEXT DEFAULT ''",
            "con_mediacion": "TEXT DEFAULT ''",
            "estado_especial": "TEXT DEFAULT ''",
            "posible_duplicado": "INTEGER DEFAULT 0",
            "datos_originales_json": "TEXT DEFAULT '{}'",
            "descripcion_estado": "TEXT DEFAULT ''",
            "paquete_multiple": "TEXT DEFAULT ''",
            "pertenece_kit": "TEXT DEFAULT ''",
            "mes_facturacion": "TEXT DEFAULT ''",
            "orden_compra": "TEXT DEFAULT ''",
            "venta_publicidad": "TEXT DEFAULT ''",
            "cuotas_agregadas": "TEXT DEFAULT ''",
            "factura_adjunta": "TEXT DEFAULT ''",
            "datos_facturacion_comprador": "TEXT DEFAULT ''",
            "negocio": "TEXT DEFAULT ''",
            "forma_entrega": "TEXT DEFAULT ''",
            "fecha_en_camino": "TEXT",
            "fecha_entregado": "TEXT",
            "transportista": "TEXT DEFAULT ''",
            "numero_seguimiento": "TEXT DEFAULT ''",
            "url_seguimiento": "TEXT DEFAULT ''",
            "revisado_ml": "TEXT DEFAULT ''",
            "fecha_revision": "TEXT",
            "dinero_favor": "REAL DEFAULT 0",
            "resultado_reclamo": "TEXT DEFAULT ''",
            "destino_reclamo": "TEXT DEFAULT ''",
            "motivo_resultado": "TEXT DEFAULT ''",
        },
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS historial_importaciones_contables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            fuente TEXT NOT NULL,
            archivo TEXT NOT NULL,
            fecha_importacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL DEFAULT 'NATALIA',
            filas_leidas INTEGER NOT NULL DEFAULT 0,
            filas_importadas INTEGER NOT NULL DEFAULT 0,
            filas_duplicadas INTEGER NOT NULL DEFAULT 0,
            filas_revisar INTEGER NOT NULL DEFAULT 0,
            filas_error INTEGER NOT NULL DEFAULT 0,
            vigencia_detectada TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'Importado correctamente',
            metadatos_json TEXT NOT NULL DEFAULT '{}',
            observaciones TEXT DEFAULT '',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS arca_domicilios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            tipo TEXT DEFAULT '', estado TEXT DEFAULT '', direccion TEXT DEFAULT '',
            localidad TEXT DEFAULT '', codigo_postal TEXT DEFAULT '', provincia TEXT DEFAULT '',
            orden INTEGER DEFAULT 0, nomenclado TEXT DEFAULT '', fecha_baja TEXT,
            fecha_actualizacion TEXT, coordenadas TEXT DEFAULT '', observaciones TEXT DEFAULT '',
            id_importacion INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_contables(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS arca_caracterizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL, descripcion TEXT NOT NULL, periodo_desde TEXT DEFAULT '',
            dia_periodo TEXT DEFAULT '', codigo_impuesto TEXT DEFAULT '', impuesto TEXT DEFAULT '',
            fecha_actualizacion TEXT, domicilios TEXT DEFAULT '', estado TEXT DEFAULT 'Activa',
            id_importacion INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_contables(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS arca_impuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL, codigo TEXT DEFAULT '', descripcion TEXT NOT NULL,
            periodo_desde TEXT DEFAULT '', dia_periodo TEXT DEFAULT '', estado TEXT DEFAULT 'Activo',
            motivo TEXT DEFAULT '', fecha_inscripcion TEXT, fecha_actualizacion TEXT,
            id_importacion INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_contables(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS arca_actividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL, nomenclador TEXT DEFAULT '', codigo TEXT NOT NULL,
            descripcion TEXT NOT NULL, condicion TEXT DEFAULT '', orden INTEGER DEFAULT 0,
            periodo_desde TEXT DEFAULT '', fecha_actualizacion TEXT, tipo TEXT DEFAULT 'Económica',
            id_importacion INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_contables(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS historial_categorias_monotributo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria_id INTEGER NOT NULL, campo TEXT NOT NULL, valor_anterior TEXT DEFAULT '',
            valor_nuevo TEXT DEFAULT '', responsable TEXT NOT NULL DEFAULT 'NATALIA',
            motivo TEXT DEFAULT '', fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(categoria_id) REFERENCES categorias_monotributo(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS arca_contactos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            clase TEXT NOT NULL,
            valor TEXT NOT NULL,
            tipo TEXT DEFAULT '',
            pais TEXT DEFAULT '',
            area TEXT DEFAULT '',
            numero TEXT DEFAULT '',
            compania TEXT DEFAULT '',
            alias TEXT DEFAULT '',
            estado TEXT DEFAULT '',
            fecha_actualizacion TEXT,
            principal INTEGER NOT NULL DEFAULT 0,
            id_importacion INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_contables(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS arca_datos_digitales (
            cliente_id INTEGER PRIMARY KEY,
            foto_registrada TEXT DEFAULT 'A revisar',
            firma_registrada TEXT DEFAULT 'A revisar',
            huella_registrada TEXT DEFAULT 'A revisar',
            domicilio_fiscal_electronico TEXT DEFAULT 'A revisar',
            fecha_alta TEXT,
            fecha_actualizacion TEXT,
            id_importacion INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_contables(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS arca_datos_migratorios (
            cliente_id INTEGER PRIMARY KEY,
            tipo_residencia TEXT DEFAULT '',
            vencimiento_migratorio TEXT,
            documento_extranjero TEXT DEFAULT '',
            fecha_actualizacion TEXT,
            id_importacion INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY(id_importacion) REFERENCES historial_importaciones_contables(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS historial_vencimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vencimiento_id INTEGER,
            cliente_id INTEGER,
            campo TEXT NOT NULL,
            valor_anterior TEXT DEFAULT '',
            valor_nuevo TEXT DEFAULT '',
            responsable TEXT NOT NULL DEFAULT 'NATALIA',
            observaciones TEXT DEFAULT '',
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(vencimiento_id) REFERENCES vencimientos(id) ON DELETE SET NULL,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_importaciones_contables_fuente
            ON historial_importaciones_contables(fuente, fecha_importacion);
        CREATE INDEX IF NOT EXISTS idx_arca_domicilios_cliente ON arca_domicilios(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_arca_impuestos_cliente ON arca_impuestos(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_arca_actividades_cliente ON arca_actividades(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_arca_contactos_cliente ON arca_contactos(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_historial_vencimientos_registro ON historial_vencimientos(vencimiento_id,fecha);
        """
    )
    # Limpia posibles registros huérfanos generados por versiones antiguas.
    for table in (
        "alertas_fiscales",
        "comprobantes_ventas",
        "comprobantes_compras",
        "importaciones_archivos",
    ):
        connection.execute(
            f"DELETE FROM {table} WHERE cliente_id NOT IN (SELECT id FROM clientes)"
        )


def _backfill_internal_numbers(connection: sqlite3.Connection) -> None:
    """Asigna códigos correlativos a registros antiguos sin alterar códigos válidos."""
    used_ledgers = {
        str(row[0]).upper()
        for row in connection.execute("SELECT legajo FROM clientes WHERE legajo<>''")
    }
    next_ledger = 10
    for row in connection.execute("SELECT id,legajo FROM clientes ORDER BY id").fetchall():
        value = str(row[1] or "").strip().upper()
        if value:
            continue
        while f"EA-{next_ledger:04d}" in used_ledgers:
            next_ledger += 1
        value = f"EA-{next_ledger:04d}"
        connection.execute("UPDATE clientes SET legajo=? WHERE id=?", (value, row[0]))
        used_ledgers.add(value)
        next_ledger += 1

    next_budget = 10
    records = connection.execute(
        """SELECT id,numero_presupuesto,datos_json FROM cliente_legajo_registros
           WHERE seccion='servicio_presupuesto' ORDER BY id"""
    ).fetchall()
    reserved = set()
    for _record_id, stored_number, raw_json in records:
        try:
            data = json.loads(raw_json or "{}")
        except json.JSONDecodeError:
            data = {}
        value = str(data.get("numero_presupuesto") or stored_number or "").strip().upper()
        if re.fullmatch(r"EAP-\d{4,}", value):
            reserved.add(value)
    seen = set()
    for record_id, stored_number, raw_json in records:
        try:
            data = json.loads(raw_json or "{}")
        except json.JSONDecodeError:
            data = {}
        value = str(data.get("numero_presupuesto") or stored_number or "").strip().upper()
        if not re.fullmatch(r"EAP-\d{4,}", value) or value in seen:
            while f"EAP-{next_budget:04d}" in reserved or f"EAP-{next_budget:04d}" in seen:
                next_budget += 1
            value = f"EAP-{next_budget:04d}"
            next_budget += 1
        data["numero_presupuesto"] = value
        connection.execute(
            "UPDATE cliente_legajo_registros SET numero_presupuesto=?,datos_json=? WHERE id=?",
            (value, json.dumps(data, ensure_ascii=False), record_id),
        )
        reserved.add(value)
        seen.add(value)
