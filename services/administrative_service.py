from __future__ import annotations

from database import Database
from utils.formatters import normalize_period
from utils.validators import positive_number, required


class AdministrativeService:
    TABLES = {
        "documentacion": "documentacion",
        "tareas": "tareas",
        "vencimientos": "vencimientos",
        "honorarios": "honorarios",
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def _table(self, module: str) -> str:
        try:
            return self.TABLES[module]
        except KeyError as error:
            raise ValueError("El módulo administrativo no existe.") from error

    def list(self, module: str) -> list[dict]:
        table = self._table(module)
        date_order = {
            "documentacion": "d.id DESC",
            "tareas": "d.fecha_vencimiento, d.id DESC",
            "vencimientos": "d.fecha_vencimiento, d.id DESC",
            "honorarios": "d.id DESC",
        }[module]
        return [
            dict(row)
            for row in self.database.query(
                f"""
                SELECT d.*, COALESCE(c.nombre_razon_social, 'General') AS cliente_nombre
                FROM {table} d LEFT JOIN clientes c ON c.id = d.cliente_id
                ORDER BY {date_order}
                """
            )
        ]

    def get(self, module: str, record_id: int) -> dict | None:
        table = self._table(module)
        row = self.database.query_one(
            f"SELECT * FROM {table} WHERE id = ?", (record_id,)
        )
        return dict(row) if row else None

    def create(self, module: str, data: dict) -> int:
        return self._save(module, data)

    def update(self, module: str, record_id: int, data: dict) -> None:
        if not self.get(module, record_id):
            raise ValueError("El registro seleccionado ya no existe.")
        self._save(module, data, record_id)

    def _save(self, module: str, data: dict, record_id: int | None = None) -> int:
        self._table(module)
        if data.get("periodo"):
            data["periodo"] = normalize_period(data["periodo"])
        if module == "documentacion":
            values = (
                data["cliente_id"], data["periodo"],
                required(data["tipo_documento"], "Documento"), data["estado"],
                data.get("fecha_solicitud") or None,
                data.get("fecha_recepcion") or None,
                data.get("observaciones", ""),
            )
            if record_id:
                self.database.execute(
                    """UPDATE documentacion SET cliente_id=?, periodo=?,
                       tipo_documento=?, estado=?, fecha_solicitud=?,
                       fecha_recepcion=?, observaciones=? WHERE id=?""",
                    (*values, record_id),
                )
                return record_id
            return self.database.execute(
                """INSERT INTO documentacion(cliente_id, periodo, tipo_documento,
                   estado, fecha_solicitud, fecha_recepcion, observaciones)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                values,
            )

        if module == "tareas":
            values = (
                data.get("cliente_id"), required(data["modulo"], "Módulo"),
                data["periodo"], required(data["titulo"], "Título"),
                data.get("descripcion", ""), data.get("responsable", ""),
                data.get("fecha_inicio") or None,
                data.get("fecha_vencimiento") or None,
                data.get("fecha_finalizacion") or None,
                data["estado"], data["prioridad"], data.get("observaciones", ""),
            )
            if record_id:
                self.database.execute(
                    """UPDATE tareas SET cliente_id=?, modulo=?, periodo=?, titulo=?,
                       descripcion=?, responsable=?, fecha_inicio=?, fecha_vencimiento=?,
                       fecha_finalizacion=?, estado=?, prioridad=?, observaciones=?
                       WHERE id=?""",
                    (*values, record_id),
                )
                return record_id
            return self.database.execute(
                """INSERT INTO tareas(cliente_id, modulo, periodo, titulo, descripcion,
                   responsable, fecha_inicio, fecha_vencimiento, fecha_finalizacion,
                   estado, prioridad, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )

        if module == "vencimientos":
            if not data.get("cliente_id"):
                raise ValueError("Debe seleccionar un cliente.")
            period = normalize_period(data["periodo"]) if data.get("periodo") else ""
            duplicate = self.database.query_one(
                """SELECT id FROM vencimientos
                   WHERE cliente_id=? AND impuesto=? AND periodo=? AND fecha_vencimiento=?
                     AND (? IS NULL OR id<>?) LIMIT 1""",
                (
                    data["cliente_id"], required(data["impuesto"], "Impuesto"),
                    period, required(data["fecha_vencimiento"], "Fecha de vencimiento"),
                    record_id, record_id,
                ),
            )
            if duplicate:
                raise ValueError("Ya existe un vencimiento similar para este cliente.")
            values = (
                data["cliente_id"], required(data["impuesto"], "Impuesto"),
                period, required(data["fecha_vencimiento"], "Fecha de vencimiento"),
                data.get("organismo", ""), data.get("tipo_vencimiento", ""),
                data["estado"], data.get("responsable") or "NATALIA",
                data.get("observaciones", ""),
            )
            if record_id:
                self.database.execute(
                    """UPDATE vencimientos SET cliente_id=?, impuesto=?, periodo=?,
                       fecha_vencimiento=?, organismo=?, tipo_vencimiento=?, estado=?,
                       responsable=?, observaciones=? WHERE id=?""",
                    (*values, record_id),
                )
                return record_id
            return self.database.execute(
                """INSERT INTO vencimientos(cliente_id, impuesto, periodo,
                   fecha_vencimiento, organismo, tipo_vencimiento, estado,
                   responsable, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )

        if not data.get("cliente_id"):
            raise ValueError("Debe seleccionar un cliente.")
        amount = positive_number(data["importe"], "Importe")
        pending = positive_number(
            data.get("saldo_pendiente") or amount,
            "Saldo pendiente",
            allow_zero=True,
        )
        if pending > amount:
            raise ValueError("El saldo pendiente no puede superar el importe total.")
        period = normalize_period(data["periodo"]) if data.get("periodo") else ""
        duplicate = self.database.query_one(
            """SELECT id FROM honorarios WHERE cliente_id=? AND servicio=? AND periodo=?
               AND (? IS NULL OR id<>?) LIMIT 1""",
            (data["cliente_id"], required(data["servicio"], "Servicio"), period, record_id, record_id),
        )
        if duplicate:
            raise ValueError("Ya existe un honorario similar para este cliente.")
        values = (
            data["cliente_id"], required(data["servicio"], "Servicio"),
            period, amount, data["estado"],
            data.get("fecha_emision") or None, data.get("fecha_cobro") or None,
            data.get("medio_pago", ""), pending, data.get("observaciones", ""),
        )
        if record_id:
            self.database.execute(
                """UPDATE honorarios SET cliente_id=?, servicio=?, periodo=?, importe=?,
                   estado=?, fecha_emision=?, fecha_cobro=?, medio_pago=?,
                   saldo_pendiente=?, observaciones=? WHERE id=?""",
                (*values, record_id),
            )
            return record_id
        return self.database.execute(
            """INSERT INTO honorarios(cliente_id, servicio, periodo, importe, estado,
               fecha_emision, fecha_cobro, medio_pago, saldo_pendiente, observaciones)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )

    def delete(self, module: str, record_id: int) -> int:
        table = self._table(module)
        with self.database.connection() as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE id = ?", (record_id,)
            )
            return int(cursor.rowcount)

    def update_status(self, module: str, record_id: int, status: str) -> None:
        table = self._table(module)
        self.database.execute(
            f"UPDATE {table} SET estado = ? WHERE id = ?", (status, record_id)
        )
