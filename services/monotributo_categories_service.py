from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from database import Database


def _amount(text: str) -> float:
    cleaned = re.sub(r"[^0-9,.-]", "", text.strip())
    if not cleaned:
        return 0.0
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


class MonotributoCategoriesService:
    FIELDS = (
        "tope_ingresos", "tope_superficie", "tope_energia", "tope_alquileres",
        "precio_unitario_maximo", "impuesto_integrado_servicios",
        "impuesto_integrado_ventas", "aporte_sipa", "aporte_obra_social",
        "total_servicios", "total_ventas",
    )

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _pdf_text(path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError("Instalá las dependencias para leer categorías desde PDF.") from error
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        if not text.strip():
            raise ValueError("El PDF no contiene texto seleccionable. Puede cargar los valores manualmente.")
        return text

    def preview_pdf(self, path: Path) -> dict:
        text = self._pdf_text(path)
        vigencia_match = re.search(
            r"(?:aplicaci[oó]n|vigencia|vigentes?)\D{0,40}(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            text, re.I,
        )
        vigencia = ""
        if vigencia_match:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                try:
                    vigencia = datetime.strptime(vigencia_match.group(1), fmt).date().isoformat()
                    break
                except ValueError:
                    pass
        if not vigencia:
            vigencia = date.today().isoformat()

        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
        rows: list[dict] = []
        for category in "ABCDEFGHIJK":
            candidates = [line for line in lines if re.match(rf"^(?:Categor[ií]a\s+)?{category}\b", line, re.I)]
            values: list[float] = []
            raw = candidates[0] if candidates else ""
            if raw:
                tokens = re.findall(r"(?:\$\s*)?-?\d[\d.]*,\d{2}|\d+(?:[.,]\d+)?", raw)
                values = [_amount(token) for token in tokens]
            row = {"categoria": category, "vigencia_desde": vigencia, "estado": "Vigente",
                   "fuente": "ARCA PDF", "archivo_origen": path.name,
                   "confianza": "Alta" if len(values) >= 9 else ("Media" if values else "A revisar"),
                   "accion": "Importar", "observaciones": "", "raw": raw}
            for index, field in enumerate(self.FIELDS):
                row[field] = values[index] if index < len(values) else 0.0
            rows.append(row)
        references = "\n".join(line for line in lines if re.match(r"^(?:\*|\(|Nota|Referencia)", line, re.I))
        return {"source": "ARCA Monotributo Categorías PDF", "path": str(path),
                "vigencia": vigencia, "records": rows, "referencias": references,
                "text_length": len(text)}

    def import_preview(self, preview: dict, conflict_action: str = "replace") -> dict:
        if conflict_action not in ("replace", "skip", "new"):
            raise ValueError("La acción ante versiones repetidas no es válida.")
        imported = duplicates = review = 0
        import_id = self.database.execute(
            """INSERT INTO historial_importaciones_contables(
                   fuente,archivo,filas_leidas,vigencia_detectada,metadatos_json)
               VALUES(?,?,?,?,?)""",
            ("ARCA Monotributo Categorías PDF", Path(preview["path"]).name,
             len(preview["records"]), preview["vigencia"], "{}"),
        )
        with self.database.connection() as connection:
            existing_vigence = connection.execute(
                "SELECT COUNT(*) n FROM categorias_monotributo WHERE vigencia_desde=?",
                (preview["vigencia"],),
            ).fetchone()["n"]
            if existing_vigence and conflict_action == "new":
                # SQLite conserva la restricción histórica (categoría, vigencia).
                raise ValueError("Ya existe esa vigencia. Elija reemplazar u omitir.")
            if not existing_vigence:
                connection.execute(
                    "UPDATE categorias_monotributo SET estado='Histórico',vigencia_hasta=? WHERE estado='Vigente'",
                    (preview["vigencia"],),
                )
            for row in preview["records"]:
                if row.get("accion") == "No importar":
                    continue
                current = connection.execute(
                    "SELECT id FROM categorias_monotributo WHERE categoria=? AND vigencia_desde=?",
                    (row["categoria"], row["vigencia_desde"]),
                ).fetchone()
                if current:
                    duplicates += 1
                    if conflict_action == "skip":
                        continue
                values = tuple(float(row.get(field, 0) or 0) for field in self.FIELDS)
                common = (*values, row["estado"], row["fuente"], row["archivo_origen"],
                          datetime.now().isoformat(timespec="seconds"), preview.get("referencias", ""),
                          row.get("observaciones", ""))
                if current:
                    connection.execute(
                        """UPDATE categorias_monotributo SET tope_ingresos=?,tope_superficie=?,
                           tope_energia=?,tope_alquileres=?,precio_unitario_maximo=?,
                           impuesto_integrado_servicios=?,impuesto_integrado_ventas=?,aporte_sipa=?,
                           aporte_obra_social=?,total_servicios=?,total_ventas=?,estado=?,fuente=?,
                           archivo_origen=?,fecha_importacion=?,referencias=?,observaciones=? WHERE id=?""",
                        (*common, current["id"]),
                    )
                else:
                    connection.execute(
                        """INSERT INTO categorias_monotributo(
                           categoria,vigencia_desde,tope_ingresos,tope_superficie,tope_energia,
                           tope_alquileres,precio_unitario_maximo,impuesto_integrado_servicios,
                           impuesto_integrado_ventas,aporte_sipa,aporte_obra_social,total_servicios,
                           total_ventas,estado,fuente,archivo_origen,fecha_importacion,referencias,observaciones)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["categoria"], row["vigencia_desde"], *common),
                    )
                imported += 1
                review += int(row.get("confianza") == "A revisar")
        state = "Importado con advertencias" if review else "Importado correctamente"
        self.database.execute(
            """UPDATE historial_importaciones_contables SET filas_importadas=?,
               filas_duplicadas=?,filas_revisar=?,estado=? WHERE id=?""",
            (imported, duplicates, review, state, import_id),
        )
        return {"import_id": import_id, "imported": imported, "duplicates": duplicates, "review": review}

    def list_versions(self, only_current: bool = False) -> list[dict]:
        condition = "WHERE estado='Vigente'" if only_current else ""
        return [dict(row) for row in self.database.query(
            f"""SELECT * FROM categorias_monotributo {condition}
                ORDER BY vigencia_desde DESC,
                CASE categoria WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3
                WHEN 'D' THEN 4 WHEN 'E' THEN 5 WHEN 'F' THEN 6 WHEN 'G' THEN 7
                WHEN 'H' THEN 8 WHEN 'I' THEN 9 WHEN 'J' THEN 10 ELSE 11 END"""
        )]

    def update(self, category_id: int, values: dict, responsible: str = "NATALIA", reason: str = "") -> None:
        current = self.database.query_one("SELECT * FROM categorias_monotributo WHERE id=?", (category_id,))
        if not current:
            raise ValueError("La categoría ya no existe.")
        allowed = set(self.FIELDS) | {"categoria", "vigencia_desde", "vigencia_hasta", "estado", "fuente", "observaciones"}
        changes = {key: values[key] for key in values if key in allowed and str(values[key]) != str(current[key] or "")}
        if not changes:
            return
        with self.database.connection() as connection:
            connection.execute(
                f"UPDATE categorias_monotributo SET {','.join(f'{key}=?' for key in changes)} WHERE id=?",
                (*changes.values(), category_id),
            )
            connection.executemany(
                """INSERT INTO historial_categorias_monotributo(
                       categoria_id,campo,valor_anterior,valor_nuevo,responsable,motivo)
                   VALUES(?,?,?,?,?,?)""",
                [(category_id, key, str(current[key] or ""), str(value), responsible, reason)
                 for key, value in changes.items()],
            )

    def client_payment(self, client_id: int) -> dict:
        profile = self.database.query_one(
            "SELECT * FROM monotributo_cliente WHERE cliente_id=?", (client_id,)
        )
        if not profile or not profile["categoria_actual"]:
            return {"category": "", "activity": "", "integrated_tax": 0.0, "sipa": 0.0,
                    "health": 0.0, "adherents": 0.0, "table_total": 0.0,
                    "adjusted_total": 0.0, "vigencia": "", "source": ""}
        category = self.database.query_one(
            """SELECT * FROM categorias_monotributo WHERE categoria=? AND estado='Vigente'
               ORDER BY vigencia_desde DESC LIMIT 1""", (profile["categoria_actual"],)
        )
        if not category:
            category = self.database.query_one(
                "SELECT * FROM categorias_monotributo WHERE categoria=? ORDER BY vigencia_desde DESC LIMIT 1",
                (profile["categoria_actual"],),
            )
        if not category:
            return {"category": profile["categoria_actual"], "activity": profile["tipo_actividad"],
                    "integrated_tax": 0.0, "sipa": 0.0, "health": 0.0, "adherents": 0.0,
                    "table_total": 0.0, "adjusted_total": 0.0, "vigencia": "", "source": ""}
        sale_activity = "venta" in (profile["tipo_actividad"] or "").casefold()
        integrated = float(category["impuesto_integrado_ventas" if sale_activity else "impuesto_integrado_servicios"] or 0)
        sipa = float(category["aporte_sipa"] or 0) if profile["aporta_sipa"] == "Sí" else 0.0
        health_base = float(category["aporte_obra_social"] or 0)
        health = health_base if profile["aporta_obra_social"] == "Sí" else 0.0
        adherents = int(profile["adherentes_obra_social"] or 0) * health_base
        table_total = float(category["total_ventas" if sale_activity else "total_servicios"] or 0)
        return {"category": profile["categoria_actual"], "activity": profile["tipo_actividad"],
                "integrated_tax": integrated, "sipa": sipa, "health": health,
                "adherents": adherents, "table_total": table_total,
                "adjusted_total": integrated + sipa + health + adherents,
                "vigencia": category["vigencia_desde"], "source": category["fuente"],
                "limits": {field: float(category[field] or 0) for field in self.FIELDS[:5]}}
