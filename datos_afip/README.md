# Comprobantes AFIP/ARCA

Coloque aquí los archivos `.xlsx` o `.csv` que utilizará el analizador y las
pruebas con datos reales. Los comprobantes se excluyen de Git porque pueden
contener CUIT, nombres, importes y otra información fiscal sensible.

La aplicación de escritorio también permite elegir los archivos desde la
interfaz. El script `scripts/validate_real_imports.py` utiliza los documentos que
encuentre en esta carpeta y no modifica la base principal.

