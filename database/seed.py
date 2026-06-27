from __future__ import annotations

from datetime import date

from .connection import Database


CONFIGURACION_INICIAL = (
    (
        "monto_comprobante_significativo",
        "500000",
        "numero",
        "Importe absoluto desde el que un comprobante genera alerta",
    ),
    (
        "alicuota_iibb_default",
        "0.035",
        "decimal",
        "Alícuota inicial para estimar Ingresos Brutos",
    ),
    (
        "concentracion_porcentaje",
        "0.30",
        "decimal",
        "Participación de una contraparte que genera alerta de concentración",
    ),
    (
        "compras_ventas_alerta",
        "0.80",
        "decimal",
        "Relación compras/ventas desde la que se recomienda revisión",
    ),
    (
        "monotributo_alerta_porcentaje",
        "0.80",
        "decimal",
        "Porcentaje del límite de categoría que activa advertencia",
    ),
    ("muchas_facturas_dia", "10", "numero", "Cantidad diaria que genera alerta"),
    ("muchas_facturas_cliente", "10", "numero", "Cantidad mensual por contraparte que genera alerta"),
)

# Valores demostrativos: deben reemplazarse por la tabla normativa vigente.
CATEGORIAS_DEMO = (
    ("A", 5_000_000),
    ("B", 7_500_000),
    ("C", 10_000_000),
    ("D", 15_000_000),
    ("E", 20_000_000),
    ("F", 25_000_000),
    ("G", 30_000_000),
    ("H", 38_000_000),
    ("I", 46_000_000),
    ("J", 55_000_000),
    ("K", 65_000_000),
)


def seed_reference_data(database: Database) -> None:
    year = date.today().year
    with database.connection() as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO configuracion(clave, valor, tipo, descripcion)
            VALUES (?, ?, ?, ?)
            """,
            CONFIGURACION_INICIAL,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO categorias_monotributo(
                categoria, tope_ingresos, vigencia_desde, observaciones
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    categoria,
                    tope,
                    f"{year}-01-01",
                    "Dato de demostración. Actualizar con normativa vigente.",
                )
                for categoria, tope in CATEGORIAS_DEMO
            ],
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO obligaciones_fiscales(codigo, nombre, modulo)
            VALUES (?, ?, ?)
            """,
            (
                ("MONOTRIBUTO", "Monotributo", "monotributo"),
                ("IIBB", "Ingresos Brutos", "iibb"),
                ("IVA", "Impuesto al Valor Agregado", "responsables_inscriptos"),
                ("GANANCIAS", "Impuesto a las Ganancias", "ganancias"),
                ("BIENES", "Bienes Personales", "bienes_personales"),
            ),
        )
        connection.executemany(
            """
            INSERT OR REPLACE INTO tipos_comprobante(
                codigo, descripcion, clase, signo_fiscal, activo
            ) VALUES (?, ?, ?, ?, 1)
            """,
            (
                (1, "Factura A", "factura", 1),
                (2, "Nota de Débito A", "nota_debito", 1),
                (3, "Nota de Crédito A", "nota_credito", -1),
                (6, "Factura B", "factura", 1),
                (7, "Nota de Débito B", "nota_debito", 1),
                (8, "Nota de Crédito B", "nota_credito", -1),
                (11, "Factura C", "factura", 1),
                (12, "Nota de Débito C", "nota_debito", 1),
                (13, "Nota de Crédito C", "nota_credito", -1),
            ),
        )


def seed_demo_data(database: Database) -> None:
    """Agrega un caso ficticio solo cuando la base todavía no tiene clientes."""
    if database.query_one("SELECT id FROM clientes LIMIT 1"):
        return

    with database.connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO clientes(
                nombre_razon_social, cuit_cuil, tipo_persona, telefono, email,
                domicilio, actividad, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Cliente Demostración",
                "20123456786",
                "persona_humana",
                "341-555-0101",
                "demo@estudio.local",
                "Rosario, Santa Fe",
                "Servicios profesionales",
                "Registro ficticio para explorar la aplicación.",
            ),
        )
        cliente_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO datos_fiscales_cliente(
                cliente_id, regimen_principal, condicion_iva, fecha_alta,
                jurisdiccion_iibb, regimen_iibb
            ) VALUES (?, 'monotributista', 'Monotributista', ?, 'Santa Fe', 'local')
            """,
            (cliente_id, f"{date.today().year}-01-01"),
        )
        connection.execute(
            """
            INSERT INTO monotributo_cliente(
                cliente_id, categoria_actual, actividad, fecha_alta,
                jurisdiccion_iibb, regimen_iibb, observaciones_fiscales
            ) VALUES (?, 'B', 'Servicios profesionales', ?, 'Santa Fe', 'local', ?)
            """,
            (
                cliente_id,
                f"{date.today().year}-01-01",
                "Categorías y límites cargados son demostrativos.",
            ),
        )
