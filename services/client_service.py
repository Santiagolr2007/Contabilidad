from __future__ import annotations

import sqlite3

from database import Database
from models import Client, FiscalProfile, MonotributoProfile
from utils.validators import required, validate_cuit, validate_email


class ClientService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_clients(
        self, search: str = "", include_inactive: bool = False
    ) -> list[dict]:
        conditions = []
        params: list[str] = []
        if search.strip():
            conditions.append(
                "(c.nombre_razon_social LIKE ? OR c.cuit_cuil LIKE ? OR c.rubro LIKE ?)"
            )
            term = f"%{search.strip()}%"
            params.extend((term, term, term))
        if not include_inactive:
            conditions.append("c.estado = 'activo'")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT c.*, COALESCE(NULLIF(c.rubro, ''), c.actividad) AS rubro_display,
                   COALESCE(df.regimen_principal, 'sin_definir') AS regimen_principal,
                   COALESCE(m.categoria_actual, '') AS categoria_actual
            FROM clientes c
            LEFT JOIN datos_fiscales_cliente df ON df.cliente_id = c.id
            LEFT JOIN monotributo_cliente m ON m.cliente_id = c.id
            {where}
            ORDER BY c.nombre_razon_social COLLATE NOCASE
        """
        return [dict(row) for row in self.database.query(sql, params)]

    def get_bundle(self, client_id: int) -> dict | None:
        client = self.database.query_one("SELECT * FROM clientes WHERE id = ?", (client_id,))
        if not client:
            return None
        fiscal = self.database.query_one(
            "SELECT * FROM datos_fiscales_cliente WHERE cliente_id = ?", (client_id,)
        )
        mono = self.database.query_one(
            "SELECT * FROM monotributo_cliente WHERE cliente_id = ?", (client_id,)
        )
        return {
            "client": dict(client),
            "fiscal": dict(fiscal) if fiscal else {},
            "monotributo": dict(mono) if mono else {},
        }

    def save(
        self,
        client: Client,
        fiscal: FiscalProfile,
        monotributo: MonotributoProfile | None = None,
    ) -> int:
        is_new = client.id is None
        client.nombre_razon_social = required(
            client.nombre_razon_social, "Nombre o razón social"
        )
        client.cuit_cuil = validate_cuit(client.cuit_cuil)
        client.email = validate_email(client.email)
        if client.tipo_persona not in ("persona_humana", "sociedad"):
            raise ValueError("El tipo de persona seleccionado no es válido.")

        if (
            monotributo
            and monotributo.codigo_actividad
            and not monotributo.codigo_actividad.strip().isdigit()
        ):
            raise ValueError("El código de actividad debe contener solamente números.")

        try:
            with self.database.connection() as connection:
                if client.id:
                    connection.execute(
                        """
                        UPDATE clientes SET
                            nombre_razon_social = ?, cuit_cuil = ?, tipo_persona = ?,
                            dni = ?, fecha_nacimiento = ?, nacionalidad = ?, estado_civil = ?,
                            telefono = ?, email = ?, instagram = ?, domicilio = ?,
                            rubro = ?, actividad = ?, fecha_alta_estudio = ?,
                            estado = ?, observaciones = ?, actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            client.nombre_razon_social,
                            client.cuit_cuil,
                            client.tipo_persona,
                            client.dni.strip(),
                            client.fecha_nacimiento or None,
                            client.nacionalidad.strip(),
                            client.estado_civil.strip(),
                            client.telefono.strip(),
                            client.email,
                            client.instagram.strip(),
                            client.domicilio.strip(),
                            client.rubro.strip(),
                            client.rubro.strip(),
                            client.fecha_alta_estudio or None,
                            client.estado,
                            client.observaciones.strip(),
                            client.id,
                        ),
                    )
                    client_id = client.id
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO clientes(
                            nombre_razon_social, cuit_cuil, tipo_persona, dni,
                            fecha_nacimiento, nacionalidad, estado_civil, telefono,
                            email, instagram, domicilio, rubro, actividad,
                            fecha_alta_estudio, estado, observaciones
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            client.nombre_razon_social,
                            client.cuit_cuil,
                            client.tipo_persona,
                            client.dni.strip(),
                            client.fecha_nacimiento or None,
                            client.nacionalidad.strip(),
                            client.estado_civil.strip(),
                            client.telefono.strip(),
                            client.email,
                            client.instagram.strip(),
                            client.domicilio.strip(),
                            client.rubro.strip(),
                            client.rubro.strip(),
                            client.fecha_alta_estudio or None,
                            client.estado,
                            client.observaciones.strip(),
                        ),
                    )
                    client_id = int(cursor.lastrowid)

                connection.execute(
                    """
                    INSERT INTO datos_fiscales_cliente(
                        cliente_id, regimen_principal, condicion_iva, fecha_alta,
                        domicilio_fiscal, jurisdiccion_iibb, regimen_iibb, observaciones
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cliente_id) DO UPDATE SET
                        regimen_principal = excluded.regimen_principal,
                        condicion_iva = excluded.condicion_iva,
                        fecha_alta = excluded.fecha_alta,
                        domicilio_fiscal = excluded.domicilio_fiscal,
                        jurisdiccion_iibb = excluded.jurisdiccion_iibb,
                        regimen_iibb = excluded.regimen_iibb,
                        observaciones = excluded.observaciones
                    """,
                    (
                        client_id,
                        fiscal.regimen_principal,
                        fiscal.condicion_iva.strip(),
                        fiscal.fecha_alta or None,
                        fiscal.domicilio_fiscal.strip(),
                        fiscal.jurisdiccion_iibb.strip(),
                        fiscal.regimen_iibb,
                        fiscal.observaciones.strip(),
                    ),
                )

                obligation_code = {
                    "monotributista": "MONOTRIBUTO",
                    "responsable_inscripto": "IVA",
                    "ganancias": "GANANCIAS",
                    "bienes_personales": "BIENES",
                }.get(fiscal.regimen_principal)
                if obligation_code:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO cliente_obligaciones(
                            cliente_id, obligacion_id, fecha_desde, estado
                        )
                        SELECT ?, id, ?, 'activa' FROM obligaciones_fiscales WHERE codigo = ?
                        """,
                        (client_id, client.fecha_alta_estudio or None, obligation_code),
                    )

                if fiscal.regimen_principal == "monotributista" and monotributo:
                    connection.execute(
                        """
                        INSERT INTO monotributo_cliente(
                            cliente_id, categoria_actual, actividad, actividad_fiscal,
                            codigo_actividad, denominacion, fecha_alta, fecha_baja_monotributo,
                            estado, observaciones_fiscales,tipo_actividad,aporta_sipa,
                            aporta_obra_social,adherentes_obra_social,condicion_especial
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(cliente_id) DO UPDATE SET
                            categoria_actual = excluded.categoria_actual,
                            actividad = excluded.actividad,
                            actividad_fiscal = excluded.actividad_fiscal,
                            codigo_actividad = excluded.codigo_actividad,
                            denominacion = excluded.denominacion,
                            fecha_alta = excluded.fecha_alta,
                            fecha_baja_monotributo = excluded.fecha_baja_monotributo,
                            estado = excluded.estado,
                            observaciones_fiscales = excluded.observaciones_fiscales,
                            tipo_actividad=excluded.tipo_actividad,
                            aporta_sipa=excluded.aporta_sipa,
                            aporta_obra_social=excluded.aporta_obra_social,
                            adherentes_obra_social=excluded.adherentes_obra_social,
                            condicion_especial=excluded.condicion_especial
                        """,
                        (
                            client_id,
                            monotributo.categoria_actual,
                            monotributo.actividad_fiscal.strip(),
                            monotributo.actividad_fiscal.strip(),
                            monotributo.codigo_actividad.strip(),
                            monotributo.denominacion.strip(),
                            monotributo.fecha_alta or None,
                            monotributo.fecha_baja or None,
                            monotributo.estado,
                            monotributo.observaciones_fiscales.strip(),
                            monotributo.tipo_actividad,
                            monotributo.aporta_sipa,
                            monotributo.aporta_obra_social,
                            int(monotributo.adherentes_obra_social or 0),
                            monotributo.condicion_especial,
                        ),
                    )
                connection.execute(
                    """
                    INSERT INTO cliente_historial(
                        cliente_id, tipo_cambio, seccion, dato_modificado,
                        estado_nuevo, responsable
                    ) VALUES (?, ?, 'datos_cliente', 'Ficha principal', ?, 'NATALIA')
                    """,
                    (
                        client_id,
                        "Alta" if is_new else "Modificación de datos",
                        client.estado,
                    ),
                )
                return client_id
        except sqlite3.IntegrityError as error:
            if "cuit_cuil" in str(error):
                raise ValueError("Ya existe un cliente con ese CUIT/CUIL.") from error
            raise ValueError("No se pudo guardar el cliente por datos duplicados.") from error

    def deactivate(self, client_id: int) -> None:
        self.database.execute(
            """
            UPDATE clientes SET estado = 'inactivo', actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (client_id,),
        )

    def delete_permanently(self, client_id: int) -> dict[str, int]:
        """Elimina la ficha y todos sus registros relacionados mediante cascada."""
        client = self.database.query_one(
            "SELECT id FROM clientes WHERE id = ?", (client_id,)
        )
        if not client:
            raise ValueError("El cliente seleccionado ya no existe.")
        sales = self.database.query_one(
            "SELECT COUNT(*) AS n FROM comprobantes_ventas WHERE cliente_id = ?",
            (client_id,),
        )
        purchases = self.database.query_one(
            "SELECT COUNT(*) AS n FROM comprobantes_compras WHERE cliente_id = ?",
            (client_id,),
        )
        # Se eliminan explícitamente los registros críticos y luego la ficha.
        # Las demás tablas relacionadas también poseen ON DELETE CASCADE.
        with self.database.connection() as connection:
            connection.execute(
                "DELETE FROM alertas_fiscales WHERE cliente_id = ?", (client_id,)
            )
            connection.execute(
                "DELETE FROM comprobantes_ventas WHERE cliente_id = ?", (client_id,)
            )
            connection.execute(
                "DELETE FROM comprobantes_compras WHERE cliente_id = ?", (client_id,)
            )
            connection.execute(
                "DELETE FROM importaciones_archivos WHERE cliente_id = ?", (client_id,)
            )
            connection.execute("DELETE FROM clientes WHERE id = ?", (client_id,))
        return {
            "ventas": int(sales["n"] or 0),
            "compras": int(purchases["n"] or 0),
        }
