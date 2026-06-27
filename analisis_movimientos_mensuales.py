"""Interfaz para analizar comprobantes emitidos y recibidos de AFIP.

Acepta CSV/XLSX cuyos nombres comiencen con ``Mis Comprobantes Emitidos``,
``Mis Comprobantes Recibidos``, ``comprobantes_consulta_csv_emitidos`` o
``comprobantes_consulta_csv_recibidos``. Los CUIT, IDs y fechas posteriores al
prefijo no se usan para identificar el archivo."""

from __future__ import annotations
import os
import shutil
import sys
import unicodedata
from pathlib import Path
import pandas as pd


DIRECTORIO_SCRIPT = Path(__file__).resolve().parent
DIRECTORIO_DATOS = DIRECTORIO_SCRIPT / "datos_afip"
ARCHIVO_SALIDA = DIRECTORIO_SCRIPT / "Analisis de Movimientos Mensuales.xlsx"
ARCHIVO_SALIDA_EMITIDOS = DIRECTORIO_SCRIPT / "Resumen de Comprobantes Emitidos.xlsx"
ARCHIVO_SALIDA_RECIBIDOS = DIRECTORIO_SCRIPT / "Resumen de Comprobantes Recibidos.xlsx"

PREFIJOS_ARCHIVOS = {
    "emitidos": (
        "comprobantes_consulta_csv_emitidos",
        "mis comprobantes emitidos",
    ),
    "recibidos": (
        "comprobantes_consulta_csv_recibidos",
        "mis comprobantes recibidos",
    ),
}
EXTENSIONES_ADMITIDAS = (".xlsx", ".csv")
CODIGOS_NOTA_CREDITO = {3, 8, 13}
IMPORTE_FACTURA_GRANDE = 500_000
ALICUOTA_IIBB = 35 / 1000


class ErrorDatosAFIP(ValueError):
    """Error de entrada comprensible para la persona que ejecuta el script."""


def preparar_directorio_datos(directorio: Path = DIRECTORIO_DATOS) -> Path:
    """Crea y devuelve la carpeta donde deben colocarse los archivos de AFIP."""
    directorio.mkdir(parents=True, exist_ok=True)
    return directorio


def _texto_normalizado(texto: str) -> str:
    """Simplifica un nombre para compararlo sin distinguir acentos o mayúsculas."""
    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caracter)
    )
    return " ".join(sin_acentos.casefold().split())


def clasificar_archivo(ruta: Path) -> str | None:
    """Clasifica por el prefijo del nombre, sin depender de CUIT, ID o fecha."""
    if ruta.suffix.lower() not in EXTENSIONES_ADMITIDAS or ruta.name.startswith("~$"):
        return None
    nombre = _texto_normalizado(ruta.stem)
    for tipo, prefijos in PREFIJOS_ARCHIVOS.items():
        if any(nombre.startswith(prefijo) for prefijo in prefijos):
            return tipo
    return None


def listar_archivos_por_tipo(directorio: Path = DIRECTORIO_DATOS) -> dict[str, list[Path]]:
    """Lista los archivos reconocidos, separados entre emitidos y recibidos."""
    encontrados: dict[str, list[Path]] = {"emitidos": [], "recibidos": []}
    if not directorio.exists():
        return encontrados
    for ruta in sorted(directorio.iterdir(), key=lambda archivo: archivo.name.casefold()):
        tipo = clasificar_archivo(ruta)
        if tipo:
            encontrados[tipo].append(ruta)
    return encontrados


def buscar_archivo(tipo: str, directorio: Path = DIRECTORIO_DATOS) -> Path:
    """Obtiene el único archivo del tipo solicitado o explica el problema."""
    encontrados = listar_archivos_por_tipo(directorio)[tipo]

    if not encontrados:
        prefijos = " o ".join(f'"{prefijo}"' for prefijo in PREFIJOS_ARCHIVOS[tipo])
        raise ErrorDatosAFIP(
            f"No se encontró el archivo de comprobantes {tipo}. "
            f"Copialo en '{directorio}'. El nombre debe comenzar con {prefijos}."
        )
    if len(encontrados) > 1:
        raise ErrorDatosAFIP(
            f"Hay más de un archivo del tipo {tipo}: "
            f"{', '.join(archivo.name for archivo in encontrados)}. "
            f"El análisis de {tipo} no se ejecutó. Dejá solamente un archivo de ese tipo."
        )
    return encontrados[0]


