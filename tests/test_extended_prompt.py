from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from reportlab.pdfgen import canvas

from database import Database, initialize_database
from database.seed import seed_reference_data
from models import Client, FiscalProfile, MonotributoProfile
from services import (
    AdministrativeService, ArcaImportService, ClientService, ConfigService,
    MonotributoCategoriesService, PlatformService, ReportService, VoucherService,
)
from services.monotributo_service import MonotributoService
from services.recategorization_service import RecategorizationService


class ExtendedPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary=tempfile.TemporaryDirectory();self.path=Path(self.temporary.name)
        self.database=Database(self.path/"test.db");initialize_database(self.database);seed_reference_data(self.database)
        self.clients=ClientService(self.database);self.config=ConfigService(self.database)
        self.client_id=self.clients.save(Client("Cliente Extendido","20333444559"),FiscalProfile(regimen_principal="monotributista"),MonotributoProfile(categoria_actual="A"))
    def tearDown(self):self.temporary.cleanup()

    def test_arca_deadlines_preview_import_and_history(self):
        source=self.path/"vencimientos.csv"
        source.write_text("REPORTE ARCA;;;;\nCUIT;Impuesto;Período;Fecha de vencimiento;Importe\n20-33344455-9;IVA;06/2026;18/07/2026;1.234,56\n",encoding="utf-8")
        service=ArcaImportService(self.database);preview=service.preview_deadlines(source)
        self.assertEqual(preview["header_row"],2);self.assertEqual(preview["records"][0]["client_id"],self.client_id)
        result=service.import_deadlines(preview);self.assertEqual(result["imported"],1)
        row=self.database.query_one("SELECT * FROM vencimientos WHERE cliente_id=?",(self.client_id,));self.assertEqual(row["periodo"],"2026-06");self.assertAlmostEqual(row["importe"],1234.56)
        self.assertEqual(len(service.history("ARCA Vencimientos")),1)

    def test_mercado_pago_irregular_csv_detects_summary_and_header(self):
        source=self.path/"mercado_pago.csv"
        source.write_text("INITIAL_BALANCE;CREDITS;DEBITS;FINAL_BALANCE\n1000;500;200;1300\n\nRELEASE_DATE;TRANSACTION_TYPE;REFERENCE_ID;TRANSACTION_NET_AMOUNT;PARTIAL_BALANCE\n01-06-2026;Transferencia recibida Sabrina Frank;REF-1;500;1500\n",encoding="utf-8")
        service=PlatformService(self.database);preview=service.preview_file(source,"mp")
        self.assertEqual(preview["header_row"],4);self.assertEqual(preview["summary"]["saldo_inicial"],1000)
        result=service.import_mercado_pago(source,self.client_id);self.assertEqual(result["imported"],1)
        row=self.database.query_one("SELECT * FROM movimientos_mercado_pago WHERE cliente_id=?",(self.client_id,));self.assertEqual(row["tipo_movimiento"],"Transferencia recibida");self.assertEqual(row["contraparte"],"Sabrina Frank")

    def test_real_mercado_libre_header_and_detail(self):
        source=self.path/"ventas_ml.xlsx"
        rows=[["Informe de ventas"],["Generado por Mercado Libre"],
              ["# de venta","Fecha de venta","Estado","Unidades","Ingresos por productos (ARS)","Cargo por venta","Costo fijo","Ingresos por envío (ARS)","Costos de envío (ARS)","Impuestos","Descuentos y bonificaciones","Anulaciones y reembolsos (ARS)","Total (ARS)","SKU","# de publicación","Título de la publicación","Comprador","DNI","Estado","Reclamo abierto","Con mediación"],
              ["V-1","01/06/2026","Entregada",2,10000,-1000,-200,500,-300,-100,-50,0,8850,"SKU-1","PUB-1","Producto","Comprador Uno","20111222333","Buenos Aires","No","No"]]
        pd.DataFrame(rows).to_excel(source,index=False,header=False,sheet_name="Ventas AR")
        service=PlatformService(self.database);preview=service.preview_file(source,"ml");self.assertEqual(preview["sheet"],"Ventas AR");self.assertEqual(preview["header_row"],3)
        result=service.import_mercado_libre(source,self.client_id);self.assertEqual(result["imported"],1)
        row=self.database.query_one("SELECT * FROM operaciones_mercado_libre WHERE cliente_id=?",(self.client_id,));self.assertEqual(row["sku"],"SKU-1");self.assertEqual(row["provincia"],"Buenos Aires");self.assertAlmostEqual(row["resultado_neto"],8850)
        self.assertEqual(service.ml_products(self.client_id)[0]["unidades_vendidas"],2)

    def test_registry_pdf_creates_editable_ledger_data(self):
        source=self.path/"sistema_registral.pdf";pdf=canvas.Canvas(str(source));pdf.drawString(60,780,"CUIT: 27-12345678-5");pdf.drawString(60,760,"Apellido y nombre: Persona Importada");pdf.drawString(60,740,"Email: persona@example.com");pdf.drawString(60,720,"Domicilio Fiscal Electrónico: No adherido");pdf.drawString(60,700,"Código de actividad: 620100 Servicios informáticos");pdf.save()
        service=ArcaImportService(self.database);preview=service.preview_registry_pdf(source);self.assertEqual(preview["fields"]["cuit_cuil"],"27123456785")
        result=service.import_registry_pdf(preview);self.assertTrue(result["client_id"])
        row=self.database.query_one("SELECT codigo_actividad FROM monotributo_cliente WHERE cliente_id=?",(result["client_id"],));self.assertEqual(row["codigo_actividad"],"620100")
        self.assertTrue(self.database.query_one("SELECT id FROM cliente_legajo_registros WHERE cliente_id=? AND seccion='arca'",(result["client_id"],)))

    def test_category_version_payment_and_customer_matrix(self):
        service=MonotributoCategoriesService(self.database)
        record={"categoria":"A","vigencia_desde":"2026-02-01","estado":"Vigente","fuente":"ARCA PDF","archivo_origen":"categorias.pdf","confianza":"Alta","accion":"Importar","observaciones":""}
        for field in service.FIELDS:record[field]=100.0
        record.update({"tope_ingresos":1000000,"impuesto_integrado_servicios":1000,"aporte_sipa":2000,"aporte_obra_social":3000,"total_servicios":6000})
        result=service.import_preview({"path":str(self.path/"categorias.pdf"),"vigencia":"2026-02-01","records":[record],"referencias":"","text_length":1});self.assertEqual(result["imported"],1)
        payment=service.client_payment(self.client_id);self.assertEqual(payment["adjusted_total"],6000)
        platform=PlatformService(self.database)
        ml=self.path/"simple_ml.xlsx";pd.DataFrame([{"Fecha":"01/06/2026","Importe bruto":100,"Importe neto":100,"Comprador":"Uno","ID venta":"S1"}]).to_excel(ml,index=False)
        platform.import_mercado_libre(ml,self.client_id)
        report=ReportService(VoucherService(self.database,self.config));matrix=report.customer_matrix(self.client_id,2026)
        self.assertEqual(matrix.iloc[-1]["Total"],100)

    def test_platform_partial_import_and_logistics(self):
        source=self.path/"ventas_detalle.xlsx"
        pd.DataFrame([
            {"Fecha de venta":"01/06/2026","Ingresos por productos (ARS)":100,"Total (ARS)":90,"# de venta":"A","Comprador":"Uno","Número de seguimiento":"TRK-A","Transportista":"Correo"},
            {"Fecha de venta":"02/06/2026","Ingresos por productos (ARS)":200,"Total (ARS)":180,"# de venta":"B","Comprador":"Dos","Número de seguimiento":"TRK-B","Transportista":"Expreso"},
        ]).to_excel(source,index=False)
        result=PlatformService(self.database).import_mercado_libre(source,self.client_id,selected_rows={1})
        self.assertEqual(result["imported"],1)
        row=self.database.query_one("SELECT * FROM operaciones_mercado_libre WHERE cliente_id=?",(self.client_id,))
        self.assertEqual(row["id_venta"],"B");self.assertEqual(row["numero_seguimiento"],"TRK-B")

    def test_recategorization_thresholds_and_honorarium_detail(self):
        self.database.execute("DELETE FROM categorias_monotributo")
        self.database.execute("""INSERT INTO categorias_monotributo(categoria,tope_ingresos,
            tope_alquileres,tope_superficie,tope_energia,precio_unitario_maximo,vigencia_desde,estado)
            VALUES('A',1000,100,10,20,50,'2026-01-01','Vigente')""")
        vouchers=VoucherService(self.database,self.config)
        from models import Voucher
        vouchers.create("ventas",Voucher(cliente_id=self.client_id,fecha="2026-06-01",periodo_fiscal="2026-06",tipo_comprobante="Factura C",punto_venta="1",numero_comprobante="900",contraparte_nombre="Cliente",importe_original=950))
        recat=RecategorizationService(self.database,MonotributoService(self.database,vouchers,self.config))
        result=recat.calculate(self.client_id,{"superficie":11})
        self.assertEqual(result["estado"],"Cerca del límite (90%)")
        self.assertEqual(result["controles_parametros"]["superficie"]["estado"],"Superado")
        admin=AdministrativeService(self.database)
        fee=admin.create("honorarios",{"cliente_id":self.client_id,"tipo_registro":"Presupuesto","servicio":"Abono","periodo":"06/2026","importe":"1000","importe_pagado":"400","saldo_pendiente":"600","estado":"cobrado parcial","fecha_emision":"","fecha_cobro":"","fecha_vencimiento":"","medio_pago":"Transferencia","numero_comprobante":"P-1","observaciones":""})
        saved=admin.get("honorarios",fee);self.assertEqual(saved["tipo_registro"],"Presupuesto");self.assertEqual(saved["importe_pagado"],400);self.assertEqual(saved["saldo_pendiente"],600)


if __name__ == "__main__":unittest.main()
