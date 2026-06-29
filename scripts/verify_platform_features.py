from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import Database, initialize_database
from database.seed import seed_reference_data
from models import Client, FiscalProfile
from services import ClientService, ConfigService, PlatformService, ReportService, VoucherService


OUTPUT = ROOT / "tmp" / "platform_verify"
OUTPUT.mkdir(parents=True, exist_ok=True)
database = Database(OUTPUT / "verify.db")
initialize_database(database); seed_reference_data(database)
clients = ClientService(database)
row = database.query_one("SELECT id FROM clientes WHERE cuit_cuil='20300412298'")
client_id = int(row["id"]) if row else clients.save(Client("Cliente Plataformas", "20300412298"), FiscalProfile(regimen_principal="responsable_inscripto"), None)
platform = PlatformService(database)

mp_file = OUTPUT / "mercado_pago_ejemplo.csv"
mp_file.write_text(
    "Fecha;Descripción;ID de operación;Contraparte;Importe bruto;Importe neto;Saldo\n"
    "01/07/2026;Cobro por venta;VERIFY-MP-1;Comprador A;150000,00;145000,00;145000,00\n"
    "02/07/2026;Pago a proveedor;VERIFY-MP-2;Proveedor B;-50000,00;-50000,00;95000,00\n",
    encoding="utf-8",
)
platform.import_mercado_pago(mp_file, client_id)

ml_file = OUTPUT / "mercado_libre_ejemplo.xlsx"
pd.DataFrame([
    {"Fecha": "03/07/2026", "Tipo de operación": "Venta", "Número de comprobante": "VERIFY-ML-1", "Cliente": "Comprador A", "Producto": "Producto demostración", "Cantidad": 2, "Importe bruto": 200000, "Comisiones": 20000, "Importe neto": 180000, "ID de venta": "VERIFY-SALE-1"},
    {"Fecha": "04/07/2026", "Tipo de operación": "Nota de crédito", "Número de comprobante": "VERIFY-ML-NC-1", "Cliente": "Comprador A", "Producto": "Producto demostración", "Cantidad": 1, "Importe bruto": 30000, "Importe neto": 30000, "ID de venta": "VERIFY-SALE-2"},
]).to_excel(ml_file, index=False)
platform.import_mercado_libre(ml_file, client_id, "Ventas")

config = ConfigService(database); vouchers = VoucherService(database, config); reports = ReportService(vouchers)
reports.export_platform_report(OUTPUT / "Reporte_Mercado_Pago.xlsx", "mercado_pago", client_id)
reports.export_platform_report(OUTPUT / "Reporte_Mercado_Libre.xlsx", "mercado_libre", client_id)
reports.export_named_pdf("mercado_pago", OUTPUT / "Reporte_Mercado_Pago.pdf", client_id)
reports.export_named_pdf("mercado_libre", OUTPUT / "Reporte_Mercado_Libre.pdf", client_id)
for path in sorted(OUTPUT.glob("Reporte_*")):
    print(path)
