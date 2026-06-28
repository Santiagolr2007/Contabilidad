from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import COLORS


class MetricCard(tk.Frame):
    def __init__(self, parent, title: str, value: str, accent: str | None = None):
        super().__init__(
            parent,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        if accent:
            tk.Frame(self, bg=accent, height=4).pack(fill="x", pady=(0, 8))
        ttk.Label(
            self, text=title, style="CardTitle.TLabel", wraplength=280, justify="left"
        ).pack(anchor="w", fill="x")
        ttk.Label(
            self, text=value, style="CardValue.TLabel", wraplength=280, justify="left"
        ).pack(anchor="w", fill="x", pady=(4, 0))


class ScrollableFrame(ttk.Frame):
    """Contenedor vertical que mantiene accesible el contenido en pantallas pequeñas."""

    def __init__(self, parent, padding: int = 0):
        super().__init__(parent)
        self.canvas = tk.Canvas(
            self,
            bg=COLORS["background"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=padding)
        self.window_id = self.canvas.create_window(
            (0, 0), window=self.content, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", self._content_changed)
        self.canvas.bind("<Configure>", self._canvas_changed)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _content_changed(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_changed(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_wheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._mousewheel)

    def _unbind_wheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


def fit_window(
    window: tk.Toplevel | tk.Tk,
    desired_width: int,
    desired_height: int,
    margin: int = 60,
) -> None:
    """Ajusta y centra una ventana sin superar el área visible de la pantalla."""
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    width = max(480, min(desired_width, screen_width - margin))
    height = max(360, min(desired_height, screen_height - margin - 20))
    x = max((screen_width - width) // 2, 0)
    y = max((screen_height - height) // 2 - 15, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")


def clear_frame(frame) -> None:
    for child in frame.winfo_children():
        child.destroy()


def selected_tree_id(tree: ttk.Treeview) -> int | None:
    selection = tree.selection()
    return int(selection[0]) if selection else None


def make_tree_sortable(tree: ttk.Treeview, numeric_columns: set[str] | None = None) -> None:
    numeric_columns = numeric_columns or set()
    directions: dict[str, bool] = {}

    def sort(column: str) -> None:
        descending = directions.get(column, False)
        items = []
        for item in tree.get_children(""):
            value = tree.set(item, column)
            if column in numeric_columns:
                cleaned = value.replace("$", "").replace("%", "").replace(" ", "")
                cleaned = cleaned.replace(".", "").replace(",", ".")
                try:
                    value = float(cleaned)
                except ValueError:
                    value = 0.0
            else:
                value = value.casefold()
            items.append((value, item))
        items.sort(reverse=descending)
        for index, (_value, item) in enumerate(items):
            tree.move(item, "", index)
        directions[column] = not descending

    for column in tree["columns"]:
        label = tree.heading(column, "text")
        tree.heading(column, text=label, command=lambda col=column: sort(col))
