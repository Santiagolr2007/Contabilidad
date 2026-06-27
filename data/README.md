# Datos locales

Esta carpeta contiene la base SQLite creada por la aplicación:
`estudio_contable.db`.

La base, sus archivos WAL y cualquier copia local están excluidos de Git porque
pueden contener datos personales, fiscales y contables. Al iniciar `main.py`, el
sistema crea o actualiza la base automáticamente. También puede inicializarse con:

```powershell
python scripts/initialize_database.py
```

No agregue bases reales al repositorio.

