from __future__ import annotations

from .connection import Database
from .migrations import migrate_database


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_razon_social TEXT NOT NULL,
    cuit_cuil TEXT NOT NULL UNIQUE,
    tipo_persona TEXT NOT NULL CHECK(tipo_persona IN ('persona_humana', 'sociedad')),
    telefono TEXT DEFAULT '',
    email TEXT DEFAULT '',
    domicilio TEXT DEFAULT '',
    actividad TEXT DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo', 'inactivo')),
    observaciones TEXT DEFAULT '',
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS datos_fiscales_cliente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL UNIQUE,
    regimen_principal TEXT NOT NULL DEFAULT 'sin_definir',
    condicion_iva TEXT DEFAULT '',
    fecha_alta TEXT,
    domicilio_fiscal TEXT DEFAULT '',
    jurisdiccion_iibb TEXT DEFAULT '',
    regimen_iibb TEXT DEFAULT '',
    observaciones TEXT DEFAULT '',
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS obligaciones_fiscales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    modulo TEXT NOT NULL,
    periodicidad TEXT DEFAULT 'mensual',
    activa INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cliente_obligaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    obligacion_id INTEGER NOT NULL,
    fecha_desde TEXT,
    fecha_hasta TEXT,
    estado TEXT NOT NULL DEFAULT 'activa',
    observaciones TEXT DEFAULT '',
    UNIQUE(cliente_id, obligacion_id),
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
    FOREIGN KEY(obligacion_id) REFERENCES obligaciones_fiscales(id)
);

CREATE TABLE IF NOT EXISTS monotributo_cliente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL UNIQUE,
    categoria_actual TEXT DEFAULT '',
    actividad TEXT DEFAULT '',
    fecha_alta TEXT,
    jurisdiccion_iibb TEXT DEFAULT '',
    regimen_iibb TEXT DEFAULT 'simplificado',
    estado TEXT NOT NULL DEFAULT 'activo',
    observaciones_fiscales TEXT DEFAULT '',
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comprobantes_ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    periodo_fiscal TEXT NOT NULL,
    tipo_comprobante TEXT NOT NULL,
    punto_venta TEXT NOT NULL,
    numero_comprobante TEXT NOT NULL,
    contraparte_nombre TEXT NOT NULL,
    contraparte_documento TEXT DEFAULT '',
    moneda TEXT NOT NULL DEFAULT 'ARS',
    tipo_cambio REAL NOT NULL DEFAULT 1,
    importe_original REAL NOT NULL,
    importe_pesos REAL NOT NULL,
    signo_fiscal INTEGER NOT NULL,
    importe_neto_fiscal REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'normal',
    origen TEXT NOT NULL DEFAULT 'manual',
    observaciones TEXT DEFAULT '',
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cliente_id, tipo_comprobante, punto_venta, numero_comprobante),
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comprobantes_compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    periodo_fiscal TEXT NOT NULL,
    tipo_comprobante TEXT NOT NULL,
    punto_venta TEXT NOT NULL,
    numero_comprobante TEXT NOT NULL,
    contraparte_nombre TEXT NOT NULL,
    contraparte_documento TEXT DEFAULT '',
    moneda TEXT NOT NULL DEFAULT 'ARS',
    tipo_cambio REAL NOT NULL DEFAULT 1,
    importe_original REAL NOT NULL,
    importe_pesos REAL NOT NULL,
    signo_fiscal INTEGER NOT NULL,
    importe_neto_fiscal REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'normal',
    origen TEXT NOT NULL DEFAULT 'manual',
    observaciones TEXT DEFAULT '',
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cliente_id, tipo_comprobante, punto_venta, numero_comprobante),
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS iibb_monotributo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    periodo TEXT NOT NULL,
    base_imponible REAL NOT NULL DEFAULT 0,
    alicuota REAL NOT NULL DEFAULT 0,
    impuesto_determinado REAL NOT NULL DEFAULT 0,
    retenciones REAL NOT NULL DEFAULT 0,
    percepciones REAL NOT NULL DEFAULT 0,
    saldo_favor_anterior REAL NOT NULL DEFAULT 0,
    saldo_pagar REAL NOT NULL DEFAULT 0,
    estado_presentacion TEXT DEFAULT 'pendiente',
    estado_pago TEXT DEFAULT 'pendiente',
    observaciones TEXT DEFAULT '',
    UNIQUE(cliente_id, periodo),
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS categorias_monotributo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT NOT NULL,
    tope_ingresos REAL NOT NULL,
    tope_alquileres REAL DEFAULT 0,
    tope_superficie REAL DEFAULT 0,
    tope_energia REAL DEFAULT 0,
    precio_unitario_maximo REAL DEFAULT 0,
    vigencia_desde TEXT NOT NULL,
    vigencia_hasta TEXT,
    observaciones TEXT DEFAULT '',
    UNIQUE(categoria, vigencia_desde)
);

