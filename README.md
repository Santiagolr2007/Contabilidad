# Sistema de gestión jurídico-contable

Aplicación de escritorio modular desarrollada con Python, Tkinter/ttk y SQLite.
Centraliza clientes, monotributo, Ingresos Brutos, comprobantes, alertas,
documentación, tareas, vencimientos, honorarios e informes.

## Instalación y ejecución

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

La base local se crea y migra automáticamente en
`data/estudio_contable.db`. Las migraciones conservan los datos cargados con
versiones anteriores.

## Funciones implementadas

- Alta, edición, búsqueda y baja lógica de clientes.
- Datos personales completos, fecha de alta en el estudio y regímenes activos.
- Ficha de monotributo con actividad fiscal, denominación, categoría y fechas.
- Perfil independiente de Ingresos Brutos y cálculo mensual.
- Ventas y compras manuales con facturas, notas de débito y crédito.
- Comprobantes anulados visibles con importe fiscal cero.
- Conversión USD y alertas por moneda o monto significativo.
- Importación ARCA de emitidos y recibidos desde XLSX o CSV.
- Detección automática de encabezados en primera o segunda fila.
- Normalización de fechas, importes argentinos, códigos y columnas variantes.
- Pantalla de mapeo manual cuando una columna obligatoria no se reconoce.
- Trazabilidad por lote: archivo, fecha, formato, usuario e ID de importación.
- Borrado confirmado por ventas/compras, período, archivo o cliente, sin borrar la ficha.
- Ventas/compras del mes, año calendario y últimos doce meses.
- Tablas ordenables ascendente/descendente y análisis de significativos/moneda extranjera.
- Rankings de clientes y proveedores.
- Recategorización de monotributo con parámetros adicionales.
- Trece solapas en dos filas en la ficha monotributista, incluidas Monotributo e IIBB,
  con desplazamiento vertical y horizontal.
- Alertas por concentración, categoría y relación compras/ventas.
- Gestión consolidada de documentación, tareas, vencimientos y honorarios de todos los clientes.
- Tareas con filtros por cliente, área, tipo, estado, prioridad, fecha y vencimiento;
  acciones de estado, colores y acceso directo al legajo.
- Vencimientos con fechas de cumplimiento y pago editables, acciones de estado,
  filtros completos y colores de situación.
- Catorce reportes Excel y exportación del detalle de comprobantes.
- Selector de calendario propio, sin dependencias gráficas externas.
- Configuración editable de límites, alícuotas y categorías.
- Índice Maestro de Clientes con filtros, casillas de selección y estados automáticos.
- Legajo integral por cliente organizado por áreas: resumen, datos,
  servicio/presupuesto, pagos, obligaciones, relevamiento, documentación y
  accesos, organismos, bancos, riesgos, tareas y vencimientos.
- Cuenta corriente de honorarios/pagos al estudio con saldo automático, cobro
  total o parcial, totales, filtros, estados coloreados y alertas por deuda.
- Auditoría técnica interna sin mostrar historial, responsables internos ni
  fechas de última modificación al usuario.
- Exportación parcial o completa a Excel/PDF y exportación masiva a ZIP.
- Exportación del Índice Maestro visible a Excel o PDF.
- Dashboard interactivo con categorías fiscales, alertas activas y vencimientos
  a 7, 15 y 30 días; cada detalle abre el legajo del cliente.
- Vencimientos con tipo múltiple, organismo, filtros y vista
  agrupada por cliente.
- Honorarios con selección de cliente por nombre/CUIT, filtros, agrupación y
  control de duplicados.
- Ingresos Brutos multijurisdicción con las 24 jurisdicciones argentinas,
  porcentajes por jurisdicción y advertencia cuando el total no llega a 100 %.
- Mercado Pago: importación XLSX/CSV, clasificación automática, resumen,
  significativos, rankings y subsolapas por movimiento.
- Mercado Libre: ventas, compras, notas de crédito, devoluciones, productos,
  contrapartes, operaciones significativas y neteo mensual.
