from __future__ import annotations

from tkinter import ttk


class PlaceholderView(ttk.Frame):
    def __init__(self, parent, _app, title: str, stage: str = "Etapa 2") -> None:
        super().__init__(parent, padding=22)
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text=f"Módulo preparado para {stage}. La estructura de base de datos ya está creada.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 20))
        box = ttk.LabelFrame(self, text="Alcance planificado", padding=18)
        box.pack(fill="x")
        ttk.Label(
            box,
            text=(
                "Esta primera entrega prioriza clientes, ficha fiscal, monotributistas, "
                "ventas, compras y métricas. Este módulo se habilitará en la etapa indicada."
            ),
            wraplength=700,
            justify="left",
        ).pack(anchor="w")
