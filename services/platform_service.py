from __future__ import annotations

import csv
import io
import json
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
        "fecha": ("release date", "fecha de liberacion", "fecha", "date", "fecha de operacion", "fecha operacion", "creation date"),
        "descripcion": ("descripcion", "detalle", "concepto", "motivo"),
        "tipo_movimiento": ("transaction type", "tipo de movimiento", "tipo movimiento", "movement type", "tipo de operacion"),
        "operacion": ("operacion", "tipo operacion", "operation"),
        "contraparte": ("contraparte", "nombre", "pagador", "receptor", "origen", "destino"),
        "contraparte_documento": ("cuit", "cuil", "documento", "identificacion contraparte"),
        "medio_pago": ("medio de pago", "payment method", "metodo de pago"),
        "id_operacion": ("reference id", "id de referencia", "id de operacion", "id operacion", "operation id", "numero de operacion"),
        "id_movimiento": ("id de movimiento", "id movimiento", "movement id"),
        "referencia": ("referencia", "reference"), "moneda": ("moneda", "currency"),
        "importe_bruto": ("importe bruto", "monto bruto", "gross amount", "importe", "monto"),
        "comisiones": ("comision", "comisiones", "fee"), "retenciones": ("retencion", "retenciones"),
        "percepciones": ("percepcion", "percepciones"), "impuestos": ("impuesto", "impuestos", "taxes"),
        "importe_neto": ("transaction net amount", "importe neto", "monto neto", "net amount", "neto"),
        "saldo": ("partial balance", "saldo parcial", "saldo", "balance"),
        "estado": ("estado", "status"),
    }
    ML_ALIASES = {
        "fecha": ("fecha", "fecha de venta", "fecha operacion", "date"),
        "tipo_operacion": ("tipo de operacion", "operacion", "tipo"),
        "tipo_comprobante": ("tipo de comprobante", "comprobante", "tipo comprobante"),
        "numero_comprobante": ("numero de comprobante", "nro comprobante", "numero factura"),
        "estado": ("estado de venta", "estado", "status"), "contraparte": ("cliente", "comprador", "proveedor", "vendedor", "nombre"),
        "contraparte_documento": ("tipo y numero de documento", "dni", "cuit", "cuil", "documento"),
        "producto": ("titulo de la publicacion", "producto", "titulo", "descripcion", "item"),
        "cantidad": ("cantidad", "units", "unidades"), "precio_unitario": ("precio unitario", "unit price", "precio"),
        "importe_bruto": ("ingresos por productos ars", "importe bruto", "monto bruto", "importe"),
        "descuentos": ("descuentos y bonificaciones", "descuento", "descuentos"),
        "comisiones": ("cargo por venta", "comision", "comisiones"),
        "envios": ("costos de envio ars", "envio", "envios", "costo de envio"),
        "retenciones": ("retencion", "retenciones"), "percepciones": ("percepcion", "percepciones"),
        "importe_neto": ("total ars", "importe neto", "neto", "monto neto", "total"), "moneda": ("moneda", "currency"),
        "id_operacion": ("numero de venta", "de venta", "id operacion", "id de operacion", "operation id"),
        "id_venta": ("numero de venta", "de venta", "id venta", "id de venta", "sale id"),
        "id_publicacion": ("numero de publicacion", "de publicacion", "id publicacion", "id de publicacion", "item id"), "medio_cobro": ("medio de cobro", "metodo de pago"),
        "observaciones": ("observaciones", "nota", "comentario"),
        "sku": ("sku",), "variante": ("variante",),
        "ingresos_envio": ("ingresos por envio ars", "ingresos por envio"),
        "costo_fijo": ("costo fijo",), "costo_cuotas": ("costo por ofrecer cuotas", "costo por cuotas"),
        "costo_envio": ("costos de envio ars", "costo de envio"), "impuestos": ("impuestos", "impuesto"),
        "anulaciones_reembolsos": ("anulaciones y reembolsos ars", "anulaciones y reembolsos", "reembolsos"),
        "condicion_fiscal_comprador": ("condicion fiscal iva", "condicion fiscal"),
        "direccion_facturacion": ("direccion", "direccion de facturacion"),
        "domicilio_entrega": ("domicilio", "domicilio de entrega"), "ciudad": ("ciudad",),
        "provincia": ("provincia", "estado 2", "estado entrega"), "codigo_postal": ("codigo postal",),
        "pais": ("pais",), "reclamo_abierto": ("reclamo abierto",), "reclamo_cerrado": ("reclamo cerrado",),
        "con_mediacion": ("con mediacion", "mediacion"),
        "descripcion_estado": ("descripcion del estado",), "paquete_multiple": ("paquete de varios productos",),
        "pertenece_kit": ("pertenece a un kit",), "mes_facturacion": ("mes de facturacion de tus cargos",),
        "orden_compra": ("orden de compra",), "venta_publicidad": ("venta por publicidad",),
        "cuotas_agregadas": ("tiene cuotas agregadas",), "factura_adjunta": ("factura adjunta",),
        "datos_facturacion_comprador": ("datos personales o de empresa",), "negocio": ("negocio",),
        "forma_entrega": ("forma de entrega",), "fecha_en_camino": ("fecha en camino",),
        "fecha_entregado": ("fecha entregado",), "transportista": ("transportista",),
        "numero_seguimiento": ("numero de seguimiento",), "url_seguimiento": ("url de seguimiento",),
        "revisado_ml": ("revisado por mercado libre",), "fecha_revision": ("fecha de revision",),
        "dinero_favor": ("dinero a favor",), "resultado_reclamo": ("resultado",),
        "destino_reclamo": ("destino",), "motivo_resultado": ("motivo del resultado",),
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def preview_file(
        self, path: Path, source: str, header_row: int | None = None,
        sheet_name: str = "",
    ) -> dict:
        frame = self._read(path, source, header_row, sheet_name)
        aliases = self.MP_ALIASES if source == "mp" else self.ML_ALIASES
        mapping = self._mapping(frame.columns, aliases)
        missing = [field for field in ("fecha", "importe_bruto") if field not in mapping]
        if source == "mp" and "importe_bruto" in missing and "importe_neto" in mapping:
            missing.remove("importe_bruto")
        return {
            "columns": list(map(str, frame.columns)), "mapping": mapping,
            "missing": missing, "rows": len(frame),
            "sheet": frame.attrs.get("sheet", ""),
            "header_row": frame.attrs.get("header_row", 1),
            "summary": frame.attrs.get("summary", {}),
            "preview": [{"_source_index": int(index), **row} for index,row in enumerate(frame.head(20).fillna("").to_dict("records"))],
        }

    def was_imported(self, client_id: int, path: Path, source_prefix: str) -> bool:
        return bool(self.database.query_one(
            "SELECT id FROM historial_importaciones_plataformas WHERE cliente_id=? AND nombre_archivo=? AND fuente LIKE ? LIMIT 1",
            (client_id, path.name, f"{source_prefix}%"),
        ))

    @staticmethod
    def _unique_headers(values: list[object]) -> list[str]:
        counts: dict[str, int] = {}
        result = []
        for index, value in enumerate(values):
            base = str(value).strip() if str(value).strip() else f"Columna {index + 1}"
            counts[base] = counts.get(base, 0) + 1
            result.append(base if counts[base] == 1 else f"{base} {counts[base]}")
        return result

    @classmethod
    def _read(
        cls, path: Path, source: str = "", header_row: int | None = None,
        sheet_name: str = "",
    ) -> pd.DataFrame:
        suffix = path.suffix.casefold()
        if suffix in (".xlsx", ".xls"):
            raw_sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
        elif suffix == ".csv":
            raw = None
            for encoding in ("utf-8-sig", "latin-1"):
                try:
                    raw = path.read_text(encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if raw is None:
                raise ValueError("No se pudo reconocer la codificación del archivo.")
            candidates = (";", "\t", "|", ",")
            lines = raw.splitlines()[:50]
            delimiter = max(candidates, key=lambda item: max((line.count(item) for line in lines), default=0))
            rows = list(csv.reader(io.StringIO(raw), delimiter=delimiter))
            width = max((len(row) for row in rows), default=0)
            raw_sheets = {"CSV": pd.DataFrame([row + [""] * (width - len(row)) for row in rows])}
        else:
            raise ValueError("El archivo debe ser Excel (.xls o .xlsx) o CSV (.csv).")

        aliases = cls.MP_ALIASES if source == "mp" else cls.ML_ALIASES if source == "ml" else {**cls.MP_ALIASES, **cls.ML_ALIASES}
        if sheet_name:
            raw_sheets = {name:frame for name,frame in raw_sheets.items() if name == sheet_name}
            if not raw_sheets:
                raise ValueError("La hoja indicada no existe en el archivo.")
        best = None
        for sheet_name, raw_frame in raw_sheets.items():
            row_indexes = [header_row - 1] if header_row else range(min(80, len(raw_frame)))
            for row_index in row_indexes:
                if row_index < 0 or row_index >= len(raw_frame):
                    continue
                headers = cls._unique_headers(raw_frame.iloc[row_index].fillna("").tolist())
                mapping = cls._mapping(headers, aliases)
                score = len(mapping) + (4 if "fecha" in mapping else 0)
                if source == "mp":
                    score += 4 if ("importe_neto" in mapping or "importe_bruto" in mapping) else 0
                else:
                    score += 4 if "importe_bruto" in mapping else 0
                if best is None or score > best[0]:
                    best = (score, sheet_name, row_index, raw_frame, headers)
        if best is None:
            raise ValueError("El archivo no contiene filas legibles.")
        _, sheet_name, row_index, raw_frame, headers = best
        data = raw_frame.iloc[row_index + 1 :].copy()
        data.columns = headers
        data = data.dropna(how="all").reset_index(drop=True)
        data["__hoja_origen"] = sheet_name
        summary: dict[str, float] = {}
        if source == "mp" and row_index > 0:
            top = raw_frame.iloc[:row_index].fillna("")
            for row in range(len(top)):
                values = top.iloc[row].tolist()
                for column, value in enumerate(values):
                    label = normalized(value)
                    summary_key = {
                        "initial balance": "saldo_inicial", "saldo inicial": "saldo_inicial",
                        "credits": "creditos", "creditos": "creditos",
                        "debits": "debitos", "debitos": "debitos",
                        "final balance": "saldo_final", "saldo final": "saldo_final",
                    }.get(label)
                    if summary_key:
                        candidate = values[column] if row + 1 >= len(top) else top.iloc[row + 1, column]
                        summary[summary_key] = number(candidate)
        data.attrs.update({"sheet": sheet_name, "header_row": row_index + 1, "summary": summary})
        return data

    @staticmethod
    def _mapping(columns, aliases: dict) -> dict:
        normalized_columns = {
            normalized(column): column for column in columns
            if not str(column).startswith("__")
        }
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
            ("Pago con QR", ("pago con qr",)),
            ("Pago de crédito / préstamo", ("pago de cuota creditos", "pago de credito", "loan payment")),
            ("Crédito / Préstamo / Financiación", ("creditos de mercado pago", "prestamo", "financiacion", "loan")),
            ("Acreditación", ("acreditacion",)),
            ("Comisión", ("comision", "cargo por cobro", "fee")), ("Retención", ("retencion",)),
            ("Percepción", ("percepcion",)), ("Impuesto", ("impuesto", "iva", "iibb")),
            ("Rendimientos / Intereses", ("interes", "rendimiento")), ("Cobranza", ("cobro", "venta", "payment received")),
            ("Pago", ("pago", "compra", "payment sent")), ("Ajuste", ("ajuste", "adjustment")),
        )
        for label, terms in rules:
            if any(term in value for term in terms): return label
        return "A revisar"

    def _new_history(self, client_id: int, source: str, path: Path, frame: pd.DataFrame) -> int:
        return self.database.execute(
            """INSERT INTO historial_importaciones_plataformas(
                   cliente_id,fuente,nombre_archivo,filas_leidas,fila_encabezado,
                   hoja_detectada,columnas_originales,resumen_json)
               VALUES(?,?,?,?,?,?,?,?)""",
            (client_id, source, path.name, len(frame), frame.attrs.get("header_row"),
             frame.attrs.get("sheet", ""), json.dumps(list(map(str, frame.columns)), ensure_ascii=False),
             json.dumps(frame.attrs.get("summary", {}), ensure_ascii=False)),
        )

    def _finish_history(self, import_id: int, imported: int, duplicates: int, review: int, rejected: int, periods: set[str]) -> None:
        state = "Importado con advertencias" if review or rejected else ("Duplicado" if not imported and duplicates else "Importado correctamente")
        self.database.execute(
            """UPDATE historial_importaciones_plataformas SET importados=?,duplicados=?,revisar=?,rechazados=?,periodo_detectado=?,estado=? WHERE id=?""",
            (imported, duplicates, review, rejected, ", ".join(sorted(periods)), state, import_id),
        )

    def import_mercado_pago(
        self, path: Path, client_id: int, manual_mapping: dict | None = None,
        duplicate_action: str = "skip", header_row: int | None = None,
        sheet_name: str = "", selected_rows: set[int] | None = None,
        row_overrides: dict[int, dict] | None = None,
    ) -> dict:
        if not client_id: raise ValueError("Debe seleccionar un cliente.")
        if duplicate_action not in ("skip", "replace", "import"):
            raise ValueError("La acción de duplicados no es válida.")
        frame = self._read(path, "mp", header_row, sheet_name)
        if frame.empty: raise ValueError("El archivo no contiene movimientos.")
        mapping = {**self._mapping(frame.columns, self.MP_ALIASES), **(manual_mapping or {})}
        missing = [field for field in ("fecha", "importe_bruto") if field not in mapping]
        if "importe_bruto" in missing and "importe_neto" in mapping: missing.remove("importe_bruto")
        if missing: raise ValueError("No se reconocieron las columnas: " + ", ".join(missing) + ". Columnas disponibles: " + ", ".join(map(str, frame.columns)))
        import_id = self._new_history(client_id, "Mercado Pago", path, frame)
        imported = duplicates = review = rejected = 0; periods = set(); messages = []
        for index, source in frame.iterrows():
            if selected_rows is not None and int(index) not in selected_rows: continue
            try:
                def get(field, default=""):
                    column = mapping.get(field); value = source.get(column, default) if column else default
                    if column and row_overrides and int(index) in row_overrides and column in row_overrides[int(index)]:
                        value = row_overrides[int(index)][column]
                    return "" if pd.isna(value) else value
                movement_date = parsed_date(get("fecha")); period = movement_date[:7]; periods.add(period)
                gross = number(get("importe_bruto", get("importe_neto"))); net = number(get("importe_neto", gross))
                description = str(get("descripcion")); operation = str(get("operacion")); original_type = str(get("tipo_movimiento"))
                classification = self.classify_mp(" ".join((description, operation, original_type, str(get("medio_pago")))))
                if classification == "A revisar": review += 1
                direction = "Egreso" if net < 0 or classification in ("Pago", "Pago con QR", "Pago de crédito / préstamo", "Transferencia realizada", "Comisión", "Retención", "Percepción", "Impuesto", "Contracargo") else "Ingreso"
                counterpart = str(get("contraparte")).strip()
                if not counterpart:
                    movement_text = " ".join((original_type, description, operation)).strip()
                    match = re.search(r"(?:transferencia (?:recibida|enviada)|pago con qr)\s+(?:de |a )?(.+)$", movement_text, re.I)
                    counterpart = match.group(1).strip() if match else ""
                operation_id = str(get("id_operacion")); movement_id = str(get("id_movimiento"))
                duplicate = self.database.query_one(
                    """SELECT id FROM movimientos_mercado_pago WHERE cliente_id=? AND
                       ((?<>'' AND id_operacion=?) OR (?<>'' AND id_movimiento=?) OR (fecha=? AND importe_neto=? AND descripcion=?)) LIMIT 1""",
                    (client_id, operation_id, operation_id, movement_id, movement_id, movement_date, net, description),
                )
                possible_duplicate = 0
                if duplicate:
                    duplicates += 1
                    if duplicate_action == "skip": continue
                    if duplicate_action == "replace":
                        self.database.execute("DELETE FROM movimientos_mercado_pago WHERE id=?", (duplicate["id"],))
                    else:
                        possible_duplicate = 1
                self.database.execute(
                    """INSERT INTO movimientos_mercado_pago(cliente_id,fecha,periodo,descripcion,tipo_movimiento,operacion,contraparte,contraparte_documento,medio_pago,id_operacion,id_movimiento,referencia,moneda,importe_bruto,comisiones,retenciones,percepciones,impuestos,importe_neto,saldo,ingreso_egreso,estado,observaciones,nombre_archivo_origen,id_importacion,estado_revision,posible_duplicado,datos_originales_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (client_id,movement_date,period,description,classification,operation,counterpart,str(get("contraparte_documento")),str(get("medio_pago")),operation_id,movement_id,str(get("referencia")),str(get("moneda") or "ARS"),gross,number(get("comisiones")),number(get("retenciones")),number(get("percepciones")),number(get("impuestos")),net,number(get("saldo")),direction,str(get("estado")),"",path.name,import_id,"A revisar" if classification == "A revisar" else "Revisado",possible_duplicate,json.dumps(source.to_dict(), ensure_ascii=False, default=str)),
                )
                imported += 1
            except Exception as error:
                rejected += 1
                if len(messages) < 10: messages.append(f"Fila {index + 2}: {error}")
        self._finish_history(import_id, imported, duplicates, review, rejected, periods)
        return {"import_id": import_id, "read": len(frame), "imported": imported, "duplicates": duplicates, "review": review, "rejected": rejected, "messages": messages}

    def import_mercado_libre(
        self, path: Path, client_id: int, source_kind: str = "Ventas",
        manual_mapping: dict | None = None, duplicate_action: str = "skip",
        header_row: int | None = None, sheet_name: str = "",
        selected_rows: set[int] | None = None, row_overrides: dict[int, dict] | None = None,
    ) -> dict:
        if not client_id: raise ValueError("Debe seleccionar un cliente.")
        if duplicate_action not in ("skip", "replace", "import"):
            raise ValueError("La acción de duplicados no es válida.")
        frame = self._read(path, "ml", header_row, sheet_name)
        if frame.empty: raise ValueError("El archivo no contiene operaciones.")
        mapping = {**self._mapping(frame.columns, self.ML_ALIASES), **(manual_mapping or {})}
        missing = [field for field in ("fecha", "importe_bruto") if field not in mapping]
        if missing: raise ValueError("No se reconocieron las columnas: " + ", ".join(missing) + ". Columnas disponibles: " + ", ".join(map(str, frame.columns)))
        import_id = self._new_history(client_id, f"Mercado Libre {source_kind}", path, frame)
        imported = duplicates = review = rejected = 0; periods = set(); messages = []
        for index, source in frame.iterrows():
            if selected_rows is not None and int(index) not in selected_rows: continue
            try:
                def get(field, default=""):
                    column = mapping.get(field); value = source.get(column, default) if column else default
                    if column and row_overrides and int(index) in row_overrides and column in row_overrides[int(index)]:
                        value = row_overrides[int(index)][column]
                    return "" if pd.isna(value) else value
                operation_date = parsed_date(get("fecha")); period = operation_date[:7]; periods.add(period)
                type_text = str(get("tipo_operacion") or source_kind[:-1]); voucher = str(get("tipo_comprobante")); state = str(get("estado"))
                combined = normalized(" ".join((type_text, voucher, state, str(get("observaciones")))))
                if "nota de credito" in combined or "devol" in combined: operation_type = "Nota de crédito"
                elif "anul" in combined or "cancel" in combined: operation_type = "Anulación"
                elif source_kind.casefold().startswith("compra") or "compra" in combined: operation_type = "Compra"
                else: operation_type = "Venta"
                gross = number(get("importe_bruto"))
                shipping_income = number(get("ingresos_envio"))
                fixed_cost = number(get("costo_fijo")); installment_cost = number(get("costo_cuotas"))
                shipping_cost = number(get("costo_envio", get("envios"))); taxes = number(get("impuestos"))
                refunds = number(get("anulaciones_reembolsos"))
                net = number(get("importe_neto", gross))
                if not get("importe_neto"):
                    net = sum((gross, shipping_income, number(get("descuentos")), number(get("comisiones")),
                               fixed_cost, installment_cost, shipping_cost, taxes, refunds,
                               number(get("retenciones")), number(get("percepciones"))))
                if operation_type in ("Nota de crédito", "Anulación"): net = -abs(net)
                operation_id, sale_id, voucher_number = str(get("id_operacion")), str(get("id_venta")), str(get("numero_comprobante"))
                duplicate = self.database.query_one(
                    """SELECT id FROM operaciones_mercado_libre WHERE cliente_id=? AND
                       ((?<>'' AND id_operacion=?) OR (?<>'' AND id_venta=?) OR (?<>'' AND numero_comprobante=?)) LIMIT 1""",
                    (client_id, operation_id, operation_id, sale_id, sale_id, voucher_number, voucher_number),
                )
                possible_duplicate = 0
                if duplicate:
                    duplicates += 1
                    if duplicate_action == "skip": continue
                    if duplicate_action == "replace":
                        self.database.execute("DELETE FROM operaciones_mercado_libre WHERE id=?", (duplicate["id"],))
                    else:
                        possible_duplicate = 1
                if not operation_id and not sale_id and not voucher_number: review += 1
                claim_open = str(get("reclamo_abierto")); mediation = str(get("con_mediacion"))
                special_text = normalized(" ".join((state, claim_open, mediation, str(get("observaciones")))))
                if refunds:
                    special_state = "Venta con devolución / anulación / reembolso"
                elif normalized(claim_open) in ("si", "yes", "true", "1") or "reclamo" in special_text:
                    special_state = "Venta con reclamo"
                elif normalized(mediation) in ("si", "yes", "true", "1") or "mediacion" in special_text:
                    special_state = "Venta con mediación"
                elif any(term in special_text for term in ("cancel", "anulad")):
                    special_state = "Venta cancelada"
                elif any(term in special_text for term in ("entreg", "delivered")):
                    special_state = "Venta entregada"
                else:
                    special_state = "Venta normal"
                inserted_id = self.database.execute(
                    """INSERT INTO operaciones_mercado_libre(
                       cliente_id,fecha,periodo,tipo_operacion,tipo_comprobante,numero_comprobante,
                       estado,contraparte,contraparte_documento,producto,cantidad,precio_unitario,
                       importe_bruto,descuentos,comisiones,envios,retenciones,percepciones,importe_neto,
                       moneda,id_operacion,id_venta,id_publicacion,medio_cobro,observaciones,
                       nombre_archivo_origen,id_importacion,sku,variante,ingresos_envio,costo_fijo,
                       costo_cuotas,costo_envio,impuestos,anulaciones_reembolsos,resultado_neto,
                       condicion_fiscal_comprador,direccion_facturacion,domicilio_entrega,ciudad,
                       provincia,codigo_postal,pais,reclamo_abierto,reclamo_cerrado,con_mediacion,
                       estado_especial,posible_duplicado,datos_originales_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (client_id,operation_date,period,operation_type,voucher,voucher_number,state,
                     str(get("contraparte")),str(get("contraparte_documento")),str(get("producto")),
                     number(get("cantidad")),number(get("precio_unitario")),gross,number(get("descuentos")),
                     number(get("comisiones")),number(get("envios")),number(get("retenciones")),
                     number(get("percepciones")),net,str(get("moneda") or "ARS"),operation_id,sale_id,
                     str(get("id_publicacion")),str(get("medio_cobro")),str(get("observaciones")),path.name,
                     import_id,str(get("sku")),str(get("variante")),shipping_income,fixed_cost,
                     installment_cost,shipping_cost,taxes,refunds,net,str(get("condicion_fiscal_comprador")),
                     str(get("direccion_facturacion")),str(get("domicilio_entrega")),str(get("ciudad")),
                     str(get("provincia")),str(get("codigo_postal")),str(get("pais")),claim_open,
                     str(get("reclamo_cerrado")),mediation,special_state,possible_duplicate,
                     json.dumps(source.to_dict(), ensure_ascii=False, default=str)),
                )
                def optional_date(field: str):
                    value = get(field)
                    if not str(value).strip():
                        return None
                    try:
                        return parsed_date(value)
                    except ValueError:
                        return None
                self.database.execute(
                    """UPDATE operaciones_mercado_libre SET descripcion_estado=?,paquete_multiple=?,
                       pertenece_kit=?,mes_facturacion=?,orden_compra=?,venta_publicidad=?,
                       cuotas_agregadas=?,factura_adjunta=?,datos_facturacion_comprador=?,negocio=?,
                       forma_entrega=?,fecha_en_camino=?,fecha_entregado=?,transportista=?,
                       numero_seguimiento=?,url_seguimiento=?,revisado_ml=?,fecha_revision=?,
                       dinero_favor=?,resultado_reclamo=?,destino_reclamo=?,motivo_resultado=? WHERE id=?""",
                    (str(get("descripcion_estado")),str(get("paquete_multiple")),str(get("pertenece_kit")),
                     str(get("mes_facturacion")),str(get("orden_compra")),str(get("venta_publicidad")),
                     str(get("cuotas_agregadas")),str(get("factura_adjunta")),str(get("datos_facturacion_comprador")),
                     str(get("negocio")),str(get("forma_entrega")),optional_date("fecha_en_camino"),
                     optional_date("fecha_entregado"),str(get("transportista")),str(get("numero_seguimiento")),
                     str(get("url_seguimiento")),str(get("revisado_ml")),optional_date("fecha_revision"),
                     number(get("dinero_favor")),str(get("resultado_reclamo")),str(get("destino_reclamo")),
                     str(get("motivo_resultado")),inserted_id),
                )
                imported += 1
            except Exception as error:
                rejected += 1
                if len(messages) < 10: messages.append(f"Fila {index + 2}: {error}")
        self._finish_history(import_id, imported, duplicates, review, rejected, periods)
        return {"import_id": import_id, "read": len(frame), "imported": imported, "duplicates": duplicates, "review": review, "rejected": rejected, "messages": messages}

    def list_mp(self, client_id: int, period: str = "", movement_type: str = "", direction: str = "", search: str = "", year: str = "", month: str = "", minimum: float = 0, state: str = "") -> list[dict]:
        conditions = ["cliente_id=?"]; params: list = [client_id]
        if period: conditions.append("periodo=?"); params.append(normalize_period(period))
        if movement_type and movement_type != "Todos": conditions.append("tipo_movimiento=?"); params.append(movement_type)
        if direction and direction != "Todos": conditions.append("ingreso_egreso=?"); params.append(direction)
        if search: conditions.append("(contraparte LIKE ? OR descripcion LIKE ? OR id_operacion LIKE ?)"); params.extend([f"%{search}%"]*3)
        if year: conditions.append("substr(periodo,1,4)=?");params.append(str(year))
        if month: conditions.append("substr(periodo,6,2)=?");params.append(str(month).zfill(2))
        if minimum: conditions.append("ABS(importe_neto)>=?");params.append(float(minimum))
        if state and state != "Todos": conditions.append("estado=?");params.append(state)
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
                SUM(CASE WHEN tipo_movimiento IN ('Interés','Rendimientos / Intereses') THEN ABS(importe_neto) ELSE 0 END) intereses,
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

    @staticmethod
    def mp_summary_rows(rows: list[dict]) -> list[dict]:
        grouped: dict[str,dict] = {}
        for row in rows:
            period=row.get("periodo","");item=grouped.setdefault(period,{"periodo":period,"total_ingresos":0.0,"total_egresos":0.0,"comisiones":0.0,"retenciones":0.0,"percepciones":0.0,"impuestos":0.0,"cantidad_movimientos":0})
            direction=row.get("ingreso_egreso");amount=abs(float(row.get("importe_neto") or 0));item["total_ingresos" if direction=="Ingreso" else "total_egresos"]+=amount;item["comisiones"]+=abs(float(row.get("comisiones") or 0));item["retenciones"]+=abs(float(row.get("retenciones") or 0));item["percepciones"]+=abs(float(row.get("percepciones") or 0));item["impuestos"]+=abs(float(row.get("impuestos") or 0));item["cantidad_movimientos"]+=1
        return sorted(grouped.values(),key=lambda item:item["periodo"],reverse=True)

    def mp_ranking(self, client_id: int, direction: str) -> list[dict]:
        return [dict(row) for row in self.database.query(
            """SELECT contraparte,contraparte_documento,COUNT(*) cantidad_movimientos,
                SUM(ABS(importe_bruto)) total_bruto,SUM(ABS(importe_neto)) total_neto,
                MAX(ABS(importe_neto)) movimiento_mas_alto,MAX(fecha) ultima_fecha
                FROM movimientos_mercado_pago WHERE cliente_id=? AND ingreso_egreso=?
                GROUP BY contraparte,contraparte_documento ORDER BY total_neto DESC""", (client_id,direction))]

    def list_ml(self, client_id: int, period: str = "", operation_type: str = "", search: str = "", year: str = "", month: str = "", minimum: float = 0, state: str = "", province: str = "", product: str = "") -> list[dict]:
        conditions = ["cliente_id=?"]; params: list = [client_id]
        if period: conditions.append("periodo=?"); params.append(normalize_period(period))
        if operation_type and operation_type != "Todos": conditions.append("tipo_operacion=?"); params.append(operation_type)
        if search: conditions.append("(contraparte LIKE ? OR producto LIKE ? OR numero_comprobante LIKE ?)"); params.extend([f"%{search}%"]*3)
        if year: conditions.append("substr(periodo,1,4)=?");params.append(str(year))
        if month: conditions.append("substr(periodo,6,2)=?");params.append(str(month).zfill(2))
        if minimum: conditions.append("ABS(importe_neto)>=?");params.append(float(minimum))
        if state and state != "Todos": conditions.append("(estado=? OR estado_especial=?)");params.extend([state,state])
        if province: conditions.append("provincia LIKE ?");params.append(f"%{province}%")
        if product: conditions.append("producto LIKE ?");params.append(f"%{product}%")
        return [dict(row) for row in self.database.query(f"SELECT * FROM operaciones_mercado_libre WHERE {' AND '.join(conditions)} ORDER BY fecha DESC,id DESC", params)]

    def ml_summary(self, client_id: int) -> list[dict]:
        return [dict(row) for row in self.database.query(
            """SELECT periodo,
                SUM(CASE WHEN tipo_operacion='Venta' THEN importe_bruto ELSE 0 END) ventas_brutas,
                SUM(CASE WHEN tipo_operacion='Nota de crédito' THEN ABS(importe_neto) ELSE 0 END) notas_credito,
                SUM(CASE WHEN tipo_operacion IN ('Anulación','Devolución') THEN ABS(importe_neto) ELSE 0 END) anulaciones_devoluciones,
                SUM(CASE WHEN tipo_operacion IN ('Venta','Nota de crédito','Anulación') THEN importe_neto ELSE 0 END) ventas_netas,
                SUM(ingresos_envio) ingresos_envio,SUM(comisiones) comisiones,
                SUM(costo_fijo) costos_fijos,SUM(costo_cuotas) costos_cuotas,
                SUM(costo_envio) costos_envio,SUM(impuestos) impuestos,
                SUM(descuentos) descuentos,SUM(anulaciones_reembolsos) anulaciones_reembolsos,
                SUM(cantidad) unidades,SUM(ABS(retenciones)) retenciones,
                SUM(ABS(percepciones)) percepciones,COUNT(*) cantidad_operaciones,
                CASE WHEN COUNT(*)=0 THEN 0 ELSE SUM(importe_neto)/COUNT(*) END ticket_promedio,
                SUM(CASE WHEN estado_especial='Venta con reclamo' THEN 1 ELSE 0 END) ventas_reclamo,
                SUM(CASE WHEN estado_especial LIKE 'Venta con devolución%' THEN 1 ELSE 0 END) ventas_devolucion,
                SUM(CASE WHEN estado_especial='Venta con mediación' THEN 1 ELSE 0 END) ventas_mediacion
                FROM operaciones_mercado_libre WHERE cliente_id=? GROUP BY periodo ORDER BY periodo DESC""", (client_id,))]

    @staticmethod
    def ml_summary_rows(rows: list[dict]) -> list[dict]:
        grouped: dict[str,dict]={}
        for row in rows:
            period=row.get("periodo","");item=grouped.setdefault(period,{"periodo":period,"cantidad_ventas":0,"unidades":0.0,"ventas_brutas":0.0,"ingresos_envio":0.0,"comisiones":0.0,"costos_fijos":0.0,"costos_cuotas":0.0,"costos_envio":0.0,"impuestos":0.0,"descuentos":0.0,"anulaciones_reembolsos":0.0,"ventas_netas":0.0,"ventas_reclamo":0,"ventas_devolucion":0,"ventas_mediacion":0})
            item["cantidad_ventas"]+=1;item["unidades"]+=float(row.get("cantidad") or 0);item["ventas_brutas"]+=float(row.get("importe_bruto") or 0);item["ingresos_envio"]+=float(row.get("ingresos_envio") or 0);item["comisiones"]+=float(row.get("comisiones") or 0);item["costos_fijos"]+=float(row.get("costo_fijo") or 0);item["costos_cuotas"]+=float(row.get("costo_cuotas") or 0);item["costos_envio"]+=float(row.get("costo_envio") or 0);item["impuestos"]+=float(row.get("impuestos") or 0);item["descuentos"]+=float(row.get("descuentos") or 0);item["anulaciones_reembolsos"]+=float(row.get("anulaciones_reembolsos") or 0);item["ventas_netas"]+=float(row.get("importe_neto") or 0);state=row.get("estado_especial","");item["ventas_reclamo"]+=int(state=="Venta con reclamo");item["ventas_devolucion"]+=int(str(state).startswith("Venta con devolución"));item["ventas_mediacion"]+=int(state=="Venta con mediación")
        for item in grouped.values():item["ticket_promedio"]=item["ventas_netas"]/item["cantidad_ventas"] if item["cantidad_ventas"] else 0
        return sorted(grouped.values(),key=lambda item:item["periodo"],reverse=True)

    def ml_buyers(self, client_id: int) -> list[dict]:
        return [dict(row) for row in self.database.query(
            """SELECT contraparte comprador,contraparte_documento documento,
                MAX(condicion_fiscal_comprador) condicion_fiscal_iva,
                MAX(direccion_facturacion) direccion_facturacion,
                MAX(domicilio_entrega) domicilio_entrega,MAX(ciudad) ciudad,
                MAX(provincia) provincia,MAX(codigo_postal) codigo_postal,MAX(pais) pais,
                COUNT(*) cantidad_ventas,SUM(cantidad) unidades,SUM(importe_bruto) ingresos_productos,
                SUM(importe_neto) total_neto,MAX(fecha) ultima_compra,
                SUM(CASE WHEN estado_especial='Venta con reclamo' THEN 1 ELSE 0 END) reclamos,
                SUM(CASE WHEN estado_especial LIKE 'Venta con devolución%' THEN 1 ELSE 0 END) devoluciones
                FROM operaciones_mercado_libre WHERE cliente_id=? AND tipo_operacion='Venta'
                GROUP BY contraparte,contraparte_documento ORDER BY total_neto DESC""", (client_id,))]

    def ml_products(self, client_id: int) -> list[dict]:
        return [dict(row) for row in self.database.query(
            """SELECT sku,id_publicacion,producto titulo,variante,COUNT(*) cantidad_operaciones,
                SUM(cantidad) unidades_vendidas,
                CASE WHEN SUM(cantidad)=0 THEN 0 ELSE SUM(importe_bruto)/SUM(cantidad) END precio_unitario_promedio,
                SUM(importe_bruto) ingresos_productos,SUM(importe_neto) total_neto,
                SUM(CASE WHEN estado_especial='Venta con reclamo' THEN 1 ELSE 0 END) reclamos,
                SUM(CASE WHEN estado_especial LIKE 'Venta con devolución%' THEN 1 ELSE 0 END) devoluciones
                FROM operaciones_mercado_libre WHERE cliente_id=? AND tipo_operacion='Venta'
                GROUP BY sku,id_publicacion,producto,variante ORDER BY unidades_vendidas DESC""", (client_id,))]

    def mp_file_summaries(self, client_id: int) -> list[dict]:
        rows = self.database.query(
            """SELECT id,nombre_archivo,fecha_importacion,resumen_json,fila_encabezado,
               hoja_detectada,filas_leidas,importados,duplicados,revisar,rechazados
               FROM historial_importaciones_plataformas
               WHERE cliente_id=? AND fuente='Mercado Pago' ORDER BY fecha_importacion DESC""",
            (client_id,),
        )
        result = []
        for source in rows:
            row = dict(source)
            row.update(json.loads(row.pop("resumen_json") or "{}"))
            result.append(row)
        return result

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

    def update_ml_classification(self, operation_id: int, classification: str) -> None:
        self.database.execute(
            "UPDATE operaciones_mercado_libre SET tipo_operacion=?,estado_especial=? WHERE id=?",
            (classification, classification, operation_id),
        )
