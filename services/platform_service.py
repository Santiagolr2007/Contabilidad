from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from database import Database
from utils.formatters import normalize_date, normalize_period


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def number(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^0-9,.-]", "", str(value)).strip()
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parsed_date(value: object) -> str:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date().isoformat()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"Fecha inválida: {text or 'vacía'}")
    return parsed.date().isoformat()


class PlatformService:
    MP_ALIASES = {
        "fecha": ("fecha", "date", "fecha de operacion", "fecha operacion", "creation date"),
        "descripcion": ("descripcion", "detalle", "concepto", "motivo"),
        "tipo_movimiento": ("tipo de movimiento", "tipo movimiento", "movement type", "tipo de operacion"),
        "operacion": ("operacion", "tipo operacion", "operation"),
        "contraparte": ("contraparte", "nombre", "pagador", "receptor", "origen", "destino"),
        "contraparte_documento": ("cuit", "cuil", "documento", "identificacion contraparte"),
        "medio_pago": ("medio de pago", "payment method", "metodo de pago"),
        "id_operacion": ("id de operacion", "id operacion", "operation id", "numero de operacion"),
        "id_movimiento": ("id de movimiento", "id movimiento", "movement id"),
        "referencia": ("referencia", "reference"), "moneda": ("moneda", "currency"),
        "importe_bruto": ("importe bruto", "monto bruto", "gross amount", "importe", "monto"),
        "comisiones": ("comision", "comisiones", "fee"), "retenciones": ("retencion", "retenciones"),
        "percepciones": ("percepcion", "percepciones"), "impuestos": ("impuesto", "impuestos", "taxes"),
        "importe_neto": ("importe neto", "monto neto", "net amount", "neto"), "saldo": ("saldo", "balance"),
        "estado": ("estado", "status"),
    }
    ML_ALIASES = {
        "fecha": ("fecha", "fecha de venta", "fecha operacion", "date"),
        "tipo_operacion": ("tipo de operacion", "operacion", "tipo"),
        "tipo_comprobante": ("tipo de comprobante", "comprobante", "tipo comprobante"),
        "numero_comprobante": ("numero de comprobante", "nro comprobante", "numero factura"),
        "estado": ("estado", "status"), "contraparte": ("cliente", "comprador", "proveedor", "vendedor", "nombre"),
        "contraparte_documento": ("cuit", "cuil", "documento"), "producto": ("producto", "titulo", "descripcion", "item"),
        "cantidad": ("cantidad", "units", "unidades"), "precio_unitario": ("precio unitario", "unit price", "precio"),
        "importe_bruto": ("importe bruto", "total", "monto bruto", "importe"), "descuentos": ("descuento", "descuentos"),
        "comisiones": ("comision", "comisiones", "cargo por venta"), "envios": ("envio", "envios", "costo de envio"),
        "retenciones": ("retencion", "retenciones"), "percepciones": ("percepcion", "percepciones"),
        "importe_neto": ("importe neto", "neto", "monto neto"), "moneda": ("moneda", "currency"),
        "id_operacion": ("id operacion", "id de operacion", "operation id"), "id_venta": ("id venta", "id de venta", "sale id"),
        "id_publicacion": ("id publicacion", "id de publicacion", "item id"), "medio_cobro": ("medio de cobro", "metodo de pago"),
        "observaciones": ("observaciones", "nota", "comentario"),
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def preview_file(self, path: Path, source: str) -> dict:
        frame = self._read(path)
        aliases = self.MP_ALIASES if source == "mp" else self.ML_ALIASES
        mapping = self._mapping(frame.columns, aliases)
        missing = [field for field in ("fecha", "importe_bruto") if field not in mapping]
        if source == "mp" and "importe_bruto" in missing and "importe_neto" in mapping:
            missing.remove("importe_bruto")
        return {"columns": list(map(str, frame.columns)), "mapping": mapping, "missing": missing, "rows": len(frame)}

    def was_imported(self, client_id: int, path: Path, source_prefix: str) -> bool:
        return bool(self.database.query_one(
            "SELECT id FROM historial_importaciones_plataformas WHERE cliente_id=? AND nombre_archivo=? AND fuente LIKE ? LIMIT 1",
            (client_id, path.name, f"{source_prefix}%"),
        ))

    @staticmethod
    def _read(path: Path) -> pd.DataFrame:
        if path.suffix.casefold() == ".xlsx":
            sheets = pd.read_excel(path, sheet_name=None, dtype=object)
            frames = []
            for name, frame in sheets.items():
                if not frame.empty:
                    frame = frame.copy(); frame["__hoja_origen"] = name; frames.append(frame)
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if path.suffix.casefold() == ".csv":
            for encoding in ("utf-8-sig", "latin-1"):
                try:
                    return pd.read_csv(path, sep=None, engine="python", dtype=object, encoding=encoding)
                except UnicodeDecodeError:
                    continue
        raise ValueError("El archivo debe ser Excel (.xlsx) o CSV (.csv).")

    @staticmethod
    def _mapping(columns, aliases: dict) -> dict:
        normalized_columns = {normalized(column): column for column in columns}
        result = {}
        for field, candidates in aliases.items():
            for candidate in candidates:
                exact = normalized_columns.get(normalized(candidate))
                if exact is not None:
                    result[field] = exact; break
            if field not in result:
                for norm_column, original in normalized_columns.items():
                    if any(normalized(candidate) in norm_column for candidate in candidates):
                        result[field] = original; break
        return result

    @staticmethod
    def classify_mp(text: str) -> str:
        value = normalized(text)
        rules = (
            ("Contracargo", ("contracargo", "chargeback")), ("Devolución", ("devolucion", "reembolso", "refund")),
            ("Transferencia recibida", ("transferencia recibida", "dinero recibido", "transfer in")),
            ("Transferencia realizada", ("transferencia enviada", "transferencia realizada", "envio de dinero", "transfer out")),
            ("Comisión", ("comision", "cargo por cobro", "fee")), ("Retención", ("retencion",)),
            ("Percepción", ("percepcion",)), ("Impuesto", ("impuesto", "iva", "iibb")),
            ("Interés", ("interes", "rendimiento")), ("Cobranza", ("cobro", "venta", "payment received")),
            ("Pago", ("pago", "compra", "payment sent")), ("Ajuste", ("ajuste", "adjustment")),
        )
        for label, terms in rules:
            if any(term in value for term in terms): return label
        return "A revisar"

    def _new_history(self, client_id: int, source: str, path: Path) -> int:
        return self.database.execute(
            "INSERT INTO historial_importaciones_plataformas(cliente_id,fuente,nombre_archivo) VALUES(?,?,?)",
            (client_id, source, path.name),
        )

    def _finish_history(self, import_id: int, imported: int, duplicates: int, review: int, rejected: int, periods: set[str]) -> None:
        state = "Importado con advertencias" if review or rejected else ("Duplicado" if not imported and duplicates else "Importado correctamente")
        self.database.execute(
            """UPDATE historial_importaciones_plataformas SET importados=?,duplicados=?,revisar=?,rechazados=?,periodo_detectado=?,estado=? WHERE id=?""",
            (imported, duplicates, review, rejected, ", ".join(sorted(periods)), state, import_id),
        )

    def import_mercado_pago(self, path: Path, client_id: int, manual_mapping: dict | None = None) -> dict:
        if not client_id: raise ValueError("Debe seleccionar un cliente.")
        frame = self._read(path)
        if frame.empty: raise ValueError("El archivo no contiene movimientos.")
        mapping = {**self._mapping(frame.columns, self.MP_ALIASES), **(manual_mapping or {})}
        missing = [field for field in ("fecha", "importe_bruto") if field not in mapping]
        if "importe_bruto" in missing and "importe_neto" in mapping: missing.remove("importe_bruto")
        if missing: raise ValueError("No se reconocieron las columnas: " + ", ".join(missing) + ". Columnas disponibles: " + ", ".join(map(str, frame.columns)))
        import_id = self._new_history(client_id, "Mercado Pago", path)
        imported = duplicates = review = rejected = 0; periods = set(); messages = []
        for index, source in frame.iterrows():
            try:
                def get(field, default=""):
                    column = mapping.get(field); value = source.get(column, default) if column else default
                    return "" if pd.isna(value) else value
                movement_date = parsed_date(get("fecha")); period = movement_date[:7]; periods.add(period)
                gross = number(get("importe_bruto", get("importe_neto"))); net = number(get("importe_neto", gross))
                description = str(get("descripcion")); operation = str(get("operacion")); original_type = str(get("tipo_movimiento"))
                classification = self.classify_mp(" ".join((description, operation, original_type, str(get("medio_pago")))))
                if classification == "A revisar": review += 1
                direction = "Egreso" if net < 0 or classification in ("Pago", "Transferencia realizada", "Comisión", "Retención", "Percepción", "Impuesto", "Contracargo") else "Ingreso"
                operation_id = str(get("id_operacion")); movement_id = str(get("id_movimiento"))
                duplicate = self.database.query_one(
                    """SELECT id FROM movimientos_mercado_pago WHERE cliente_id=? AND
                       ((?<>'' AND id_operacion=?) OR (?<>'' AND id_movimiento=?) OR (fecha=? AND importe_neto=? AND descripcion=?)) LIMIT 1""",
                    (client_id, operation_id, operation_id, movement_id, movement_id, movement_date, net, description),
                )
                if duplicate: duplicates += 1; continue
                self.database.execute(
                    """INSERT INTO movimientos_mercado_pago(cliente_id,fecha,periodo,descripcion,tipo_movimiento,operacion,contraparte,contraparte_documento,medio_pago,id_operacion,id_movimiento,referencia,moneda,importe_bruto,comisiones,retenciones,percepciones,impuestos,importe_neto,saldo,ingreso_egreso,estado,observaciones,nombre_archivo_origen,id_importacion)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (client_id,movement_date,period,description,classification,operation,str(get("contraparte")),str(get("contraparte_documento")),str(get("medio_pago")),operation_id,movement_id,str(get("referencia")),str(get("moneda") or "ARS"),gross,number(get("comisiones")),number(get("retenciones")),number(get("percepciones")),number(get("impuestos")),net,number(get("saldo")),direction,str(get("estado")),"",path.name,import_id),
                ); imported += 1
            except Exception as error:
                rejected += 1
                if len(messages) < 10: messages.append(f"Fila {index + 2}: {error}")
        self._finish_history(import_id, imported, duplicates, review, rejected, periods)
        return {"import_id": import_id, "read": len(frame), "imported": imported, "duplicates": duplicates, "review": review, "rejected": rejected, "messages": messages}

    def import_mercado_libre(self, path: Path, client_id: int, source_kind: str = "Ventas", manual_mapping: dict | None = None) -> dict:
        if not client_id: raise ValueError("Debe seleccionar un cliente.")
        frame = self._read(path)
        if frame.empty: raise ValueError("El archivo no contiene operaciones.")
        mapping = {**self._mapping(frame.columns, self.ML_ALIASES), **(manual_mapping or {})}
        missing = [field for field in ("fecha", "importe_bruto") if field not in mapping]
        if missing: raise ValueError("No se reconocieron las columnas: " + ", ".join(missing) + ". Columnas disponibles: " + ", ".join(map(str, frame.columns)))
        import_id = self._new_history(client_id, f"Mercado Libre {source_kind}", path)
        imported = duplicates = review = rejected = 0; periods = set(); messages = []
        for index, source in frame.iterrows():
            try:
                def get(field, default=""):
                    column = mapping.get(field); value = source.get(column, default) if column else default
                    return "" if pd.isna(value) else value
                operation_date = parsed_date(get("fecha")); period = operation_date[:7]; periods.add(period)
                type_text = str(get("tipo_operacion") or source_kind[:-1]); voucher = str(get("tipo_comprobante")); state = str(get("estado"))
                combined = normalized(" ".join((type_text, voucher, state, str(get("observaciones")))))
                if "nota de credito" in combined or "devol" in combined: operation_type = "Nota de crédito"
                elif "anul" in combined or "cancel" in combined: operation_type = "Anulación"
                elif source_kind.casefold().startswith("compra") or "compra" in combined: operation_type = "Compra"
                else: operation_type = "Venta"
                gross = abs(number(get("importe_bruto"))); net = number(get("importe_neto", gross))
                if not get("importe_neto"): net = gross - abs(number(get("descuentos"))) - abs(number(get("comisiones"))) - abs(number(get("envios"))) - abs(number(get("retenciones"))) - abs(number(get("percepciones")))
                if operation_type in ("Nota de crédito", "Anulación"): net = -abs(net)
                operation_id, sale_id, voucher_number = str(get("id_operacion")), str(get("id_venta")), str(get("numero_comprobante"))
                duplicate = self.database.query_one(
                    """SELECT id FROM operaciones_mercado_libre WHERE cliente_id=? AND
                       ((?<>'' AND id_operacion=?) OR (?<>'' AND id_venta=?) OR (?<>'' AND numero_comprobante=?)) LIMIT 1""",
                    (client_id, operation_id, operation_id, sale_id, sale_id, voucher_number, voucher_number),
                )
                if duplicate: duplicates += 1; continue
                if not operation_id and not sale_id and not voucher_number: review += 1
                self.database.execute(
                    """INSERT INTO operaciones_mercado_libre(cliente_id,fecha,periodo,tipo_operacion,tipo_comprobante,numero_comprobante,estado,contraparte,contraparte_documento,producto,cantidad,precio_unitario,importe_bruto,descuentos,comisiones,envios,retenciones,percepciones,importe_neto,moneda,id_operacion,id_venta,id_publicacion,medio_cobro,observaciones,nombre_archivo_origen,id_importacion)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (client_id,operation_date,period,operation_type,voucher,voucher_number,state,str(get("contraparte")),str(get("contraparte_documento")),str(get("producto")),number(get("cantidad")),number(get("precio_unitario")),gross,number(get("descuentos")),number(get("comisiones")),number(get("envios")),number(get("retenciones")),number(get("percepciones")),net,str(get("moneda") or "ARS"),operation_id,sale_id,str(get("id_publicacion")),str(get("medio_cobro")),str(get("observaciones")),path.name,import_id),
                ); imported += 1
            except Exception as error:
                rejected += 1
                if len(messages) < 10: messages.append(f"Fila {index + 2}: {error}")
        self._finish_history(import_id, imported, duplicates, review, rejected, periods)
        return {"import_id": import_id, "read": len(frame), "imported": imported, "duplicates": duplicates, "review": review, "rejected": rejected, "messages": messages}

    def list_mp(self, client_id: int, period: str = "", movement_type: str = "", direction: str = "", search: str = "") -> list[dict]:
        conditions = ["cliente_id=?"]; params: list = [client_id]
        if period: conditions.append("periodo=?"); params.append(normalize_period(period))
        if movement_type and movement_type != "Todos": conditions.append("tipo_movimiento=?"); params.append(movement_type)
        if direction and direction != "Todos": conditions.append("ingreso_egreso=?"); params.append(direction)
        if search: conditions.append("(contraparte LIKE ? OR descripcion LIKE ? OR id_operacion LIKE ?)"); params.extend([f"%{search}%"]*3)
        return [dict(row) for row in self.database.query(f"SELECT * FROM movimientos_mercado_pago WHERE {' AND '.join(conditions)} ORDER BY fecha DESC,id DESC", params)]

    def mp_summary(self, client_id: int) -> list[dict]:
        rows = [dict(row) for row in self.database.query(
            """SELECT m.periodo,
                SUM(CASE WHEN ingreso_egreso='Ingreso' THEN ABS(importe_neto) ELSE 0 END) total_ingresos,
                SUM(CASE WHEN ingreso_egreso='Egreso' THEN ABS(importe_neto) ELSE 0 END) total_egresos,
                SUM(CASE WHEN tipo_movimiento='Cobranza' THEN ABS(importe_neto) ELSE 0 END) cobranzas,
                SUM(CASE WHEN tipo_movimiento='Pago' THEN ABS(importe_neto) ELSE 0 END) pagos,
                SUM(CASE WHEN tipo_movimiento='Transferencia recibida' THEN ABS(importe_neto) ELSE 0 END) transferencias_recibidas,
                SUM(CASE WHEN tipo_movimiento='Transferencia realizada' THEN ABS(importe_neto) ELSE 0 END) transferencias_realizadas,
                SUM(CASE WHEN tipo_movimiento='Interés' THEN ABS(importe_neto) ELSE 0 END) intereses,
                SUM(ABS(comisiones)) comisiones,SUM(ABS(retenciones)) retenciones,SUM(ABS(percepciones)) percepciones,SUM(ABS(impuestos)) impuestos,
                (SELECT s.saldo FROM movimientos_mercado_pago s WHERE s.cliente_id=m.cliente_id AND s.periodo=m.periodo ORDER BY s.fecha,s.id LIMIT 1) saldo_inicial,
                (SELECT s.saldo FROM movimientos_mercado_pago s WHERE s.cliente_id=m.cliente_id AND s.periodo=m.periodo ORDER BY s.fecha DESC,s.id DESC LIMIT 1) saldo_final,
                COUNT(*) cantidad_movimientos
                FROM movimientos_mercado_pago m WHERE m.cliente_id=? GROUP BY m.periodo ORDER BY m.periodo DESC""", (client_id,))]
        for row in rows:
            row["diferencia_control"] = round(
                float(row["saldo_final"] or 0) - float(row["saldo_inicial"] or 0)
                - float(row["total_ingresos"] or 0) + float(row["total_egresos"] or 0), 2
            )
            row["observaciones"] = "Revisar diferencia" if abs(row["diferencia_control"]) > .01 else "OK"
        return rows

    def mp_ranking(self, client_id: int, direction: str) -> list[dict]:
        return [dict(row) for row in self.database.query(
            """SELECT contraparte,contraparte_documento,COUNT(*) cantidad_movimientos,
                SUM(ABS(importe_bruto)) total_bruto,SUM(ABS(importe_neto)) total_neto,
                MAX(ABS(importe_neto)) movimiento_mas_alto,MAX(fecha) ultima_fecha
                FROM movimientos_mercado_pago WHERE cliente_id=? AND ingreso_egreso=?
                GROUP BY contraparte,contraparte_documento ORDER BY total_neto DESC""", (client_id,direction))]

    def list_ml(self, client_id: int, period: str = "", operation_type: str = "", search: str = "") -> list[dict]:
        conditions = ["cliente_id=?"]; params: list = [client_id]
        if period: conditions.append("periodo=?"); params.append(normalize_period(period))
        if operation_type and operation_type != "Todos": conditions.append("tipo_operacion=?"); params.append(operation_type)
        if search: conditions.append("(contraparte LIKE ? OR producto LIKE ? OR numero_comprobante LIKE ?)"); params.extend([f"%{search}%"]*3)
        return [dict(row) for row in self.database.query(f"SELECT * FROM operaciones_mercado_libre WHERE {' AND '.join(conditions)} ORDER BY fecha DESC,id DESC", params)]

    def ml_summary(self, client_id: int) -> list[dict]:
        return [dict(row) for row in self.database.query(
            """SELECT periodo,
                SUM(CASE WHEN tipo_operacion='Venta' THEN importe_bruto ELSE 0 END) ventas_brutas,
                SUM(CASE WHEN tipo_operacion='Nota de crédito' THEN ABS(importe_neto) ELSE 0 END) notas_credito,
                SUM(CASE WHEN tipo_operacion IN ('Anulación','Devolución') THEN ABS(importe_neto) ELSE 0 END) anulaciones_devoluciones,
                SUM(CASE WHEN tipo_operacion IN ('Venta','Nota de crédito','Anulación') THEN importe_neto ELSE 0 END) ventas_netas,
                SUM(ABS(comisiones)) comisiones,SUM(ABS(envios)) envios,SUM(ABS(retenciones)) retenciones,SUM(ABS(percepciones)) percepciones,COUNT(*) cantidad_operaciones
                FROM operaciones_mercado_libre WHERE cliente_id=? GROUP BY periodo ORDER BY periodo DESC""", (client_id,))]

    def imports(self, client_id: int | None = None) -> list[dict]:
        condition = "WHERE h.cliente_id=?" if client_id else ""; params = (client_id,) if client_id else ()
        return [dict(row) for row in self.database.query(f"SELECT h.*,c.nombre_razon_social cliente FROM historial_importaciones_plataformas h JOIN clientes c ON c.id=h.cliente_id {condition} ORDER BY h.fecha_importacion DESC", params)]

    def delete_import(self, import_id: int, client_id: int) -> int:
        with self.database.connection() as connection:
            mp = connection.execute("DELETE FROM movimientos_mercado_pago WHERE id_importacion=? AND cliente_id=?", (import_id,client_id)).rowcount
            ml = connection.execute("DELETE FROM operaciones_mercado_libre WHERE id_importacion=? AND cliente_id=?", (import_id,client_id)).rowcount
            connection.execute("UPDATE historial_importaciones_plataformas SET estado='A revisar',observaciones='Datos importados eliminados por el usuario' WHERE id=? AND cliente_id=?", (import_id,client_id))
            return int(mp + ml)

    def delete_period(self, source: str, client_id: int, period: str) -> int:
        table = "movimientos_mercado_pago" if source == "mp" else "operaciones_mercado_libre"
        with self.database.connection() as connection:
            return int(connection.execute(f"DELETE FROM {table} WHERE cliente_id=? AND periodo=?", (client_id, normalize_period(period))).rowcount)

    def delete_all(self, source: str, client_id: int) -> int:
        table = "movimientos_mercado_pago" if source == "mp" else "operaciones_mercado_libre"
        with self.database.connection() as connection:
            return int(connection.execute(f"DELETE FROM {table} WHERE cliente_id=?", (client_id,)).rowcount)

    def update_mp_classification(self, movement_id: int, classification: str) -> None:
        self.database.execute("UPDATE movimientos_mercado_pago SET tipo_movimiento=?,clasificacion_manual=? WHERE id=?", (classification, classification, movement_id))