def _normalizar_columnas(datos: pd.DataFrame) -> pd.DataFrame:
    datos.columns = (
        pd.Index(datos.columns)
        .map(str)
        .str.replace("\ufeff", "", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    if "Fecha de Emisión" in datos.columns and "Fecha" not in datos.columns:
        datos = datos.rename(columns={"Fecha de Emisión": "Fecha"})
    return datos


def _es_fila_encabezado(celdas: set[str]) -> bool:
    tiene_fecha = "Fecha" in celdas or "Fecha de Emisión" in celdas
    return tiene_fecha and "Imp. Total" in celdas


def _fila_encabezado_excel(ruta: Path) -> int:
    vista_previa = pd.read_excel(ruta, header=None, nrows=15)
    for numero_fila, fila in vista_previa.iterrows():
        celdas = {str(valor).strip().replace("\ufeff", "") for valor in fila.dropna()}
        if _es_fila_encabezado(celdas):
            return int(numero_fila)
    raise ErrorDatosAFIP(
        f"No se encontró una fila de encabezados con 'Fecha' e 'Imp. Total' en '{ruta.name}'."
    )


def _configuracion_csv(ruta: Path) -> tuple[str, str, int]:
    """Detecta codificación, separador y fila de encabezado de un CSV de AFIP."""
    texto = None
    codificacion_detectada = ""
    for codificacion in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            texto = ruta.read_text(encoding=codificacion)
            codificacion_detectada = codificacion
            break
        except UnicodeDecodeError:
            continue

    if texto is None:
        raise ErrorDatosAFIP(f"No se pudo determinar la codificación de '{ruta.name}'.")

    separadores = (";", ",", "\t", "|")
    for numero_fila, linea in enumerate(texto.splitlines()[:30]):
        if "Fecha" not in linea or "Imp. Total" not in linea:
            continue
        separador = max(separadores, key=linea.count)
        if linea.count(separador) == 0:
            break
        return codificacion_detectada, separador, numero_fila

    raise ErrorDatosAFIP(
        f"No se encontró una fila de encabezados con 'Fecha' e 'Imp. Total' en '{ruta.name}'."
    )


def leer_archivo_afip(ruta: Path) -> pd.DataFrame:
    """Lee un XLSX o CSV de AFIP conservando sus columnas originales."""
    extension = ruta.suffix.lower()
    if extension == ".xlsx":
        encabezado = _fila_encabezado_excel(ruta)
        datos = pd.read_excel(ruta, header=encabezado)
    elif extension == ".csv":
        codificacion, separador, encabezado = _configuracion_csv(ruta)
        datos = pd.read_csv(
            ruta,
            header=encabezado,
            sep=separador,
            encoding=codificacion,
            dtype=str,
        )
    else:
        raise ErrorDatosAFIP(
            f"El formato '{extension}' no está admitido. Usá un archivo .xlsx o .csv."
        )

    datos = _normalizar_columnas(datos)
    requeridas = {"Fecha", "Imp. Total", "Moneda", "Número Desde"}
    faltantes = requeridas.difference(datos.columns)
    if faltantes:
        raise ErrorDatosAFIP(
            f"En '{ruta.name}' faltan estas columnas requeridas: {', '.join(sorted(faltantes))}."
        )
    return datos


def _normalizar_importes(serie: pd.Series) -> pd.Series:
    """Convierte importes numéricos o textos en formato argentino a números."""
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")

    texto = serie.astype("string").str.strip()
    negativos_entre_parentesis = texto.str.match(r"^\s*\(.*\)\s*$", na=False)
    texto = texto.str.replace(r"[^0-9,\.\-]", "", regex=True)

    tiene_coma = texto.str.contains(",", regex=False, na=False)
    tiene_punto = texto.str.contains(".", regex=False, na=False)
    ambos = tiene_coma & tiene_punto
    decimal_coma = ambos & texto.str.match(r".*,[0-9]{1,2}$", na=False)
    decimal_punto = ambos & ~decimal_coma
    solo_coma = tiene_coma & ~tiene_punto
    puntos_de_miles = (
        tiene_punto
        & ~tiene_coma
        & texto.str.match(r"^-?[0-9]{1,3}(?:\.[0-9]{3})+$", na=False)
    )

    normalizado = texto.copy()
    normalizado = normalizado.mask(
        decimal_coma,
        texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
    )
    normalizado = normalizado.mask(
        decimal_punto,
        texto.str.replace(",", "", regex=False),
    )
    normalizado = normalizado.mask(
        solo_coma,
        texto.str.replace(",", ".", regex=False),
    )
    normalizado = normalizado.mask(
        puntos_de_miles,
        texto.str.replace(".", "", regex=False),
    )

    importes = pd.to_numeric(normalizado, errors="coerce")
    return importes.mask(negativos_entre_parentesis, -importes.abs())


def _normalizar_fechas(serie: pd.Series) -> pd.Series:
    """Interpreta correctamente fechas ISO y fechas argentinas DD/MM/AAAA."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return pd.to_datetime(serie, errors="coerce")

    texto = serie.astype("string").str.strip()
    es_iso = texto.str.match(r"^\d{4}-\d{2}-\d{2}(?:\s|$)", na=False)
    fechas_iso = pd.to_datetime(
        texto.where(es_iso).str.slice(0, 10),
        format="%Y-%m-%d",
        errors="coerce",
    )
    fechas_argentinas = pd.to_datetime(
        texto.where(~es_iso),
        format="mixed",
        dayfirst=True,
        errors="coerce",
    )
    return fechas_iso.fillna(fechas_argentinas)


def _columna_tipo(datos: pd.DataFrame, nombre_archivo: str) -> str:
    for candidata in ("Tipo", "Tipo de Comprobante"):
        if candidata in datos.columns:
            return candidata
    raise ErrorDatosAFIP(
        f"En '{nombre_archivo}' no existe la columna 'Tipo' ni 'Tipo de Comprobante'."
    )


def preparar_comprobantes(datos: pd.DataFrame, nombre_archivo: str) -> tuple[pd.DataFrame, str]:
    """Normaliza fechas/importes y convierte las notas de crédito en negativas."""
    preparados = datos.copy()
    columna_tipo = _columna_tipo(preparados, nombre_archivo)
    preparados["Fecha"] = _normalizar_fechas(preparados["Fecha"])
    preparados["Imp. Total"] = _normalizar_importes(preparados["Imp. Total"])

    codigo_tipo = pd.to_numeric(
        preparados[columna_tipo]
        .astype("string")
        .str.strip()
        .str.extract(r"^(\d+)(?:\.0)?(?:\s*-|$)", expand=False),
        errors="coerce",
    )
    es_nota_credito = codigo_tipo.isin(CODIGOS_NOTA_CREDITO)
    preparados["Imp. Total"] = preparados["Imp. Total"].mask(
        es_nota_credito,
        -preparados["Imp. Total"].abs(),
    )
    return preparados, columna_tipo


def resumir_por_mes(datos: pd.DataFrame, clase: str) -> pd.DataFrame:
    """Agrupa importes, cantidad de facturas y notas de crédito por mes."""
    nombres = {
        "emitidos": ("Ventas", "F_Ventas", "Nota_c_v"),
        "recibidos": ("Compras", "F_Compras", "Nota_c_c"),
    }
    importe, cantidad, notas_credito = nombres[clase]
    con_fecha = datos.dropna(subset=["Fecha"])
    if con_fecha.empty:
        raise ErrorDatosAFIP(f"Los comprobantes {clase} no contienen fechas válidas.")

    resumen = (
        con_fecha.assign(Mes=con_fecha["Fecha"].dt.to_period("M"))
        .groupby("Mes", as_index=False)
        .agg(
            **{
                importe: ("Imp. Total", "sum"),
                cantidad: ("Imp. Total", "count"),
                notas_credito: ("Imp. Total", lambda valores: valores.lt(0).sum()),
            }
        )
    )
    resumen[[cantidad, notas_credito]] = resumen[[cantidad, notas_credito]].astype(int)
    return resumen


def combinar_resumenes(emitidos: pd.DataFrame, recibidos: pd.DataFrame) -> pd.DataFrame:
    """Une ambos resúmenes y completa todos los meses intermedios."""
    movimientos = emitidos.merge(recibidos, on="Mes", how="outer")
    rango_meses = pd.period_range(
        start=movimientos["Mes"].min(),
        end=movimientos["Mes"].max(),
        freq="M",
    )
    movimientos = movimientos.set_index("Mes").reindex(rango_meses, fill_value=0)
    movimientos.index.name = "Mes"
    movimientos = movimientos.reset_index().fillna(0)

    columnas_enteras = ["F_Ventas", "Nota_c_v", "F_Compras", "Nota_c_c"]
    movimientos[columnas_enteras] = movimientos[columnas_enteras].astype(int)
    movimientos["Resultado"] = movimientos["Ventas"] - movimientos["Compras"]
    movimientos["% C/V"] = (
        movimientos["Compras"]
        .div(movimientos["Ventas"].where(movimientos["Ventas"].ne(0)))
        .mul(100)
        .fillna(0)
        .round()
        .astype(int)
    )
    movimientos["IIBB"] = movimientos["Ventas"] * ALICUOTA_IIBB

    return movimientos[
        [
            "Mes",
            "Ventas",
            "F_Ventas",
            "Nota_c_v",
            "Compras",
            "F_Compras",
            "Nota_c_c",
            "Resultado",
            "% C/V",
            "IIBB",
        ]
    ]


def _normalizar_cuit_y_denominacion(facturas: pd.DataFrame) -> pd.DataFrame:
    cuit_numerico = pd.to_numeric(facturas["CUIT"], errors="coerce").fillna(0)
    consumidor_final = cuit_numerico.eq(99)
    facturas["CUIT"] = cuit_numerico.mask(consumidor_final, 0).round().astype("Int64").astype(str)
    denominacion = facturas["Denominacion"].astype("string").str.strip()
    facturas["Denominacion"] = denominacion.mask(
        consumidor_final | denominacion.isna() | denominacion.eq(""),
        "(Consumidor Final)",
    )
    return facturas


def filtrar_facturas_grandes(
    datos: pd.DataFrame,
    columna_tipo: str,
    clase: str,
) -> pd.DataFrame:
    """Selecciona comprobantes de $500.000 o más, o emitidos en USD."""
    configuracion = {
        "emitidos": ("Denominación Receptor", "Nro. Doc. Receptor", "Venta"),
        "recibidos": ("Denominación Emisor", "Nro. Doc. Emisor", "Compra"),
    }
    columna_denominacion, columna_cuit, operacion = configuracion[clase]
    columnas_requeridas = {columna_tipo, columna_denominacion, columna_cuit}
    faltantes = columnas_requeridas.difference(datos.columns)
    if faltantes:
        raise ErrorDatosAFIP(
            f"En los comprobantes {clase} faltan estas columnas: {', '.join(sorted(faltantes))}."
        )

    moneda_usd = datos["Moneda"].astype("string").str.strip().str.upper().eq("USD")
    seleccion = datos["Fecha"].notna() & (
        datos["Imp. Total"].ge(IMPORTE_FACTURA_GRANDE) | moneda_usd
    )
    facturas = datos.loc[
        seleccion,
        [
            "Fecha",
            columna_tipo,
            "Número Desde",
            columna_denominacion,
            columna_cuit,
            "Imp. Total",
            "Moneda",
        ],
    ].copy()
    facturas.columns = [
        "Fecha",
        "Tipo",
        "Numero",
        "Denominacion",
        "CUIT",
        "Importe total",
        "Moneda",
    ]
    facturas = _normalizar_cuit_y_denominacion(facturas).reset_index(drop=True)
    facturas["Operacion"] = operacion
    return facturas


def _agregar_grafico_columnas(
    workbook,
    worksheet,
    titulo: str,
    columna_valores: int,
    color: str,
    ultima_fila: int,
    celda: str,
    nombre_hoja: str = "Resumen Mensual",
) -> None:
    grafico = workbook.add_chart({"type": "column"})
    grafico.add_series(
        {
            "name": titulo,
            "categories": [nombre_hoja, 1, 0, ultima_fila, 0],
            "values": [nombre_hoja, 1, columna_valores, ultima_fila, columna_valores],
            "fill": {"color": color},
            "border": {"color": "black"},
            "data_labels": {"value": True, "num_format": '$0.0,,"M"'},
        }
    )
    grafico.set_title({"name": titulo})
    grafico.set_y_axis({"name": "Millones de Pesos $", "num_format": '$0.0,,"M"', "major_gridlines": {"visible": True}})
    grafico.set_x_axis({"name": "Mes", "label_position": "low"})
    grafico.set_legend({"none": True})
    grafico.set_size({"width": 620, "height": 360})
    worksheet.insert_chart(celda, grafico)


def generar_excel(
    movimientos: pd.DataFrame,
    facturas: pd.DataFrame,
    ruta_salida: Path = ARCHIVO_SALIDA,
) -> None:
    """Crea el Excel final con las dos hojas y dos gráficos editables."""
    resumen_excel = movimientos.copy()
    resumen_excel["Mes"] = resumen_excel["Mes"].dt.to_timestamp()

    with pd.ExcelWriter(
        ruta_salida,
        engine="xlsxwriter",
        datetime_format="dd/mm/yyyy",
    ) as writer:
        resumen_excel.to_excel(writer, sheet_name="Resumen Mensual", index=False)
        facturas.to_excel(writer, sheet_name="Facturas Grandes", index=False)

        workbook = writer.book
        hoja_resumen = writer.sheets["Resumen Mensual"]
        hoja_facturas = writer.sheets["Facturas Grandes"]

        formato_mes = workbook.add_format({"num_format": "mmmm yyyy"})
        formato_moneda = workbook.add_format({"num_format": '$#,##0.00;[Red]-$#,##0.00'})
        formato_porcentaje = workbook.add_format({"num_format": '0"%"'})

        hoja_resumen.freeze_panes(1, 1)
        hoja_resumen.autofilter(0, 0, len(resumen_excel), len(resumen_excel.columns) - 1)
        hoja_resumen.set_column("A:A", 16, formato_mes)
        hoja_resumen.set_column("B:B", 16, formato_moneda)
        hoja_resumen.set_column("C:D", 12)
        hoja_resumen.set_column("E:E", 16, formato_moneda)
        hoja_resumen.set_column("F:G", 12)
        hoja_resumen.set_column("H:H", 16, formato_moneda)
        hoja_resumen.set_column("I:I", 10, formato_porcentaje)
        hoja_resumen.set_column("J:J", 16, formato_moneda)

        hoja_facturas.freeze_panes(1, 0)
        hoja_facturas.autofilter(0, 0, len(facturas), len(facturas.columns) - 1)
        hoja_facturas.set_column("A:A", 12)
        hoja_facturas.set_column("B:B", 28)
        hoja_facturas.set_column("C:C", 16)
        hoja_facturas.set_column("D:D", 34)
        hoja_facturas.set_column("E:E", 16)
        hoja_facturas.set_column("F:F", 18, formato_moneda)
        hoja_facturas.set_column("G:H", 12)

        if not resumen_excel.empty:
            fila_graficos = max(len(resumen_excel) + 3, 14)
            _agregar_grafico_columnas(
                workbook,
                hoja_resumen,
                "Ventas Mensuales",
                1,
                "#4169E1",
                len(resumen_excel),
                f"B{fila_graficos + 1}",
            )
            _agregar_grafico_columnas(
                workbook,
                hoja_resumen,
                "Compras Mensuales",
                4,
                "#008000",
                len(resumen_excel),
                f"K{fila_graficos + 1}",
            )


def generar_excel_individual(
    resumen: pd.DataFrame,
    facturas: pd.DataFrame,
    clase: str,
    ruta_salida: Path,
) -> None:
    """Crea el Excel independiente de emitidos o recibidos con su gráfico."""
    configuracion = {
        "emitidos": ("Resumen Emitidos", "Ventas Mensuales", 1, "#4169E1"),
        "recibidos": ("Resumen Recibidos", "Compras Mensuales", 1, "#008000"),
    }
    nombre_hoja, titulo_grafico, columna_valores, color = configuracion[clase]
    resumen_excel = resumen.copy()
    resumen_excel["Mes"] = resumen_excel["Mes"].dt.to_timestamp()

    with pd.ExcelWriter(
        ruta_salida,
        engine="xlsxwriter",
        datetime_format="dd/mm/yyyy",
    ) as writer:
        resumen_excel.to_excel(writer, sheet_name=nombre_hoja, index=False)
        facturas.to_excel(writer, sheet_name="Facturas Grandes", index=False)

        workbook = writer.book
        hoja_resumen = writer.sheets[nombre_hoja]
        hoja_facturas = writer.sheets["Facturas Grandes"]
        formato_mes = workbook.add_format({"num_format": "mmmm yyyy"})
        formato_moneda = workbook.add_format(
            {"num_format": '$#,##0.00;[Red]-$#,##0.00'}
        )

        hoja_resumen.freeze_panes(1, 1)
        hoja_resumen.autofilter(
            0, 0, len(resumen_excel), len(resumen_excel.columns) - 1
        )
        hoja_resumen.set_column("A:A", 16, formato_mes)
        hoja_resumen.set_column("B:B", 18, formato_moneda)
        hoja_resumen.set_column("C:D", 14)

        hoja_facturas.freeze_panes(1, 0)
        hoja_facturas.autofilter(0, 0, len(facturas), len(facturas.columns) - 1)
        hoja_facturas.set_column("A:A", 12)
        hoja_facturas.set_column("B:B", 28)
        hoja_facturas.set_column("C:C", 16)
        hoja_facturas.set_column("D:D", 34)
        hoja_facturas.set_column("E:E", 16)
        hoja_facturas.set_column("F:F", 18, formato_moneda)
        hoja_facturas.set_column("G:H", 12)

        if not resumen_excel.empty:
            fila_grafico = max(len(resumen_excel) + 3, 14)
            _agregar_grafico_columnas(
                workbook,
                hoja_resumen,
                titulo_grafico,
                columna_valores,
                color,
                len(resumen_excel),
                f"B{fila_grafico + 1}",
                nombre_hoja,
            )


def _imprimir_resultados(
    resumen_emitidos: pd.DataFrame,
    resumen_recibidos: pd.DataFrame,
    movimientos: pd.DataFrame,
    facturas: pd.DataFrame,
) -> None:
    total_emitidos = resumen_emitidos["Ventas"].sum()
    total_recibidos = resumen_recibidos["Compras"].sum()
    meses_con_ventas = int(movimientos["F_Ventas"].gt(0).sum())
    meses_con_compras = int(movimientos["F_Compras"].gt(0).sum())
    promedio_ventas = total_emitidos / meses_con_ventas if meses_con_ventas else 0
    promedio_compras = total_recibidos / meses_con_compras if meses_con_compras else 0

    print("\nSuma de FC EMITIDAS")
    print(resumen_emitidos.to_string(index=False))
    print(f"\nEl resultado de la suma de todos los meses es: ${total_emitidos:.2f}")
    print("\nSuma de FC RECIBIDAS")
    print(resumen_recibidos.to_string(index=False))
    print(f"\nEl resultado de la suma de todos los meses es: ${total_recibidos:.2f}")
    print("\nRESUMEN MENSUAL")
    print(movimientos.to_string(index=False))
    print(f"\nSuma Ventas: ${total_emitidos:.2f}")
    print(f"Promedio Ventas: ${promedio_ventas:.2f}")
    print(f"Suma Compras: ${total_recibidos:.2f}")
    print(f"Promedio Compras: ${promedio_compras:.2f}")
    print("\nFacturas mayores o iguales a $500.000 o facturas en USD")
    print(facturas.to_string(index=False) if not facturas.empty else "No se encontraron facturas.")


def _procesar_archivo(
    clase: str,
    directorio: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Path]:
    """Lee un único archivo y devuelve datos, resumen, facturas y ruta fuente."""
    ruta = buscar_archivo(clase, directorio)
    datos, columna_tipo = preparar_comprobantes(leer_archivo_afip(ruta), ruta.name)
    resumen = resumir_por_mes(datos, clase)
    facturas = filtrar_facturas_grandes(datos, columna_tipo, clase)
    return datos, resumen, facturas, ruta


def ejecutar_resumen_individual(
    clase: str,
    directorio: Path = DIRECTORIO_DATOS,
    ruta_salida: Path | None = None,
) -> Path:
    """Genera solo emitidos o solo recibidos, sin exigir el otro archivo."""
    if clase not in ("emitidos", "recibidos"):
        raise ValueError("La clase debe ser 'emitidos' o 'recibidos'.")
    preparar_directorio_datos(directorio)
    _, resumen, facturas, _ = _procesar_archivo(clase, directorio)
    if ruta_salida is None:
        ruta_salida = (
            ARCHIVO_SALIDA_EMITIDOS if clase == "emitidos" else ARCHIVO_SALIDA_RECIBIDOS
        )
    generar_excel_individual(resumen, facturas, clase, ruta_salida)
    return ruta_salida


def ejecutar_analisis(
    directorio: Path = DIRECTORIO_DATOS,
    ruta_salida: Path = ARCHIVO_SALIDA,
) -> Path:
    """Genera el movimiento conjunto; requiere exactamente un archivo de cada tipo."""
    preparar_directorio_datos(directorio)
    emitidos, resumen_emitidos, facturas_emitidos, _ = _procesar_archivo(
        "emitidos", directorio
    )
    recibidos, resumen_recibidos, facturas_recibidos, _ = _procesar_archivo(
        "recibidos", directorio
    )
    del emitidos, recibidos

    movimientos = combinar_resumenes(resumen_emitidos, resumen_recibidos)
    facturas = pd.concat(
        [facturas_emitidos, facturas_recibidos],
        ignore_index=True,
    )
    generar_excel(movimientos, facturas, ruta_salida)
    _imprimir_resultados(resumen_emitidos, resumen_recibidos, movimientos, facturas)
    return ruta_salida


def _abrir_ruta(ruta: Path) -> None:
    """Abre un archivo o carpeta con la aplicación predeterminada del sistema."""
    if not ruta.exists():
        raise ErrorDatosAFIP(f"No existe: {ruta}")
    if sys.platform == "win32":
        os.startfile(ruta)  # type: ignore[attr-defined]
        return
    raise ErrorDatosAFIP("La apertura automática está disponible en Windows.")


def iniciar_interfaz() -> None:
    """Abre la interfaz gráfica para cargar archivos y generar los Excel."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    directorio = preparar_directorio_datos()

    class AplicacionAFIP:
        def __init__(self, raiz: tk.Tk) -> None:
            self.raiz = raiz
            self.ultimo_resultado: Path | None = None
            self.abrir_al_finalizar = tk.BooleanVar(value=True)

            raiz.title("Análisis de comprobantes AFIP")
            raiz.geometry("980x690")
            raiz.minsize(820, 600)

            estilo = ttk.Style(raiz)
            estilo.configure("Titulo.TLabel", font=("Segoe UI", 18, "bold"))
            estilo.configure("Subtitulo.TLabel", font=("Segoe UI", 10))
            estilo.configure("Accion.TButton", font=("Segoe UI", 10, "bold"), padding=10)

            contenedor = ttk.Frame(raiz, padding=18)
            contenedor.pack(fill="both", expand=True)

            ttk.Label(
                contenedor,
                text="Análisis de comprobantes AFIP",
                style="Titulo.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                contenedor,
                text=(
                    "Cargá archivos CSV o XLSX. Los CUIT, IDs y fechas del nombre "
                    "pueden variar: se reconoce el prefijo."
                ),
                style="Subtitulo.TLabel",
            ).pack(anchor="w", pady=(2, 14))

            barra_archivos = ttk.Frame(contenedor)
            barra_archivos.pack(fill="x", pady=(0, 8))
            ttk.Button(
                barra_archivos,
                text="Agregar archivos…",
                command=self.agregar_archivos,
            ).pack(side="left")
            ttk.Button(
                barra_archivos,
                text="Abrir carpeta datos_afip",
                command=self.abrir_carpeta,
            ).pack(side="left", padx=8)
            ttk.Button(
                barra_archivos,
                text="Actualizar lista",
                command=self.actualizar_lista,
            ).pack(side="left")

            self.tabla = ttk.Treeview(
                contenedor,
                columns=("tipo", "formato", "estado"),
                show="tree headings",
                height=9,
            )
            self.tabla.heading("#0", text="Archivo")
            self.tabla.heading("tipo", text="Tipo detectado")
            self.tabla.heading("formato", text="Formato")
            self.tabla.heading("estado", text="Estado")
            self.tabla.column("#0", width=520)
            self.tabla.column("tipo", width=110, anchor="center")
            self.tabla.column("formato", width=80, anchor="center")
            self.tabla.column("estado", width=150, anchor="center")
            self.tabla.pack(fill="both", expand=True)

            ttk.Separator(contenedor).pack(fill="x", pady=15)
            ttk.Label(
                contenedor,
                text="Generar resultados",
                font=("Segoe UI", 12, "bold"),
            ).pack(anchor="w", pady=(0, 8))

            acciones = ttk.Frame(contenedor)
            acciones.pack(fill="x")
            ttk.Button(
                acciones,
                text="Resumen de emitidos",
                style="Accion.TButton",
                command=lambda: self.generar_individual("emitidos"),
            ).pack(side="left", fill="x", expand=True)
            ttk.Button(
                acciones,
                text="Resumen de recibidos",
                style="Accion.TButton",
                command=lambda: self.generar_individual("recibidos"),
            ).pack(side="left", fill="x", expand=True, padx=10)
            ttk.Button(
                acciones,
                text="Movimiento total de ambos",
                style="Accion.TButton",
                command=self.generar_total,
            ).pack(side="left", fill="x", expand=True)

            opciones = ttk.Frame(contenedor)
            opciones.pack(fill="x", pady=12)
            ttk.Checkbutton(
                opciones,
                text="Abrir el Excel al finalizar",
                variable=self.abrir_al_finalizar,
            ).pack(side="left")
            ttk.Button(
                opciones,
                text="Abrir último resultado",
                command=self.abrir_ultimo_resultado,
            ).pack(side="right")

            self.estado = tk.StringVar(value="Listo.")
            ttk.Label(
                contenedor,
                textvariable=self.estado,
                relief="sunken",
                padding=8,
                anchor="w",
            ).pack(fill="x", side="bottom")
            self.actualizar_lista()

        def actualizar_lista(self) -> None:
            for item in self.tabla.get_children():
                self.tabla.delete(item)
            reconocidos = listar_archivos_por_tipo(directorio)
            cantidades = {tipo: len(rutas) for tipo, rutas in reconocidos.items()}

            for ruta in sorted(directorio.iterdir(), key=lambda item: item.name.casefold()):
                if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES_ADMITIDAS:
                    continue
                tipo = clasificar_archivo(ruta)
                if tipo is None:
                    tipo_texto = "No reconocido"
                    estado = "Nombre no admitido"
                else:
                    tipo_texto = tipo.capitalize()
                    estado = "Listo" if cantidades[tipo] == 1 else "Duplicado"
                self.tabla.insert(
                    "",
                    "end",
                    text=ruta.name,
                    values=(tipo_texto, ruta.suffix.upper().lstrip("."), estado),
                )

            resumen_estado = (
                f"Emitidos: {cantidades['emitidos']} archivo(s) · "
                f"Recibidos: {cantidades['recibidos']} archivo(s)"
            )
            self.estado.set(resumen_estado)

        def agregar_archivos(self) -> None:
            seleccionados = filedialog.askopenfilenames(
                title="Seleccionar comprobantes AFIP",
                filetypes=(
                    ("Archivos admitidos", "*.xlsx *.csv"),
                    ("Excel", "*.xlsx"),
                    ("CSV", "*.csv"),
                ),
            )
            if not seleccionados:
                return

            errores: list[str] = []
            copiados = 0
            for nombre in seleccionados:
                origen = Path(nombre)
                if clasificar_archivo(origen) is None:
                    errores.append(f"Nombre no reconocido: {origen.name}")
                    continue
                destino = directorio / origen.name
                if origen.resolve() == destino.resolve():
                    continue
                if destino.exists() and not messagebox.askyesno(
                    "Reemplazar archivo",
                    f"'{destino.name}' ya existe en datos_afip. ¿Querés reemplazarlo?",
                ):
                    continue
                shutil.copy2(origen, destino)
                copiados += 1

            self.actualizar_lista()
            if errores:
                messagebox.showwarning("Algunos archivos no se cargaron", "\n".join(errores))
            elif copiados:
                self.estado.set(f"Se cargaron {copiados} archivo(s) en {directorio}.")

        def abrir_carpeta(self) -> None:
            try:
                _abrir_ruta(directorio)
            except (ErrorDatosAFIP, OSError) as error:
                messagebox.showerror("No se pudo abrir la carpeta", str(error))

        def _finalizar_resultado(self, salida: Path) -> None:
            self.ultimo_resultado = salida
            self.estado.set(f"Excel creado: {salida.name}")
            messagebox.showinfo("Análisis terminado", f"Se creó:\n{salida}")
            if self.abrir_al_finalizar.get():
                try:
                    _abrir_ruta(salida)
                except (ErrorDatosAFIP, OSError) as error:
                    messagebox.showwarning(
                        "Excel creado, pero no se pudo abrir",
                        str(error),
                    )

        def generar_individual(self, clase: str) -> None:
            try:
                salida = ejecutar_resumen_individual(clase, directorio)
                self._finalizar_resultado(salida)
            except (ErrorDatosAFIP, ImportError, OSError, ValueError) as error:
                self.estado.set(f"No se ejecutó el análisis de {clase}.")
                messagebox.showerror(f"Error en {clase}", str(error))

        def generar_total(self) -> None:
            try:
                salida = ejecutar_analisis(directorio)
                self._finalizar_resultado(salida)
            except (ErrorDatosAFIP, ImportError, OSError, ValueError) as error:
                self.estado.set("No se ejecutó el movimiento total.")
                messagebox.showerror("Error en movimiento total", str(error))

        def abrir_ultimo_resultado(self) -> None:
            if self.ultimo_resultado is None:
                messagebox.showinfo(
                    "Sin resultados",
                    "Todavía no se generó un archivo Excel en esta sesión.",
                )
                return
            try:
                _abrir_ruta(self.ultimo_resultado)
            except (ErrorDatosAFIP, OSError) as error:
                messagebox.showerror("No se pudo abrir el resultado", str(error))

    raiz = tk.Tk()
    AplicacionAFIP(raiz)
    raiz.mainloop()


def main() -> int:
    try:
        iniciar_interfaz()
    except (ErrorDatosAFIP, ImportError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