CREATE TABLE IF NOT EXISTS recategorizaciones_monotributo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    periodo_desde TEXT NOT NULL,
    periodo_hasta TEXT NOT NULL,
    ventas_ultimos_12_meses REAL NOT NULL,
    categoria_actual TEXT,
    categoria_sugerida TEXT,
    diferencia_categoria REAL DEFAULT 0,
    diferencia_tope REAL DEFAULT 0,
    estado TEXT NOT NULL,
    alquileres REAL DEFAULT 0,
    energia REAL DEFAULT 0,
    superficie REAL DEFAULT 0,
    precio_unitario_maximo REAL DEFAULT 0,
    observaciones TEXT DEFAULT '',
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alertas_fiscales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    periodo TEXT,
    tipo_alerta TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    importe_relacionado REAL DEFAULT 0,
    gravedad TEXT NOT NULL DEFAULT 'media',
    estado TEXT NOT NULL DEFAULT 'activa',
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observaciones TEXT DEFAULT '',
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documentacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    periodo TEXT,
    tipo_documento TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'solicitada',
    fecha_solicitud TEXT,
    fecha_recepcion TEXT,
    observaciones TEXT DEFAULT '',
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    modulo TEXT NOT NULL,
    periodo TEXT,
    titulo TEXT NOT NULL,
    descripcion TEXT DEFAULT '',
    responsable TEXT DEFAULT '',
    fecha_inicio TEXT,
    fecha_vencimiento TEXT,
    fecha_finalizacion TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    prioridad TEXT NOT NULL DEFAULT 'media',
    observaciones TEXT DEFAULT '',
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS vencimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    impuesto TEXT NOT NULL,
    periodo TEXT,
    fecha_vencimiento TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    observaciones TEXT DEFAULT '',
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS honorarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    servicio TEXT NOT NULL,
    periodo TEXT,
    importe REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente de facturar',
    fecha_emision TEXT,
    fecha_cobro TEXT,
    medio_pago TEXT DEFAULT '',
    saldo_pendiente REAL NOT NULL DEFAULT 0,
    observaciones TEXT DEFAULT '',
    FOREIGN KEY(cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'texto',
    descripcion TEXT DEFAULT '',
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ventas_cliente_fecha
    ON comprobantes_ventas(cliente_id, fecha);
CREATE INDEX IF NOT EXISTS idx_compras_cliente_fecha
    ON comprobantes_compras(cliente_id, fecha);
CREATE INDEX IF NOT EXISTS idx_alertas_cliente_estado
    ON alertas_fiscales(cliente_id, estado);
CREATE INDEX IF NOT EXISTS idx_vencimientos_fecha
    ON vencimientos(fecha_vencimiento, estado);
"""


def initialize_database(database: Database) -> None:
    with database.connection() as connection:
        connection.executescript(SCHEMA_SQL)
        migrate_database(connection)
