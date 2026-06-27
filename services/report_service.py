from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from .voucher_service import VoucherService


class ReportService:
    """Exportaciones básicas de la Etapa 1."""

    def __init__(self, vouchers: VoucherService) -> None:
        self.vouchers = vouchers
        self.database = vouchers.database

    REPORTS = {
        "ventas_mensuales": "Ventas mensuales por cliente",
        "compras_mensuales": "Compras mensuales por proveedor",
        "ventas_anio": "Ventas acumuladas año calendario",
        "ventas_12": "Ventas últimos 12 meses",
        "compras_anio": "Compras acumuladas año calendario",
        "compras_12": "Compras últimos 12 meses",
        "recategorizacion": "Recategorización de monotributo",
        "significativos": "Comprobantes significativos",
        "usd": "Comprobantes en USD",
        "iibb": "Ingresos Brutos mensual",
        "alertas": "Alertas fiscales",
        "ranking_clientes": "Ranking de clientes por ventas",
        "ranking_proveedores": "Ranking de proveedores por compras",
        "documentacion": "Documentación pendiente",
        "tareas": "Tareas pendientes",
        "honorarios": "Honorarios pendientes",
    }

    def export_named(self, report: str, destination: Path, client_id: int | None = None) -> Path:
        if report not in self.REPORTS:
            raise ValueError("El reporte seleccionado no existe.")
        condition = " AND cliente_id = ?" if client_id else ""
        params = (client_id,) if client_id else ()
        year = pd.Timestamp.today().year
        queries = {
            "ventas_mensuales": "SELECT periodo_fiscal AS periodo, contraparte_nombre, contraparte_documento, COUNT(*) cantidad, SUM(importe_neto_fiscal) total FROM comprobantes_ventas WHERE 1=1"+condition+" GROUP BY periodo_fiscal, contraparte_nombre, contraparte_documento ORDER BY periodo_fiscal DESC, total DESC",
            "compras_mensuales": "SELECT periodo_fiscal AS periodo, contraparte_nombre, contraparte_documento, COUNT(*) cantidad, SUM(importe_neto_fiscal) total FROM comprobantes_compras WHERE 1=1"+condition+" GROUP BY periodo_fiscal, contraparte_nombre, contraparte_documento ORDER BY periodo_fiscal DESC, total DESC",
            "ventas_anio": "SELECT * FROM comprobantes_ventas WHERE periodo_fiscal LIKE '"+str(year)+"-%'"+condition+" ORDER BY fecha",
            "ventas_12": "SELECT * FROM comprobantes_ventas WHERE fecha >= date('now','-12 months')"+condition+" ORDER BY fecha",
            "compras_anio": "SELECT * FROM comprobantes_compras WHERE periodo_fiscal LIKE '"+str(year)+"-%'"+condition+" ORDER BY fecha",
            "compras_12": "SELECT * FROM comprobantes_compras WHERE fecha >= date('now','-12 months')"+condition+" ORDER BY fecha",
            "recategorizacion": "SELECT * FROM recategorizaciones_monotributo WHERE 1=1"+condition+" ORDER BY creado_en DESC",
            "usd": "SELECT 'Venta' operacion, * FROM comprobantes_ventas WHERE moneda='USD'"+condition+" UNION ALL SELECT 'Compra' operacion, * FROM comprobantes_compras WHERE moneda='USD'"+condition,
            "iibb": "SELECT * FROM iibb_monotributo WHERE 1=1"+condition+" ORDER BY periodo DESC",
            "alertas": "SELECT * FROM alertas_fiscales WHERE 1=1"+condition+" ORDER BY fecha_creacion DESC",
            "documentacion": "SELECT * FROM documentacion WHERE estado NOT IN ('Aprobada','aprobada')"+condition+" ORDER BY id DESC",
            "tareas": "SELECT * FROM tareas WHERE estado NOT IN ('finalizado','archivado','cobrado')"+condition+" ORDER BY fecha_vencimiento",
            "honorarios": "SELECT * FROM honorarios WHERE estado NOT IN ('cobrado total')"+condition+" ORDER BY id DESC",
            "ranking_clientes": "SELECT contraparte_nombre,contraparte_documento,COUNT(*) cantidad,SUM(importe_neto_fiscal) total FROM comprobantes_ventas WHERE 1=1"+condition+" GROUP BY contraparte_nombre,contraparte_documento ORDER BY total DESC",
            "ranking_proveedores": "SELECT contraparte_nombre,contraparte_documento,COUNT(*) cantidad,SUM(importe_neto_fiscal) total FROM comprobantes_compras WHERE 1=1"+condition+" GROUP BY contraparte_nombre,contraparte_documento ORDER BY total DESC",
        }
        if report == "significativos":
            threshold = self.vouchers.config.get_float("monto_comprobante_significativo", 500000)
            sql = "SELECT 'Venta' operacion, * FROM comprobantes_ventas WHERE ABS(importe_pesos)>=?"+condition+" UNION ALL SELECT 'Compra' operacion, * FROM comprobantes_compras WHERE ABS(importe_pesos)>=?"+condition
            query_params = (threshold, *params, threshold, *params)
        else:
            sql = queries[report]
            query_params = (*params, *params) if report == "usd" else params
        rows = [dict(row) for row in self.database.query(sql, query_params)]
        if not rows:
            raise ValueError("No hay datos para el reporte seleccionado.")
        dataframe = pd.DataFrame(rows)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(destination, engine="openpyxl") as writer:
            dataframe.to_excel(writer, sheet_name="Reporte", index=False)
        workbook = load_workbook(destination); sheet = workbook.active
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for cell in sheet[1]: cell.fill=header_fill; cell.font=Font(color="FFFFFF",bold=True)
        sheet.freeze_panes="A2"; sheet.auto_filter.ref=sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width=min(max(len(str(c.value or "")) for c in column)+2,38)
        workbook.save(destination)
        return destination

    def export_vouchers(
        self,
        kind: str,
        destination: Path,
        client_id: int | None = None,
        period: str = "",
    ) -> Path:
        rows = self.vouchers.list(kind, client_id=client_id, period=period)
        if not rows:
            raise ValueError("No hay comprobantes para exportar con los filtros actuales.")
        dataframe = pd.DataFrame(rows)
        columns = [
            "cliente_nombre",
            "fecha",
            "periodo_fiscal",
            "tipo_comprobante",
            "punto_venta",
            "numero_comprobante",
            "contraparte_nombre",
            "contraparte_documento",
            "moneda",
            "tipo_cambio",
            "importe_original",
            "importe_pesos",
            "importe_neto_fiscal",
            "estado",
            "origen",
            "observaciones",
        ]
        labels = {
            "cliente_nombre": "Cliente del estudio",
            "fecha": "Fecha",
            "periodo_fiscal": "Período",
            "tipo_comprobante": "Tipo",
            "punto_venta": "Punto de venta",
            "numero_comprobante": "Número",
            "contraparte_nombre": "Cliente / proveedor",
            "contraparte_documento": "CUIT / DNI",
            "moneda": "Moneda",
            "tipo_cambio": "Tipo de cambio",
            "importe_original": "Importe original",
            "importe_pesos": "Importe en pesos",
            "importe_neto_fiscal": "Importe neto fiscal",
            "estado": "Estado",
            "origen": "Origen",
            "observaciones": "Observaciones",
        }
        dataframe = dataframe[columns].rename(columns=labels)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(destination, engine="openpyxl") as writer:
            dataframe.to_excel(writer, sheet_name=kind.capitalize(), index=False)

        workbook = load_workbook(destination)
        sheet = workbook.active
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 38)
            sheet.column_dimensions[column[0].column_letter].width = width
        for row in sheet.iter_rows(min_row=2):
            for index in (10, 11, 12):
                row[index].number_format = '"$"#,##0.00;[Red]-"$"#,##0.00'
        workbook.save(destination)
        return destination

    def export_accounting_section(
        self,
        kind: str,
        section: str,
        destination: Path,
        client_id: int,
    ) -> Path:
        """Exporta exactamente una sección analítica del módulo contable."""
        configurations = {
            "resumen_mensual": {
                "sheet": "Resumen mensual",
                "rows": lambda: self.vouchers.monthly_summary(kind, client_id),
                "columns": (
                    "periodo", "facturas", "notas_credito", "notas_debito",
                    "anulados", "total_neto", "cantidad",
                ),
                "labels": (
                    "Período", "Facturas", "Notas de crédito", "Notas de débito",
                    "Comprobantes anulados", "Neto", "Cantidad",
                ),
                "formats": {
                    "Facturas": '"$"#,##0.00;[Red]-"$"#,##0.00',
                    "Notas de crédito": '"$"#,##0.00;[Red]-"$"#,##0.00',
                    "Notas de débito": '"$"#,##0.00;[Red]-"$"#,##0.00',
                    "Neto": '"$"#,##0.00;[Red]-"$"#,##0.00',
                    "Comprobantes anulados": "#,##0",
                    "Cantidad": "#,##0",
                },
            },
            "significativos": {
                "sheet": "Significativos",
                "rows": lambda: self.vouchers.noteworthy(kind, client_id),
                "columns": (
                    "fecha", "tipo_comprobante", "contraparte_nombre",
                    "contraparte_documento", "moneda", "importe_pesos",
                    "motivo_alerta",
                ),
                "labels": (
                    "Fecha", "Tipo de comprobante", "Cliente / proveedor",
                    "CUIT / DNI", "Moneda", "Importe en pesos", "Motivo",
                ),
                "formats": {
                    "Importe en pesos": '"$"#,##0.00;[Red]-"$"#,##0.00',
                },
            },
            "moneda_extranjera": {
                "sheet": "Moneda extranjera",
                "rows": lambda: self.vouchers.noteworthy(kind, client_id, True),
                "columns": (
                    "fecha", "tipo_comprobante", "contraparte_nombre", "moneda",
                    "importe_original", "tipo_cambio", "importe_pesos", "estado",
                ),
                "labels": (
                    "Fecha", "Tipo de comprobante", "Cliente / proveedor", "Moneda",
                    "Importe original", "Tipo de cambio", "Importe en pesos", "Estado",
                ),
                "formats": {
                    "Importe original": '#,##0.00;[Red]-#,##0.00',
                    "Tipo de cambio": '#,##0.0000',
                    "Importe en pesos": '"$"#,##0.00;[Red]-"$"#,##0.00',
                },
            },
            "ranking": {
                "sheet": "Ranking",
                "rows": lambda: self.vouchers.ranking(kind, client_id),
                "columns": (
                    "puesto", "contraparte_nombre", "contraparte_documento",
                    "total", "cantidad", "porcentaje",
                ),
                "labels": (
                    "Puesto", "Cliente / proveedor", "CUIT / DNI",
                    "Total", "Cantidad", "Participación",
                ),
                "formats": {
                    "Puesto": "#,##0",
                    "Total": '"$"#,##0.00;[Red]-"$"#,##0.00',
                    "Cantidad": "#,##0",
                    "Participación": "0.0%",
                },
            },
        }
        if section not in configurations:
            raise ValueError("La sección contable seleccionada no existe.")
        if not client_id:
            raise ValueError("Seleccioná un cliente para exportar esta sección.")

        configuration = configurations[section]
        rows = configuration["rows"]()
        if not rows:
            raise ValueError("No hay datos para exportar en esta sección.")
        dataframe = pd.DataFrame(rows)
        dataframe = dataframe[list(configuration["columns"])]
        dataframe.columns = list(configuration["labels"])
        return self._write_dataframe(
            destination,
            dataframe,
            str(configuration["sheet"]),
            configuration["formats"],
        )

    @staticmethod
    def _write_dataframe(
        destination: Path,
        dataframe: pd.DataFrame,
        sheet_name: str,
        number_formats: dict[str, str] | None = None,
    ) -> Path:
        """Escribe una tabla legible, filtrable y con tipos numéricos preservados."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(destination, engine="openpyxl") as writer:
            dataframe.to_excel(writer, sheet_name=sheet_name, index=False)

        workbook = load_workbook(destination)
        sheet = workbook[sheet_name]
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 24
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)

        for column in sheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 38)
            sheet.column_dimensions[column[0].column_letter].width = max(width, 11)

        formats = number_formats or {}
        for column_name, number_format in formats.items():
            column_index = dataframe.columns.get_loc(column_name) + 1
            for row_index in range(2, sheet.max_row + 1):
                sheet.cell(row=row_index, column=column_index).number_format = number_format

        workbook.save(destination)
        return destination
