from __future__ import annotations

from database import Database


class AdministrativeService:
    TABLES = {
        "documentacion": "documentacion",
        "tareas": "tareas",
        "vencimientos": "vencimientos",
        "honorarios": "honorarios",
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self, module: str) -> list[dict]:
        table = self.TABLES[module]
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

    def create(self, module: str, data: dict) -> int:
        if module == "documentacion":
            return self.database.execute(
                """INSERT INTO documentacion(cliente_id, periodo, tipo_documento, estado,
                       fecha_solicitud, fecha_recepcion, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (data["cliente_id"], data["periodo"], data["tipo_documento"], data["estado"],
                 data.get("fecha_solicitud") or None, data.get("fecha_recepcion") or None,
                 data.get("observaciones", "")),
            )
        if module == "tareas":
            return self.database.execute(
                """INSERT INTO tareas(cliente_id, modulo, periodo, titulo, descripcion,
                       responsable, fecha_inicio, fecha_vencimiento, fecha_finalizacion,
                       estado, prioridad, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data.get("cliente_id"), data["modulo"], data["periodo"], data["titulo"],
                 data.get("descripcion", ""), data.get("responsable", ""),
                 data.get("fecha_inicio") or None, data.get("fecha_vencimiento") or None,
                 data.get("fecha_finalizacion") or None, data["estado"], data["prioridad"],
                 data.get("observaciones", "")),
            )
        if module == "vencimientos":
            return self.database.execute(
                """INSERT INTO vencimientos(cliente_id, impuesto, periodo, fecha_vencimiento,
                       estado, observaciones) VALUES (?, ?, ?, ?, ?, ?)""",
                (data.get("cliente_id"), data["impuesto"], data["periodo"],
                 data["fecha_vencimiento"], data["estado"], data.get("observaciones", "")),
            )
        return self.database.execute(
            """INSERT INTO honorarios(cliente_id, servicio, periodo, importe, estado,
                   fecha_emision, fecha_cobro, medio_pago, saldo_pendiente, observaciones)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["cliente_id"], data["servicio"], data["periodo"], float(data["importe"]),
             data["estado"], data.get("fecha_emision") or None, data.get("fecha_cobro") or None,
             data.get("medio_pago", ""), float(data.get("saldo_pendiente") or data["importe"]),
             data.get("observaciones", "")),
        )

    def update_status(self, module: str, record_id: int, status: str) -> None:
        table = self.TABLES[module]
        self.database.execute(f"UPDATE {table} SET estado = ? WHERE id = ?", (status, record_id))
