from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Voucher:
    cliente_id: int
    fecha: str
    periodo_fiscal: str
    tipo_comprobante: str
    punto_venta: str
    numero_comprobante: str
    contraparte_nombre: str
    numero_hasta: str = ""
    codigo_autorizacion: str = ""
    tipo_doc_contraparte: str = ""
    contraparte_documento: str = ""
    tipo_doc_receptor: str = ""
    nro_doc_receptor: str = ""
    concepto: str = ""
    moneda: str = "ARS"
    tipo_cambio: float = 1.0
    importe_original: float = 0.0
    estado: str = "normal"
    origen: str = "manual"
    observaciones: str = ""
    nombre_archivo_origen: str = ""
    fecha_importacion: str = ""
    tipo_archivo: str = ""
    usuario_importacion: str = ""
    id_importacion: int | None = None
    id: int | None = None
