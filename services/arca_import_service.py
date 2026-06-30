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
from utils.validators import digits


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.encode("ascii", "ignore").decode().casefold()).strip()


def _number(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    text = str(value).strip().replace("$", "").replace("ARS", "").replace(" ", "")
    if not text:
        return 0.0
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("()-")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    value_float = float(re.sub(r"[^0-9.]", "", text) or 0)
    return -value_float if negative else value_float


def _date(value: object) -> str:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.date().isoformat() if hasattr(value, "date") else value.isoformat()
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Fecha inválida: {text or 'vacía'}")


def _period(value: object, fallback_date: str = "") -> str:
    text = str(value or "").strip()
    if text:
        for fmt in ("%m/%Y", "%m-%Y", "%Y-%m", "%Y/%m", "%m/%y"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m")
            except ValueError:
                pass
        match = re.search(r"(0?[1-9]|1[0-2])\D+(20\d{2})", text)
        if match:
            return f"{match.group(2)}-{int(match.group(1)):02d}"
    return fallback_date[:7] if fallback_date else ""


class ArcaImportService:
    """Importadores auditables de vencimientos y PDF de Sistema Registral."""

    DEADLINE_ALIASES = {
        "cuit": ("cuit", "cuit cuil", "identificacion fiscal"),
        "nombre": ("razon social", "cliente", "contribuyente", "nombre"),
        "organismo": ("organismo", "ente"),
        "impuesto": ("impuesto", "tributo", "obligacion", "concepto", "descripcion"),
        "subconcepto": ("subconcepto", "detalle"),
        "periodo": ("periodo", "periodo fiscal", "mes", "anticipo", "cuota"),
        "vencimiento": ("fecha de vencimiento", "fecha venc", "f vencimiento", "vencimiento", "vto"),
        "presentacion": ("fecha de presentacion", "presentacion"),
        "pago": ("fecha de pago", "pago"),
        "tipo": ("tipo de obligacion", "tipo de vencimiento", "tipo"),
        "estado": ("estado", "situacion"),
        "importe": ("importe", "monto", "total", "deuda"),
        "saldo": ("saldo", "saldo pendiente"),
        "observaciones": ("observaciones", "nota", "comentario"),
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _mapping(headers: list[object], aliases: dict[str, tuple[str, ...]]) -> dict[str, int]:
        normalized = [_key(header) for header in headers]
        mapping: dict[str, int] = {}
        used: set[int] = set()
        for field, candidates in aliases.items():
            candidate_keys = tuple(_key(candidate) for candidate in candidates)
            for index, header in enumerate(normalized):
                if index in used:
                    continue
                if header in candidate_keys or any(candidate in header for candidate in candidate_keys):
                    mapping[field] = index
                    used.add(index)
                    break
        return mapping

    @staticmethod
    def _csv_rows(path: Path) -> list[list[object]]:
        raw = None
        for encoding in ("utf-8-sig", "latin-1"):
            try:
                raw = path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        if raw is None:
            raise ValueError("No se pudo reconocer la codificación del CSV.")
        candidates = (";", "\t", "|", ",")
        lines = raw.splitlines()[:50]
        delimiter = max(candidates, key=lambda item: max((line.count(item) for line in lines), default=0))
        return [list(row) for row in csv.reader(io.StringIO(raw), delimiter=delimiter)]

    @classmethod
    def _sheets(cls, path: Path) -> dict[str, list[list[object]]]:
        suffix = path.suffix.casefold()
        if suffix == ".csv":
            return {"CSV": cls._csv_rows(path)}
        if suffix not in (".xls", ".xlsx"):
            raise ValueError("El archivo debe ser .xls, .xlsx o .csv.")
        try:
            frames = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
        except ImportError as error:
            raise RuntimeError("Para leer Excel .xls instalá las dependencias del proyecto.") from error
        return {name: frame.where(pd.notna(frame), "").values.tolist() for name, frame in frames.items()}

    def preview_deadlines(self, path: Path, manual_mapping: dict[str, int] | None = None) -> dict:
        best: tuple[int, str, int, list[list[object]], dict[str, int]] | None = None
        for sheet, rows in self._sheets(path).items():
            for index, row in enumerate(rows[:80]):
                mapping = self._mapping(list(row), self.DEADLINE_ALIASES)
                score = len(mapping) + (3 if "vencimiento" in mapping else 0) + (2 if "impuesto" in mapping else 0)
                if best is None or score > best[0]:
                    best = (score, sheet, index, rows, mapping)
        if not best:
            raise ValueError("El archivo no contiene filas legibles.")
        _, sheet, header_index, rows, mapping = best
        mapping.update(manual_mapping or {})
        headers = [str(value or "") for value in rows[header_index]]
        missing = [field for field in ("impuesto", "vencimiento") if field not in mapping]
        records: list[dict] = []
        errors: list[str] = []
        for source_index, row in ([] if missing else enumerate(rows[header_index + 1 :], header_index + 2)):
            if not any(str(value).strip() for value in row):
                continue

            def get(field: str, default: object = "") -> object:
                column = mapping.get(field)
                return row[column] if column is not None and column < len(row) else default

            try:
                due_date = _date(get("vencimiento"))
                tax = str(get("impuesto")).strip()
                if not tax:
                    raise ValueError("impuesto vacío")
                cuit = digits(str(get("cuit")))
                client = self.database.query_one(
                    "SELECT id,nombre_razon_social FROM clientes WHERE cuit_cuil=?", (cuit,)
                ) if cuit else None
                status_text = _key(get("estado"))
                if "pag" in status_text:
                    status = "pagado"
                elif "present" in status_text:
                    status = "presentado"
                elif due_date < date.today().isoformat():
                    status = "vencido"
                else:
                    status = "pendiente"
                period = _period(get("periodo"), due_date)
                confidence = "Alta" if client and period else ("Media" if client else "A revisar")
                extra = []
                if get("subconcepto"):
                    extra.append(f"Subconcepto: {get('subconcepto')}")
                if get("observaciones"):
                    extra.append(str(get("observaciones")))
                records.append({
                    "source_row": source_index,
                    "client_id": int(client["id"]) if client else None,
                    "cliente": client["nombre_razon_social"] if client else str(get("nombre")).strip(),
                    "cuit": cuit,
                    "impuesto": tax,
                    "organismo": str(get("organismo") or "ARCA").strip(),
                    "periodo": period,
                    "fecha_vencimiento": due_date,
                    "fecha_presentacion": _date(get("presentacion")) if str(get("presentacion")).strip() else "",
                    "fecha_pago": _date(get("pago")) if str(get("pago")).strip() else "",
                    "tipo_vencimiento": str(get("tipo") or "Presentación / Pago").strip(),
                    "estado": status,
                    "importe": _number(get("importe")),
                    "saldo": _number(get("saldo")),
                    "observaciones": " | ".join(extra),
                    "confianza": confidence,
                    "accion": "Importar",
                })
            except Exception as error:
                errors.append(f"Fila {source_index}: {error}")
        return {
            "source": "ARCA Vencimientos",
            "path": str(path),
            "sheet": sheet,
            "header_row": header_index + 1,
            "headers": headers,
            "mapping": mapping,
            "missing": missing,
            "unrecognized": [header for index, header in enumerate(headers) if index not in mapping.values()],
            "rows_read": max(0, len(rows) - header_index - 1),
            "records": records,
            "errors": errors,
        }

    def import_deadlines(self, preview: dict, duplicate_action: str = "skip") -> dict:
        if duplicate_action not in ("skip", "replace", "import"):
            raise ValueError("La acción de duplicados no es válida.")
        imported = duplicates = review = rejected = 0
        primary_client = next((row.get("client_id") for row in preview["records"] if row.get("client_id")), None)
        import_id = self.database.execute(
            """INSERT INTO historial_importaciones_contables(
                   cliente_id,fuente,archivo,filas_leidas,metadatos_json)
               VALUES(?,?,?,?,?)""",
            (primary_client, "ARCA Vencimientos", Path(preview["path"]).name,
             preview["rows_read"], json.dumps({"sheet": preview["sheet"], "header_row": preview["header_row"], "mapping": preview["mapping"]}, ensure_ascii=False)),
        )
        for row in preview["records"]:
            if row.get("accion") == "No importar":
                continue
            if not row.get("client_id"):
                review += 1
                continue
            duplicate = self.database.query_one(
                """SELECT id FROM vencimientos WHERE cliente_id=? AND organismo=?
                   AND impuesto=? AND periodo=? AND fecha_vencimiento=?
                   AND COALESCE(tipo_vencimiento,'')=? LIMIT 1""",
                (row["client_id"], row["organismo"], row["impuesto"], row["periodo"],
                 row["fecha_vencimiento"], row["tipo_vencimiento"]),
            )
            if duplicate:
                duplicates += 1
                if duplicate_action == "skip":
                    continue
            try:
                values = (row["client_id"], row["impuesto"], row["periodo"], row["fecha_vencimiento"],
                          row["organismo"], row["tipo_vencimiento"], row["estado"], "NATALIA",
                          row["observaciones"], row["importe"], row["saldo"], row["fecha_presentacion"] or None,
                          row["fecha_pago"] or None, "ARCA", import_id, datetime.now().isoformat(timespec="seconds"))
                if duplicate and duplicate_action == "replace":
                    self.database.execute(
                        """UPDATE vencimientos SET cliente_id=?,impuesto=?,periodo=?,fecha_vencimiento=?,
                           organismo=?,tipo_vencimiento=?,estado=?,responsable=?,observaciones=?,importe=?,saldo=?,
                           fecha_presentacion=?,fecha_pago=?,origen=?,id_importacion=?,actualizado_en=? WHERE id=?""",
                        (*values, duplicate["id"]),
                    )
                else:
                    inserted_id=self.database.execute(
                        """INSERT INTO vencimientos(cliente_id,impuesto,periodo,fecha_vencimiento,
                           organismo,tipo_vencimiento,estado,responsable,observaciones,importe,saldo,
                           fecha_presentacion,fecha_pago,origen,id_importacion,actualizado_en)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values,
                    )
                    if duplicate and duplicate_action=="import":
                        self.database.execute("UPDATE vencimientos SET posible_duplicado=1 WHERE id=?",(inserted_id,))
                imported += 1
                if row["confianza"] == "A revisar":
                    review += 1
            except Exception:
                rejected += 1
        state = "Importado con advertencias" if review or rejected else "Importado correctamente"
        self.database.execute(
            """UPDATE historial_importaciones_contables SET filas_importadas=?,filas_duplicadas=?,
               filas_revisar=?,filas_error=?,estado=? WHERE id=?""",
            (imported, duplicates, review, rejected, state, import_id),
        )
        return {"import_id": import_id, "imported": imported, "duplicates": duplicates,
                "review": review, "rejected": rejected}

    @staticmethod
    def _pdf_text(path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError("Instalá las dependencias para poder leer archivos PDF.") from error
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        if not text.strip():
            raise ValueError("El PDF no contiene texto seleccionable. Requiere OCR o carga manual.")
        return text

    def preview_registry_pdf(self, path: Path) -> dict:
        text = self._pdf_text(path)
        compact = re.sub(r"[ \t]+", " ", text)

        def first(patterns: tuple[str, ...]) -> str:
            for pattern in patterns:
                match = re.search(pattern, compact, re.I | re.M)
                if match:
                    return match.group(1).strip(" :-\n")
            return ""

        cuit_match = re.search(r"\b(?:CUIT|CUIL)\D{0,15}(\d{2}[- ]?\d{8}[- ]?\d)\b", compact, re.I)
        cuit = digits(cuit_match.group(1)) if cuit_match else ""
        fields = {
            "cuit_cuil": cuit,
            "nombre_razon_social": first((r"Raz[oó]n social\s*[:\-]?\s*([^\n]+)", r"Apellido y nombre\s*[:\-]?\s*([^\n]+)", r"Denominaci[oó]n\s*[:\-]?\s*([^\n]+)")),
            "apellido": first((r"^Apellido\s*[:\-]?\s*([^\n]+)",)),
            "nombre": first((r"^Nombre\s*[:\-]?\s*([^\n]+)",)),
            "tipo_persona_detectado": first((r"Tipo de persona\s*[:\-]?\s*([^\n]+)",)),
            "dni": first((r"(?:N[uú]mero de documento|Documento)\s*[:\-]?\s*([\d.]+)",)),
            "tipo_documento": first((r"Tipo de documento\s*[:\-]?\s*([^\n]+)",)),
            "genero": first((r"G[eé]nero\s*[:\-]?\s*([^\n]+)",)),
            "fecha_nacimiento": first((r"Fecha de nacimiento\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",)),
            "fecha_fallecimiento": first((r"Fecha de fallecimiento\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",)),
            "sucesion_indivisa": first((r"Sucesi[oó]n indivisa\s*[:\-]?\s*([^\n]+)",)),
            "nacionalidad": first((r"Pa[ií]s de nacimiento\s*[:\-]?\s*([^\n]+)", r"Nacionalidad\s*[:\-]?\s*([^\n]+)")),
            "apellido_materno": first((r"Apellido materno\s*[:\-]?\s*([^\n]+)",)),
            "apellido_casada": first((r"Apellido de casada\s*[:\-]?\s*([^\n]+)",)),
            "email": first((r"([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})",)),
            "telefono": first((r"(?:Tel[eé]fono|Celular)\s*[:\-]?\s*([+\d ()-]{7,})",)),
            "fecha_inscripcion": first((r"Fecha de inscripci[oó]n\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",)),
            "mes_cierre": first((r"Mes de cierre\s*[:\-]?\s*([^\n]+)",)),
            "dependencia": first((r"Dependencia\s*[:\-]?\s*([^\n]+)",)),
            "region": first((r"Regi[oó]n\s*[:\-]?\s*([^\n]+)",)),
            "tipo_inscripcion": first((r"Tipo de inscripci[oó]n\s*[:\-]?\s*([^\n]+)",)),
            "sistema_control": first((r"Sistema de control\s*[:\-]?\s*([^\n]+)",)),
            "segmento": first((r"Segmento\s*[:\-]?\s*([^\n]+)",)),
            "ultima_actualizacion": first((r"[UÚ]ltima actualizaci[oó]n\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",)),
            "impuestos_activos": first((r"Registra impuestos activos\s*[:\-]?\s*([^\n]+)",)),
            "pasivo_decreto_1299": first((r"Pasivo decreto 1299\s*[:\-]?\s*([^\n]+)",)),
            "dnrp": first((r"DNRP\s*[:\-]?\s*([^\n]+)",)),
            "dfe": "No" if re.search(r"domicilio fiscal electr[oó]nico.{0,50}(no adherido|no activo|\bno\b)", compact, re.I) else ("Sí" if re.search(r"domicilio fiscal electr[oó]nico.{0,50}(adherido|activo|\bs[ií]\b)", compact, re.I) else "A revisar"),
        }
        if not fields["nombre_razon_social"]:
            fields["nombre_razon_social"] = " ".join(part for part in (fields["apellido"], fields["nombre"]) if part)
        contacts = []
        for match in re.finditer(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", compact):
            context = compact[max(0, match.start()-80):match.start()].casefold()
            email_type = "Tributario" if "tribut" in context else ("Personal" if "personal" in context else "Otro")
            contacts.append({"clase": "Email", "valor": match.group(0), "tipo": email_type,
                             "estado": "Confirmado", "principal": 1 if not any(row["clase"] == "Email" for row in contacts) else 0})
        phone_pattern = re.compile(r"(?:Tel[eé]fono|Celular|M[oó]vil|Fijo)\s*[:\-]?\s*(\+?\d[\d ()-]{6,}\d)", re.I)
        for match in phone_pattern.finditer(compact):
            label = match.group(0)[:match.group(0).find(match.group(1))].casefold()
            phone_type = "Móvil" if "celular" in label or "móvil" in label else "Fijo" if "fijo" in label else "Otro"
            contacts.append({"clase": "Teléfono", "valor": match.group(1).strip(), "tipo": phone_type,
                             "estado": "A revisar" if "no confirmado" in compact[match.start():match.end()+50].casefold() else "Confirmado",
                             "principal": 1 if not any(row["clase"] == "Teléfono" for row in contacts) else 0})
        emails = [row["valor"] for row in contacts if row["clase"] == "Email"]
        addresses = []
        address_pattern = re.compile(r"(?:Tipo de domicilio|Domicilio)\s*[:\-]?\s*([^\n]+)\n(?:Direcci[oó]n\s*[:\-]?\s*)?([^\n]+)", re.I)
        for match in address_pattern.finditer(compact):
            block = compact[match.start():match.end()+250]
            addresses.append({"tipo": match.group(1).strip(), "direccion": match.group(2).strip(),
                "estado": first((r"Estado\s*[:\-]?\s*([^\n]+)",)) or "A revisar",
                "localidad": (re.search(r"Localidad\s*[:\-]?\s*([^\n]+)", block, re.I).group(1).strip() if re.search(r"Localidad\s*[:\-]?\s*([^\n]+)", block, re.I) else ""),
                "codigo_postal": (re.search(r"C[oó]digo postal\s*[:\-]?\s*([^\n]+)", block, re.I).group(1).strip() if re.search(r"C[oó]digo postal\s*[:\-]?\s*([^\n]+)", block, re.I) else ""),
                "provincia": (re.search(r"Provincia\s*[:\-]?\s*([^\n]+)", block, re.I).group(1).strip() if re.search(r"Provincia\s*[:\-]?\s*([^\n]+)", block, re.I) else "")})
        taxes = []
        for match in re.finditer(r"\b(\d{2,4})\s+([^\n]{3,100}?(?:MONOTRIBUTO|GANANCIAS|IVA|IIBB|INGRESOS BRUTOS|MUNICIPAL)[^\n]*)", compact, re.I):
            description = match.group(2).strip()
            state = "Baja definitiva" if "baja definitiva" in description.casefold() else ("No alcanzado" if "no aportante" in description.casefold() or "no alcanzado" in description.casefold() else "Activo")
            taxes.append({"codigo": match.group(1), "descripcion": description, "estado": state,
                          "periodo_desde": first((r"Per[ií]odo desde\s*[:\-]?\s*([^\n]+)",)), "motivo": ""})
        activities = []
        for match in re.finditer(r"(?:Actividad|C[oó]digo de actividad)\s*[:\-]?\s*(\d{3,8})\s+([^\n]+)", compact, re.I):
            activities.append({"codigo": match.group(1), "descripcion": match.group(2).strip(), "orden": len(activities) + 1})
        characterizations = []
        for match in re.finditer(r"(?:Caracterizaci[oó]n|Categor[ií]a de riesgo)\s*[:\-]?\s*([^\n]+)", compact, re.I):
            characterizations.append({"descripcion": match.group(1).strip(), "estado": "Activa", "periodo_desde": ""})
        category_match = re.search(r"(?:Categor[ií]a|MONOTRIBUTO)\s*[:\-]?\s*([A-K])\b\s*([^\n]*)", compact, re.I)
        mono = {"categoria": category_match.group(1).upper() if category_match else "",
                "descripcion": category_match.group(2).strip() if category_match else "",
                "tipo_actividad": "Servicios" if category_match and "serv" in category_match.group(2).casefold() else ("Venta de cosas muebles" if category_match else "")}
        digital = {
            "foto_registrada": "Sí" if re.search(r"foto.{0,30}(registrada|s[ií])", compact, re.I) else "A revisar",
            "firma_registrada": "Sí" if re.search(r"firma.{0,30}(registrada|s[ií])", compact, re.I) else "A revisar",
            "huella_registrada": "Sí" if re.search(r"huella.{0,30}(registrada|s[ií])", compact, re.I) else "A revisar",
            "domicilio_fiscal_electronico": fields["dfe"],
            "fecha_alta": first((r"Datos digitales[\s\S]{0,200}?Fecha de alta\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",)),
            "fecha_actualizacion": first((r"Datos digitales[\s\S]{0,250}?Fecha de actualizaci[oó]n\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",)),
        }
        migratory = {"tipo_residencia": first((r"Tipo de residencia\s*[:\-]?\s*([^\n]+)",)),
            "vencimiento_migratorio": first((r"(?:Vencimiento migratorio|Fecha vencimiento migraci[oó]n)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",)),
            "documento_extranjero": first((r"Documento extranjero\s*[:\-]?\s*([^\n]+)",)),
            "fecha_actualizacion": ""}
        existing = self.database.query_one("SELECT id,nombre_razon_social FROM clientes WHERE cuit_cuil=?", (cuit,)) if cuit else None
        return {
            "source": "Sistema Registral ARCA", "path": str(path), "fields": fields,
            "emails": emails, "contactos": contacts, "domicilios": addresses, "impuestos": taxes,
            "actividades": activities, "caracterizaciones": characterizations,
            "datos_digitales": digital, "datos_migratorios": migratory, "monotributo": mono,
            "existing_client_id": int(existing["id"]) if existing else None,
            "existing_client_name": existing["nombre_razon_social"] if existing else "",
            "confidence": "Alta" if cuit and fields["nombre_razon_social"] else "Media",
            "text_length": len(text),
        }

    def import_registry_pdf(self, preview: dict, client_id: int | None = None, replace: bool = False) -> dict:
        fields = preview["fields"]
        client_id = client_id or preview.get("existing_client_id")
        if not client_id:
            if len(fields.get("cuit_cuil", "")) != 11 or not fields.get("nombre_razon_social"):
                raise ValueError("Para crear el cliente se necesitan CUIT y nombre o razón social.")
            client_id = self.database.execute(
                """INSERT INTO clientes(nombre_razon_social,cuit_cuil,tipo_persona,dni,
                   fecha_nacimiento,nacionalidad,telefono,email,estado)
                   VALUES(?,?,?,?,?,?,?,?, 'activo')""",
                (fields["nombre_razon_social"], fields["cuit_cuil"],
                 "sociedad" if any(term in fields.get("tipo_persona_detectado", "").casefold() for term in ("jurid", "sociedad")) else "persona_humana",
                 digits(fields.get("dni", "")), normalize_date(fields["fecha_nacimiento"]) if fields.get("fecha_nacimiento") else None,
                 fields.get("nacionalidad", ""), fields.get("telefono", ""), fields.get("email", "")),
            )
        current = self.database.query_one("SELECT * FROM clientes WHERE id=?", (client_id,))
        if not current:
            raise ValueError("El cliente seleccionado no existe.")
        self.database.execute(
            "INSERT OR IGNORE INTO datos_fiscales_cliente(cliente_id,regimen_principal) VALUES(?, 'sin_definir')",
            (client_id,),
        )
        replacements = 0
        client_columns = ("nombre_razon_social", "dni", "fecha_nacimiento", "nacionalidad", "telefono", "email")
        updates = {}
        for column in client_columns:
            detected = fields.get(column, "")
            if detected and (replace or not current[column]):
                updates[column] = normalize_date(detected) if column == "fecha_nacimiento" else detected
                replacements += int(bool(current[column]))
        if updates:
            assignments = ",".join(f"{column}=?" for column in updates)
            self.database.execute(f"UPDATE clientes SET {assignments},actualizado_en=CURRENT_TIMESTAMP WHERE id=?", (*updates.values(), client_id))
        import_id = self.database.execute(
            """INSERT INTO historial_importaciones_contables(
                   cliente_id,fuente,archivo,filas_leidas,filas_importadas,filas_revisar,estado,metadatos_json)
               VALUES(?,?,?,?,?,?,?,?)""",
            (client_id, "Sistema Registral ARCA", Path(preview["path"]).name, preview["text_length"],
             len(updates) + len(preview["domicilios"]) + len(preview["impuestos"]) + len(preview["actividades"]) + len(preview.get("contactos", [])) + len(preview.get("caracterizaciones", [])),
             int(preview["confidence"] != "Alta"), "Importado correctamente" if preview["confidence"] == "Alta" else "Importado con advertencias",
             json.dumps({"fields": fields, "emails": preview["emails"], "digital": preview.get("datos_digitales", {}), "migratory": preview.get("datos_migratorios", {})}, ensure_ascii=False)),
        )
        client_main = {"cuit_cuil", "nombre_razon_social", "dni", "fecha_nacimiento", "nacionalidad", "telefono", "email"}
        for key, detected in fields.items():
            if key in client_main or not detected:
                continue
            existing_field = self.database.query_one(
                "SELECT valor FROM cliente_legajo_campos WHERE cliente_id=? AND seccion='arca' AND campo=?",
                (client_id, key),
            )
            if existing_field and existing_field["valor"] and not replace:
                continue
            self.database.execute(
                """INSERT INTO cliente_legajo_campos(cliente_id,seccion,campo,valor)
                   VALUES(?, 'arca', ?, ?) ON CONFLICT(cliente_id,seccion,campo)
                   DO UPDATE SET valor=excluded.valor,actualizado_en=CURRENT_TIMESTAMP""",
                (client_id, key, detected),
            )
        for row in preview["domicilios"]:
            if row.get("accion") == "No importar": continue
            self.database.execute(
                """INSERT INTO arca_domicilios(cliente_id,tipo,estado,direccion,localidad,
                   codigo_postal,provincia,orden,nomenclado,fecha_baja,fecha_actualizacion,
                   coordenadas,observaciones,id_importacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (client_id,row.get("tipo",""),row.get("estado",""),row.get("direccion",""),
                 row.get("localidad",""),row.get("codigo_postal",""),row.get("provincia",""),
                 int(row.get("orden",0) or 0),row.get("nomenclado",""),row.get("fecha_baja") or None,
                 row.get("fecha_actualizacion") or None,row.get("coordenadas",""),row.get("observaciones",""),import_id),
            )
        for row in preview.get("contactos", []):
            if row.get("accion") == "No importar": continue
            self.database.execute(
                """INSERT INTO arca_contactos(cliente_id,clase,valor,tipo,pais,area,numero,
                   compania,alias,estado,fecha_actualizacion,principal,id_importacion)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (client_id,row["clase"],row["valor"],row.get("tipo",""),row.get("pais",""),
                 row.get("area",""),row.get("numero",""),row.get("compania",""),row.get("alias",""),
                 row.get("estado",""),row.get("fecha_actualizacion") or None,int(row.get("principal",0)),import_id),
            )
        for row in preview.get("caracterizaciones", []):
            if row.get("accion") == "No importar": continue
            self.database.execute(
                """INSERT INTO arca_caracterizaciones(cliente_id,descripcion,periodo_desde,
                   dia_periodo,codigo_impuesto,impuesto,fecha_actualizacion,domicilios,estado,id_importacion)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (client_id,row["descripcion"],row.get("periodo_desde",""),row.get("dia_periodo",""),
                 row.get("codigo_impuesto",""),row.get("impuesto",""),row.get("fecha_actualizacion") or None,
                 row.get("domicilios",""),row.get("estado","Activa"),import_id),
            )
        for row in preview["impuestos"]:
            if row.get("accion") == "No importar": continue
            self.database.execute(
                """INSERT INTO arca_impuestos(cliente_id,codigo,descripcion,periodo_desde,
                   dia_periodo,estado,motivo,fecha_inscripcion,fecha_actualizacion,id_importacion)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (client_id,row.get("codigo",""),row["descripcion"],row.get("periodo_desde",""),
                 row.get("dia_periodo",""),row.get("estado","Activo"),row.get("motivo",""),
                 row.get("fecha_inscripcion") or None,row.get("fecha_actualizacion") or None,import_id),
            )
        for row in preview["actividades"]:
            if row.get("accion") == "No importar": continue
            self.database.execute(
                """INSERT INTO arca_actividades(cliente_id,nomenclador,codigo,descripcion,condicion,
                   orden,periodo_desde,fecha_actualizacion,tipo,id_importacion)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (client_id,row.get("nomenclador",""),row["codigo"],row["descripcion"],row.get("condicion",""),
                 row.get("orden",0),row.get("periodo_desde",""),row.get("fecha_actualizacion") or None,
                 row.get("tipo","Económica"),import_id),
            )
        digital = preview.get("datos_digitales", {})
        self.database.execute(
            """INSERT INTO arca_datos_digitales(cliente_id,foto_registrada,firma_registrada,
               huella_registrada,domicilio_fiscal_electronico,fecha_alta,fecha_actualizacion,id_importacion)
               VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(cliente_id) DO UPDATE SET
               foto_registrada=excluded.foto_registrada,firma_registrada=excluded.firma_registrada,
               huella_registrada=excluded.huella_registrada,
               domicilio_fiscal_electronico=excluded.domicilio_fiscal_electronico,
               fecha_alta=excluded.fecha_alta,fecha_actualizacion=excluded.fecha_actualizacion,
               id_importacion=excluded.id_importacion""",
            (client_id,digital.get("foto_registrada","A revisar"),digital.get("firma_registrada","A revisar"),
             digital.get("huella_registrada","A revisar"),digital.get("domicilio_fiscal_electronico","A revisar"),
             digital.get("fecha_alta") or None,digital.get("fecha_actualizacion") or None,import_id),
        )
        migratory = preview.get("datos_migratorios", {})
        if any(migratory.values()):
            self.database.execute(
                """INSERT INTO arca_datos_migratorios(cliente_id,tipo_residencia,
                   vencimiento_migratorio,documento_extranjero,fecha_actualizacion,id_importacion)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(cliente_id) DO UPDATE SET
                   tipo_residencia=excluded.tipo_residencia,vencimiento_migratorio=excluded.vencimiento_migratorio,
                   documento_extranjero=excluded.documento_extranjero,fecha_actualizacion=excluded.fecha_actualizacion,
                   id_importacion=excluded.id_importacion""",
                (client_id,migratory.get("tipo_residencia",""),migratory.get("vencimiento_migratorio") or None,
                 migratory.get("documento_extranjero",""),migratory.get("fecha_actualizacion") or None,import_id),
            )
        if preview["actividades"]:
            activity = preview["actividades"][0]
            self.database.execute("UPDATE clientes SET actividad=?,rubro=? WHERE id=?", (activity["descripcion"], activity["descripcion"], client_id))
            self.database.execute(
                """INSERT INTO monotributo_cliente(cliente_id,actividad,actividad_fiscal,codigo_actividad)
                   VALUES(?,?,?,?) ON CONFLICT(cliente_id) DO UPDATE SET actividad=excluded.actividad,
                   actividad_fiscal=excluded.actividad_fiscal,codigo_actividad=excluded.codigo_actividad""",
                (client_id, activity["descripcion"], activity["descripcion"], activity["codigo"]),
            )
        mono = preview.get("monotributo", {})
        if mono.get("categoria"):
            self.database.execute(
                """INSERT INTO monotributo_cliente(cliente_id,categoria_actual,tipo_actividad)
                   VALUES(?,?,?) ON CONFLICT(cliente_id) DO UPDATE SET
                   categoria_actual=excluded.categoria_actual,tipo_actividad=excluded.tipo_actividad""",
                (client_id,mono["categoria"],mono.get("tipo_actividad") or "Servicios"),
            )
        for tax in preview["impuestos"]:
            description=tax["descripcion"].casefold()
            if "monotributo" in description:
                self.database.execute("UPDATE datos_fiscales_cliente SET regimen_principal='monotributista' WHERE cliente_id=?",(client_id,))
            if "iibb" in description or "ingresos brutos" in description:
                regime="Convenio Multilateral" if "convenio" in description else "Régimen simplificado" if "simplificado" in description else "Régimen general/local"
                self.database.execute(
                    """INSERT INTO ingresos_brutos_cliente(cliente_id,regimen_principal,jurisdiccion)
                       VALUES(?,?,?) ON CONFLICT(cliente_id) DO UPDATE SET regimen_principal=excluded.regimen_principal""",
                    (client_id,regime,"Buenos Aires" if "arba" in description else ""),
                )
        arca_record = {
            "estado_cuit":"Activo", "domicilio_fiscal_electronico":"Adherido" if fields.get("dfe")=="Sí" else "No adherido" if fields.get("dfe")=="No" else "A revisar",
            "fecha_inscripcion_arca":fields.get("fecha_inscripcion",""),"mes_cierre":fields.get("mes_cierre",""),
            "dependencia":fields.get("dependencia",""),"region":fields.get("region",""),
            "tipo_inscripcion":fields.get("tipo_inscripcion",""),"sistema_control":fields.get("sistema_control",""),
            "segmento":fields.get("segmento",""),"ultima_actualizacion":fields.get("ultima_actualizacion",""),
            "foto_registrada":digital.get("foto_registrada","A revisar"),"firma_registrada":digital.get("firma_registrada","A revisar"),
            "huella_registrada":digital.get("huella_registrada","A revisar"),"estado_control":"Revisar" if preview["confidence"]!="Alta" else "OK",
            "observaciones":"Impuestos: "+"; ".join(row["descripcion"] for row in preview["impuestos"])+" | Actividades: "+"; ".join(row["descripcion"] for row in preview["actividades"]),
        }
        self.database.execute(
            """INSERT INTO cliente_legajo_registros(cliente_id,seccion,fecha,descripcion,estado,
               datos_json,responsable) VALUES(?,'arca',?,'Importación Sistema Registral ARCA',?,?, 'NATALIA')""",
            (client_id,date.today().isoformat(),"A revisar" if preview["confidence"]!="Alta" else "OK",json.dumps(arca_record,ensure_ascii=False)),
        )
        for row in preview.get("contactos",[]):
            if row.get("accion")=="No importar":continue
            data={**row,"principal":"Sí" if row.get("principal") else "No"}
            self.database.execute(
                """INSERT INTO cliente_legajo_registros(cliente_id,seccion,fecha,descripcion,estado,
                   datos_json,responsable) VALUES(?,'contactos_arca',?,?,?,?,'NATALIA')""",
                (client_id,date.today().isoformat(),f"{row['clase']}: {row['valor']}",row.get("estado","A revisar"),json.dumps(data,ensure_ascii=False)),
            )
        for row in preview.get("domicilios",[]):
            if row.get("accion")=="No importar":continue
            self.database.execute(
                """INSERT INTO cliente_legajo_registros(cliente_id,seccion,fecha,descripcion,estado,
                   datos_json,responsable) VALUES(?,'domicilios_arca',?,?,?,?,'NATALIA')""",
                (client_id,date.today().isoformat(),f"{row.get('tipo','Domicilio')}: {row.get('direccion','')}",row.get("estado","A revisar"),json.dumps(row,ensure_ascii=False)),
            )
        if any(migratory.values()):
            self.database.execute(
                """INSERT INTO cliente_legajo_registros(cliente_id,seccion,fecha,descripcion,estado,
                   datos_json,responsable) VALUES(?,'migratorios_arca',?,'Datos migratorios importados',
                   'A revisar',?,'NATALIA')""",
                (client_id,date.today().isoformat(),json.dumps(migratory,ensure_ascii=False)),
            )
        alerts=[]
        if fields.get("dfe") == "No": alerts.append(("dfe_no_adherido","Domicilio Fiscal Electrónico no adherido.","alta"))
        if not preview.get("emails"): alerts.append(("email_tributario_faltante","No se detectó email tributario en Sistema Registral.","media"))
        if not any(row["clase"]=="Teléfono" for row in preview.get("contactos",[])): alerts.append(("telefono_faltante","No se detectó teléfono confirmado en Sistema Registral.","media"))
        if preview["confidence"] != "Alta": alerts.append(("datos_arca_revisar","La importación ARCA contiene datos de confianza media o baja.","media"))
        for row in preview.get("caracterizaciones",[]):
            if "riesgo" in row["descripcion"].casefold(): alerts.append(("riesgo_fiscal_arca",row["descripcion"],"alta"))
        for alert_type,description,severity in alerts:
            self.database.execute("INSERT INTO alertas_fiscales(cliente_id,tipo_alerta,descripcion,gravedad) VALUES(?,?,?,?)",(client_id,alert_type,description,severity))
        if alerts:
            self.database.execute(
                """INSERT INTO tareas(cliente_id,modulo,titulo,descripcion,responsable,estado,prioridad)
                   VALUES(?,'ARCA','Revisar importación de Sistema Registral',?,'NATALIA','pendiente','alta')""",
                (client_id,"; ".join(item[1] for item in alerts)),
            )
        self.database.execute(
            """INSERT INTO cliente_legajo_registros(cliente_id,seccion,fecha,descripcion,estado,
               datos_json,responsable) VALUES(?,'eventos',?,'Importación de Sistema Registral ARCA',
               'Finalizado',?,'NATALIA')""",
            (client_id,date.today().isoformat(),json.dumps({"fecha":date.today().isoformat(),"area":"ARCA","tipo_evento":"Modificación","descripcion":"Importación de Sistema Registral ARCA","responsable":"NATALIA","estado":"Finalizado","prioridad":"Media","observaciones":Path(preview["path"]).name},ensure_ascii=False)),
        )
        return {"import_id": import_id, "client_id": client_id, "updated": len(updates), "replaced": replacements}

    def history(self, source: str = "", client_id: int | None = None) -> list[dict]:
        conditions = ["1=1"]
        params: list[object] = []
        if source:
            conditions.append("h.fuente=?")
            params.append(source)
        if client_id:
            conditions.append("h.cliente_id=?")
            params.append(client_id)
        return [dict(row) for row in self.database.query(
            f"""SELECT h.*,COALESCE(c.nombre_razon_social,'') cliente
                FROM historial_importaciones_contables h LEFT JOIN clientes c ON c.id=h.cliente_id
                WHERE {' AND '.join(conditions)} ORDER BY h.fecha_importacion DESC""", params)]
