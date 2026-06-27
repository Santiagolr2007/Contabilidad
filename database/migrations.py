from __future__ import annotations

import sqlite3


CLIENT_COLUMNS = {
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
        """
    )
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
        },
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
