from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from utils.formatters import money

from .common import MetricCard
from .theme import COLORS


class DashboardView(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=22)
        metrics = app.dashboard_service.general_metrics()
        # El dashboard ocupa el área disponible sin un canvas desplazable. Esto
        # evita que la vista cambie de posición al usar la rueda del mouse.
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Dashboard general", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="Panorama del estudio y actividad del período actual.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 18))

        cards = ttk.Frame(body)
        cards.pack(fill="x")
        data = (
            ("Clientes activos", str(metrics.get("clientes_activos", 0)), COLORS["blue"]),
            ("Monotributistas", str(metrics.get("monotributistas", 0)), COLORS["green"]),
            ("Ventas del mes", money(metrics.get("ventas_mes", 0)), COLORS["blue"]),
            ("Compras del mes", money(metrics.get("compras_mes", 0)), COLORS["amber"]),
            ("Alertas activas", str(metrics.get("alertas_activas", 0)), COLORS["red"]),
            ("Vencen en 7 días", str(metrics.get("vencimientos_semana", 0)), COLORS["amber"]),
        )
        for index, (title, value, color) in enumerate(data):
            cards.columnconfigure(index % 3, weight=1)
            MetricCard(cards, title, value, color).grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=6,
                pady=6,
            )

        lower = ttk.Frame(body)
        lower.pack(fill="both", expand=True, pady=(18, 0))
        lower.columnconfigure(0, weight=2)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(0, weight=1)

        alerts_box = ttk.LabelFrame(lower, text="Alertas fiscales recientes", padding=10)
        alerts_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        columns = ("cliente", "tipo", "gravedad", "importe")
        tree = ttk.Treeview(alerts_box, columns=columns, show="headings", height=10)
        for column, label, width in (
            ("cliente", "Cliente", 210),
            ("tipo", "Alerta", 190),
            ("gravedad", "Gravedad", 80),
            ("importe", "Importe", 110),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width)
        tree.pack(fill="both", expand=True)
        for alert in app.dashboard_service.recent_alerts():
            tree.insert(
                "",
                "end",
                values=(
                    alert["cliente_nombre"],
                    alert["tipo_alerta"].replace("_", " ").title(),
                    alert["gravedad"].title(),
                    money(alert["importe_relacionado"]),
                ),
            )

        next_box = tk.Frame(
            lower,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        next_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tk.Label(
            next_box,
            text="Accesos rápidos",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        ttk.Button(
            next_box,
            text="Nuevo cliente",
            style="Primary.TButton",
            command=lambda: app.show_view("clientes", action="new"),
        ).pack(fill="x", pady=4)
        ttk.Button(
            next_box,
            text="Cargar venta o compra",
            command=lambda: app.show_view("contable"),
        ).pack(fill="x", pady=4)
        ttk.Button(
            next_box,
            text="Ver monotributistas",
            command=lambda: app.show_view("monotributistas"),
        ).pack(fill="x", pady=4)