- Borrado controlado de importaciones de plataformas y trazabilidad técnica interna.
- Reportes Mercado Pago y Mercado Libre en Excel, PDF e impresión.
- Importación robusta de vencimientos ARCA (`.xls`, `.xlsx` o `.csv`) con detección
  de encabezados, vinculación por CUIT, vista previa, control de duplicados e historial.
- Importación desde PDF de Sistema Registral ARCA para precargar clientes y su legajo.
- Importación y versionado de las categorías A a K de Monotributo desde PDF ARCA,
  con cálculo del pago por actividad, SIPA, obra social y adherentes.
- Reportes matriciales anuales de compras por proveedor y ventas por comprador,
  combinando comprobantes ARCA y operaciones de Mercado Libre.
- Pantalla individual de Responsables Inscriptos con selector por nombre/CUIT,
  14 solapas en dos filas y tarjetas coloreadas para ventas, compras, IVA,
  saldo técnico, vencimientos, pagos, documentación, riesgos y alertas.
- Consolidación de ARCA, Mercado Libre, Mercado Pago e Ingresos Brutos por
  responsable, con detalle desplazable y exportación a Excel, PDF e impresión.
- Reporte General de Tareas exportable a Excel/PDF e imprimible.
- Mercado Pago y Mercado Libre con barras de acciones separadas, menús en dos
  filas, vista previa, confirmación independiente y scroll horizontal/vertical.

Todas las pantallas y exportaciones muestran fechas como `DD/MM/AAAA`, períodos
como `MM/AAAA` e importes con formato argentino (`1.250.000,00`). Internamente,
SQLite conserva fechas y períodos normalizados para poder ordenarlos correctamente.

## Legajo integral de clientes

Desde **Clientes**, use **Abrir legajo integral**. Cada solapa permite agregar,
modificar, eliminar, filtrar y exportar sus registros. Los campos con opciones
usan listas desplegables y muestran sus alternativas en azul. Los datos técnicos
de auditoría se conservan internamente y no se muestran en la interfaz.

Para una exportación masiva, marque clientes con la casilla de la primera
columna y pulse **Exportar clientes seleccionados**. Si no marca ninguno, se
usan la selección normal de la tabla o todos los clientes que quedaron visibles
después de aplicar los filtros.

## Importar comprobantes ARCA

1. Abrir **Módulo contable** y elegir Ventas o Compras.
2. Seleccionar el cliente interno del estudio.
3. Presionar **Importar ARCA** y elegir un `.xlsx` o `.csv`.
4. Confirmar el mapeo solamente si alguna columna no fue reconocida.

El importador acepta, entre otras, las variantes `Fecha` / `Fecha de Emisión`,
`Tipo` / `Tipo de Comprobante`, archivos CSV separados por punto y coma e
importes como `1.250.000,50`. Las notas de crédito se vuelven negativas incluso
si el archivo trae el importe positivo.

## Configuración normativa

El monto significativo comienza en $500.000 pero es editable. Las categorías
de monotributo incluidas son exclusivamente demostrativas; deben reemplazarse
por los valores normativos vigentes desde **Configuración** antes del uso real.

## Estructura

```text
main.py
database/      conexión, esquema, migraciones y datos iniciales
models/        estructuras de clientes y comprobantes
services/      reglas contables, importación, alertas y reportes
views/         interfaz gráfica modular
utils/         validaciones y formatos
data/          base SQLite
scripts/       inicialización y verificaciones técnicas
tests/         pruebas automáticas
```

El analizador AFIP anterior permanece disponible en
`analisis_movimientos_mensuales.py`.

## Pruebas

```powershell
python -m unittest -v
python scripts/validate_real_imports.py
```

La segunda orden usa los archivos presentes en `datos_afip` y una base temporal;
no modifica la base de trabajo.

## Uso con Git

El repositorio versiona el código, la documentación y las pruebas. Por seguridad,
no incluye la base SQLite local, los comprobantes AFIP/ARCA, el entorno virtual,
las cachés ni los Excel generados.

Después de clonar el repositorio en Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\initialize_database.py
.\.venv\Scripts\python.exe main.py
```

Si `python` no está disponible como comando, use `py` en la primera línea. Las
carpetas `data` y `datos_afip` incluyen instrucciones, pero su contenido local y
sensible permanece fuera del control de versiones.
