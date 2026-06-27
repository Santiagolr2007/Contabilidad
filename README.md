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
- Once solapas visibles en la ficha monotributista, incluidas Monotributo e IIBB.
- Alertas por concentración, categoría y relación compras/ventas.
- Gestión de documentación, tareas, vencimientos y honorarios.
- Catorce reportes Excel y exportación del detalle de comprobantes.
- Selector de calendario propio, sin dependencias gráficas externas.
- Configuración editable de límites, alícuotas y categorías.

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
