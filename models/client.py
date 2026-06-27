from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Client:
    nombre_razon_social: str
    cuit_cuil: str
    tipo_persona: str = "persona_humana"
    dni: str = ""
    fecha_nacimiento: str = ""
    nacionalidad: str = ""
    estado_civil: str = ""
    telefono: str = ""
    email: str = ""
    instagram: str = ""
    domicilio: str = ""
    rubro: str = ""
    fecha_alta_estudio: str = ""
    estado: str = "activo"
    observaciones: str = ""
    id: int | None = None


@dataclass(slots=True)
class FiscalProfile:
    regimen_principal: str = "sin_definir"
    condicion_iva: str = ""
    fecha_alta: str = ""
    domicilio_fiscal: str = ""
    jurisdiccion_iibb: str = ""
    regimen_iibb: str = ""
    observaciones: str = ""


@dataclass(slots=True)
class MonotributoProfile:
    categoria_actual: str = ""
    actividad_fiscal: str = ""
    denominacion: str = ""
    fecha_alta: str = ""
    fecha_baja: str = ""
    estado: str = "activo"
    observaciones_fiscales: str = ""
