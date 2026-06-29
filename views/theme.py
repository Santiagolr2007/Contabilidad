from __future__ import annotations

from tkinter import ttk


COLORS = {
    "navy": "#17324D",
    "navy_light": "#244A6B",
    "blue": "#2E75B6",
    "blue_soft": "#EAF3FA",
    "background": "#F4F6F8",
    "surface": "#FFFFFF",
    "text": "#243447",
    "muted": "#697A8C",
    "green": "#2E8B57",
    "amber": "#D58A00",
    "red": "#C0392B",
    "border": "#DCE3E8",
}


def configure_theme(root) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.configure(bg=COLORS["background"])
    style.configure("TFrame", background=COLORS["background"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure(
        "Title.TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=("Segoe UI", 22, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=COLORS["background"],
        foreground=COLORS["muted"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "CardTitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "CardValue.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        font=("Segoe UI", 16, "bold"),
    )
    style.configure("TButton", font=("Segoe UI", 9), padding=(10, 6))
    style.configure(
        "Primary.TButton",
        background=COLORS["blue"],
        foreground="white",
        font=("Segoe UI", 9, "bold"),
    )
    style.map("Primary.TButton", background=[("active", COLORS["navy_light"])])
    style.configure("Treeview", rowheight=28, font=("Segoe UI", 9), padding=(5, 1))
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), anchor="center", padding=(6, 5))
    style.configure("TNotebook.Tab", font=("Segoe UI", 9), padding=(7, 6))
