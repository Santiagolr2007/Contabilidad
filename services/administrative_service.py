from __future__ import annotations

import json
from datetime import date

from database import Database
from utils.formatters import normalize_period
from utils.validators import positive_number, required
from .ledger_service import LedgerService


class AdministrativeService:
    GENERIC_OFFSET = 1_000_000_000
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
        rows = [
            dict(row)
            for row in self.database.query(
                f"""
                SELECT d.*, COALESCE(c.nombre_razon_social, 'General') AS cliente_nombre
                FROM {table} d LEFT JOIN clientes c ON c.id = d.cliente_id
                ORDER BY {date_order}
                """
            )
        ]
        if module in ("tareas", "vencimientos", "honorarios"):
            rows.extend(self._ledger_rows(module))
        order_key = "fecha_vencimiento" if module in ("tareas", "vencimientos") else "periodo"
        rows.sort(key=lambda row: (str(row.get(order_key) or "9999-99-99"), str(row.get("cliente_nombre") or "").casefold()))
        return rows

    def _ledger_rows(self, module: str) -> list[dict]:
        sections = {
            "tareas": ("eventos",),
            "vencimientos": ("vencimientos_legajo",),
            "honorarios": ("pagos", "servicio_presupuesto"),
        }[module]
        placeholders = ",".join("?" for _ in sections)
        source = self.database.query(
            f"""SELECT r.*,c.nombre_razon_social cliente_nombre
                FROM cliente_legajo_registros r JOIN clientes c ON c.id=r.cliente_id
                WHERE r.seccion IN ({placeholders}) ORDER BY r.id DESC""",
            sections,
        )
        result = []
        for raw in source:
            row = dict(raw); data = json.loads(row.get("datos_json") or "{}")
            base = {"id": self.GENERIC_OFFSET + int(row["id"]), "cliente_id": row["cliente_id"], "cliente_nombre": row["cliente_nombre"], "_ledger_section": row["seccion"]}
            if module == "tareas":
                base.update({
                    "modulo": data.get("area", ""), "periodo": data.get("periodo", row.get("periodo", "")),
                    "titulo": data.get("tipo_evento", data.get("titulo", "")), "descripcion": data.get("descripcion", row.get("descripcion", "")),
                    "fecha_inicio": data.get("fecha", row.get("fecha", "")), "fecha_vencimiento": data.get("fecha_vencimiento", row.get("vencimiento", "")),
                    "fecha_cumplimiento": data.get("fecha_resolucion", ""), "estado": data.get("estado", row.get("estado", "")),
                    "prioridad": data.get("prioridad", ""), "medio": data.get("medio", ""),
                    "documentacion_vinculada": data.get("documentacion_vinculada", ""), "proximo_paso": data.get("proximo_paso", ""),
                    "observaciones": data.get("observaciones", ""),
                })
            elif module == "vencimientos":
                base.update({
                    "impuesto": data.get("impuesto_tramite", row.get("descripcion", "")), "organismo": data.get("organismo", ""),
                    "periodo": data.get("periodo", row.get("periodo", "")), "fecha_vencimiento": data.get("fecha_vencimiento", row.get("vencimiento", "")),
                    "tipo_vencimiento": data.get("tipo", ""), "estado": data.get("estado", row.get("estado", "")),
                    "fecha_cumplimiento": data.get("fecha_cumplimiento", data.get("fecha_presentacion", "")), "fecha_pago": data.get("fecha_pago", ""),
                    "importe": float(row.get("importe") or 0), "saldo": float(row.get("saldo") or 0), "observaciones": data.get("observaciones", ""),
                })
            elif row["seccion"] == "pagos":
                base.update({
                    "numero_presupuesto": data.get("numero_presupuesto", "Sin presupuesto asociado"),
                    "tipo_registro": "Honorario", "servicio": data.get("concepto", row.get("descripcion", "")), "periodo": data.get("periodo", row.get("periodo", "")),
                    "importe": float(data.get("importe_facturado") or row.get("importe") or 0), "importe_pagado": float(data.get("importe_cobrado") or 0),
                    "saldo_pendiente": float(data.get("saldo_pendiente") or row.get("saldo") or 0), "estado": data.get("estado_pago", row.get("estado", "")),
                    "fecha_vencimiento": data.get("fecha_vencimiento", row.get("vencimiento", "")), "fecha_cobro": data.get("fecha_cobro", ""),
                    "fecha_emision": data.get("fecha_emision", row.get("fecha", "")), "medio_pago": data.get("medio_pago", ""),
                    "comprobante_emitido": data.get("comprobante_emitido", ""), "tipo_comprobante": data.get("tipo_comprobante", ""),
                    "numero_comprobante": data.get("numero_comprobante", ""), "observaciones": data.get("observaciones", ""),
                })
            else:
                base.update({
                    "numero_presupuesto": data.get("numero_presupuesto", row.get("numero_presupuesto", "")),
                    "tipo_registro": "Presupuesto", "servicio": data.get("concepto", data.get("tipo_servicio", row.get("descripcion", ""))),
                    "periodo": data.get("periodo", row.get("periodo", "")), "importe": float(data.get("valor_presupuestado") or row.get("importe") or 0),
                    "importe_pagado": 0.0, "saldo_pendiente": float(data.get("valor_presupuestado") or row.get("saldo") or 0),
                    "estado": data.get("estado_presupuesto", row.get("estado", "")), "fecha_vencimiento": data.get("fecha_vencimiento", row.get("vencimiento", "")),
                    "fecha_emision": data.get("fecha_presupuesto", row.get("fecha", "")), "condiciones_presupuesto": data.get("condiciones_presupuesto", ""),
                    "observaciones": data.get("observaciones", ""),
                })
            result.append(base)
        return result

    def get(self, module: str, record_id: int) -> dict | None:
        if record_id >= self.GENERIC_OFFSET:
            return next((row for row in self._ledger_rows(module) if int(row["id"]) == record_id), None)
        table = self._table(module)
        row = self.database.query_one(
            f"SELECT * FROM {table} WHERE id = ?", (record_id,)
        )
        return dict(row) if row else None

    def create(self, module: str, data: dict) -> int:
        return self._save(module, data)

    def update(self, module: str, record_id: int, data: dict) -> None:
        if record_id >= self.GENERIC_OFFSET:
            self._update_ledger_record(module, record_id - self.GENERIC_OFFSET, data)
            return
        previous = self.get(module, record_id)
        if not previous:
            raise ValueError("El registro seleccionado ya no existe.")
        self._save(module, data, record_id)
        if module == "vencimientos":
            current = self.get(module, record_id) or {}
            audited = (
                "cliente_id", "impuesto", "organismo", "periodo", "fecha_vencimiento",
                "tipo_vencimiento", "estado", "importe", "saldo", "responsable", "observaciones",
            )
            changes = [
                (record_id, current.get("cliente_id"), field, str(previous.get(field) or ""),
                 str(current.get(field) or ""), data.get("responsable") or "NATALIA", "Modificación manual")
                for field in audited if str(previous.get(field) or "") != str(current.get(field) or "")
            ]
            if changes:
                self.database.executemany(
                    """INSERT INTO historial_vencimientos(vencimiento_id,cliente_id,campo,
                       valor_anterior,valor_nuevo,responsable,observaciones)
                       VALUES(?,?,?,?,?,?,?)""", changes,
                )

    def _update_ledger_record(self, module: str, ledger_id: int, data: dict) -> None:
        ledger = LedgerService(self.database)
        record = ledger.get_record(ledger_id)
        if not record: raise ValueError("El registro seleccionado ya no existe.")
        payload = dict(record["datos"])
        mappings = {
            "tareas": {"modulo":"area", "titulo":"tipo_evento", "fecha_inicio":"fecha", "fecha_cumplimiento":"fecha_resolucion"},
            "vencimientos": {"impuesto":"impuesto_tramite", "tipo_vencimiento":"tipo"},
        }
        if module in mappings:
            for key, value in data.items(): payload[mappings[module].get(key, key)] = value
        elif record["seccion"] == "pagos":
            map_fields = {"servicio":"concepto", "importe":"importe_facturado", "importe_pagado":"importe_cobrado", "estado":"estado_pago", "medio_pago":"medio_pago"}
            for key, value in data.items(): payload[map_fields.get(key, key)] = value
        else:
            map_fields = {"servicio":"concepto", "importe":"valor_presupuestado", "estado":"estado_presupuesto", "fecha_emision":"fecha_presupuesto"}
            for key, value in data.items(): payload[map_fields.get(key, key)] = value
        ledger.save_record(int(data.get("cliente_id") or record["cliente_id"]), record["seccion"], payload, ledger_id)

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
                data.get("obligatorio", "Según caso"),
                data.get("archivo_link", ""),
                data.get("observaciones", ""),
            )
            if record_id:
                self.database.execute(
                    """UPDATE documentacion SET cliente_id=?, periodo=?,
                       tipo_documento=?, estado=?, fecha_solicitud=?,
                       fecha_recepcion=?, obligatorio=?, archivo_link=?, observaciones=? WHERE id=?""",
                    (*values, record_id),
                )
                return record_id
            return self.database.execute(
                """INSERT INTO documentacion(cliente_id, periodo, tipo_documento,
                   estado, fecha_solicitud, fecha_recepcion, obligatorio, archivo_link, observaciones)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                data.get("medio", ""), data.get("documentacion_vinculada", ""),
                data.get("proximo_paso", ""), data.get("fecha_cumplimiento") or None,
            )
            if record_id:
                self.database.execute(
                    """UPDATE tareas SET cliente_id=?, modulo=?, periodo=?, titulo=?,
                       descripcion=?, responsable=?, fecha_inicio=?, fecha_vencimiento=?,
                       fecha_finalizacion=?, estado=?, prioridad=?, observaciones=?,
                       medio=?,documentacion_vinculada=?,proximo_paso=?,fecha_cumplimiento=?
                       WHERE id=?""",
                    (*values, record_id),
                )
                return record_id
            return self.database.execute(
                """INSERT INTO tareas(cliente_id, modulo, periodo, titulo, descripcion,
                   responsable, fecha_inicio, fecha_vencimiento, fecha_finalizacion,
                   estado, prioridad, observaciones,medio,documentacion_vinculada,
                   proximo_paso,fecha_cumplimiento)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                positive_number(data.get("importe") or 0, "Importe", allow_zero=True),
                positive_number(data.get("saldo") or 0, "Saldo", allow_zero=True),
                data.get("fecha_presentacion") or None, data.get("fecha_pago") or None,
                data.get("fecha_cumplimiento") or None,
            )
            if record_id:
                self.database.execute(
                    """UPDATE vencimientos SET cliente_id=?, impuesto=?, periodo=?,
                       fecha_vencimiento=?, organismo=?, tipo_vencimiento=?, estado=?,
                       responsable=?, observaciones=?,importe=?,saldo=?,fecha_presentacion=?,
                       fecha_pago=?,fecha_cumplimiento=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?""",
                    (*values, record_id),
                )
                return record_id
            return self.database.execute(
                """INSERT INTO vencimientos(cliente_id, impuesto, periodo,
                   fecha_vencimiento, organismo, tipo_vencimiento, estado,
                   responsable, observaciones,importe,saldo,fecha_presentacion,fecha_pago,
                   fecha_cumplimiento)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        paid = positive_number(data.get("importe_pagado") or max(amount-pending,0), "Importe pagado", allow_zero=True)
        if paid > amount:
            raise ValueError("El importe pagado no puede superar el importe total.")
        if abs((amount-paid)-pending) > .01:
            pending = max(amount-paid,0)
        period = normalize_period(data["periodo"]) if data.get("periodo") else ""
        duplicate = self.database.query_one(
            """SELECT id FROM honorarios WHERE cliente_id=? AND servicio=? AND periodo=?
               AND (? IS NULL OR id<>?) LIMIT 1""",
            (data["cliente_id"], required(data["servicio"], "Servicio"), period, record_id, record_id),
        )
        if duplicate:
            raise ValueError("Ya existe un honorario similar para este cliente.")
        budget_number = str(data.get("numero_presupuesto") or "").strip()
        if not budget_number:
            budget_number = "Sin presupuesto asociado"
        if budget_number.casefold() != "sin presupuesto asociado":
            linked = self.database.query_one(
                """SELECT id FROM cliente_legajo_registros WHERE cliente_id=?
                   AND seccion='servicio_presupuesto' AND numero_presupuesto=?""",
                (data["cliente_id"], budget_number),
            )
            if not linked:
                raise ValueError("El presupuesto seleccionado no pertenece al cliente.")
        values = (
            data["cliente_id"], required(data["servicio"], "Servicio"),
            period, amount, data["estado"],
            data.get("fecha_emision") or None, data.get("fecha_cobro") or None,
            data.get("medio_pago", ""), pending, data.get("observaciones", ""),
            data.get("tipo_registro") or "Honorario",data.get("fecha_vencimiento") or None,
            paid,data.get("numero_comprobante", ""), data.get("comprobante_emitido", ""),
            data.get("tipo_comprobante", ""), data.get("condiciones_presupuesto", ""),
            budget_number,
        )
        if record_id:
            self.database.execute(
                """UPDATE honorarios SET cliente_id=?, servicio=?, periodo=?, importe=?,
                   estado=?, fecha_emision=?, fecha_cobro=?, medio_pago=?,
                       saldo_pendiente=?, observaciones=?,tipo_registro=?,fecha_vencimiento=?,
                       importe_pagado=?,numero_comprobante=?,comprobante_emitido=?,
                       tipo_comprobante=?,condiciones_presupuesto=?,numero_presupuesto=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?""",
                (*values, record_id),
            )
            return record_id
        return self.database.execute(
            """INSERT INTO honorarios(cliente_id, servicio, periodo, importe, estado,
               fecha_emision, fecha_cobro, medio_pago, saldo_pendiente, observaciones,
               tipo_registro,fecha_vencimiento,importe_pagado,numero_comprobante,
               comprobante_emitido,tipo_comprobante,condiciones_presupuesto,numero_presupuesto)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )

    def delete(self, module: str, record_id: int) -> int:
        if record_id >= self.GENERIC_OFFSET:
            ledger_id = record_id - self.GENERIC_OFFSET
            record = LedgerService(self.database).get_record(ledger_id)
            if not record: return 0
            LedgerService(self.database).delete_record(int(record["cliente_id"]), ledger_id)
            return 1
        table = self._table(module)
        with self.database.connection() as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE id = ?", (record_id,)
            )
            return int(cursor.rowcount)

    def update_status(
        self, module: str, record_id: int, status: str,
        effective_date: str | None = None, amount_paid: float | None = None,
    ) -> None:
        """Actualiza estados administrativos y sus datos dependientes en una operación."""
        self._table(module)
        when = effective_date or date.today().isoformat()
        if record_id >= self.GENERIC_OFFSET:
            ledger_id = record_id - self.GENERIC_OFFSET
            ledger = LedgerService(self.database); record = ledger.get_record(ledger_id)
            if not record: raise ValueError("El registro seleccionado ya no existe.")
            payload = dict(record["datos"])
            if module == "tareas":
                payload["estado"] = status
                if status == "Cumplimentada": payload["fecha_resolucion"] = when
            elif module == "vencimientos":
                payload["estado"] = status
                if status == "Cumplido": payload["fecha_cumplimiento"] = when
                if status == "Pagado": payload["fecha_pago"] = when
            elif record["seccion"] == "pagos":
                total = float(payload.get("importe_facturado") or record.get("importe") or 0)
                paid = total if status == "Cobrado" else float(amount_paid or payload.get("importe_cobrado") or 0)
                if status == "Cobro parcial" and not 0 < paid < total: raise ValueError("El cobro parcial debe ser mayor a cero y menor al total facturado.")
                payload.update({"estado_pago":status, "importe_cobrado":paid, "saldo_pendiente":max(total-paid,0)})
                if status in ("Cobrado", "Cobro parcial"): payload["fecha_cobro"] = when
            else:
                payload["estado_presupuesto"] = status
            ledger.save_record(int(record["cliente_id"]), record["seccion"], payload, ledger_id)
            return
        if module == "tareas":
            completed = status.casefold() == "cumplimentada"
            self.database.execute(
                """UPDATE tareas SET estado=?,fecha_cumplimiento=?,fecha_finalizacion=?
                   WHERE id=?""",
                (status, when if completed else None, when if completed else None, record_id),
            )
            return
        if module == "vencimientos":
            normalized = status.casefold()
            completion = when if normalized == "cumplido" else None
            payment = when if normalized == "pagado" else None
            self.database.execute(
                """UPDATE vencimientos SET estado=?,fecha_cumplimiento=?,fecha_presentacion=?,
                   fecha_pago=?,saldo=CASE WHEN ?='pagado' THEN 0 ELSE saldo END,
                   actualizado_en=CURRENT_TIMESTAMP WHERE id=?""",
                (status, completion, completion, payment, normalized, record_id),
            )
            return
        if module == "honorarios":
            current = self.get(module, record_id)
            if not current:
                raise ValueError("El honorario seleccionado ya no existe.")
            total = float(current.get("importe") or 0)
            paid = total if status == "Cobrado" else (
                float(amount_paid or 0) if status == "Cobro parcial"
                else float(current.get("importe_pagado") or 0)
            )
            if status == "Cobro parcial" and not 0 < paid < total:
                raise ValueError("El cobro parcial debe ser mayor a cero y menor al total facturado.")
            if status in ("Bonificado", "Anulado", "No corresponde"):
                paid = 0
                balance = 0
            else:
                balance = max(total - paid, 0)
            self.database.execute(
                """UPDATE honorarios SET estado=?,importe_pagado=?,saldo_pendiente=?,
                   fecha_cobro=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?""",
                (status, paid, balance, when if status in ("Cobrado", "Cobro parcial") else None, record_id),
            )
            return
        if module == "documentacion":
            self.database.execute(
                "UPDATE documentacion SET estado=?,fecha_recepcion=? WHERE id=?",
                (status, when if status.casefold() in ("recibido", "recibida") else None, record_id),
            )
            return
        self.database.execute(
            f"UPDATE {self._table(module)} SET estado=? WHERE id=?", (status, record_id)
        )
