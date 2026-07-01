from __future__ import annotations

from tkinter import ttk


COLORS = {
    "navy": "#17324D",
    "navy_light": "#244A6B",
    "blue": "#2E75B6",
    "blue_soft": "#EAF3FA",
    "background": "#F3F5F7",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "text": "#243447",
    "muted": "#697A8C",
    "green": "#2E8B57",
    "amber": "#D58A00",
    "red": "#C0392B",
    "border": "#D7E0E7",
    "border_strong": "#B9C8D4",
}


def configure_theme(root) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.configure(bg=COLORS["background"])
    root.option_add("*Font", "{Segoe UI} 9")
    root.option_add("*selectBackground", COLORS["blue"])
    root.option_add("*selectForeground", "white")
    style.configure("TFrame", background=COLORS["background"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("TabBar.TFrame", background=COLORS["surface_alt"])
    style.configure(
        "TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "Title.TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=("Segoe UI", 21, "bold"),
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
    style.configure(
        "TLabelframe",
        background=COLORS["background"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=COLORS["background"],
        foreground=COLORS["navy"],
        font=("Segoe UI", 9, "bold"),
    )
    style.configure(
        "TEntry",
        fieldbackground=COLORS["surface"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        insertcolor=COLORS["text"],
        padding=(7, 5),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", COLORS["blue"])],
        lightcolor=[("focus", COLORS["blue"])],
        darkcolor=[("focus", COLORS["blue"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=COLORS["surface"],
        background=COLORS["surface"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        padding=(7, 5),
        arrowsize=13,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", COLORS["surface"]), ("focus", COLORS["surface"])],
        foreground=[("readonly", COLORS["text"])],
        bordercolor=[("focus", COLORS["blue"])],
    )
    style.configure(
        "TButton",
        background=COLORS["surface"],
        foreground=COLORS["navy"],
        bordercolor=COLORS["border_strong"],
        lightcolor=COLORS["surface"],
        darkcolor=COLORS["border_strong"],
        font=("Segoe UI", 9),
        padding=(11, 6),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", COLORS["blue_soft"]), ("pressed", "#DDEBF5")],
        foreground=[("disabled", "#9AA8B4"), ("active", COLORS["navy"])],
        bordercolor=[("focus", COLORS["blue"]), ("active", COLORS["blue"])],
    )
    style.configure(
        "Primary.TButton",
        background=COLORS["blue"],
        foreground="white",
        bordercolor=COLORS["blue"],
        lightcolor=COLORS["blue"],
        darkcolor=COLORS["blue"],
        font=("Segoe UI", 9, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLORS["navy_light"]), ("pressed", COLORS["navy"])],
        foreground=[("active", "white"), ("pressed", "white"), ("disabled", "#E5EDF3")],
        bordercolor=[("active", COLORS["navy_light"]), ("focus", COLORS["navy"])],
    )
    style.configure(
        "TabNav.TButton",
        background=COLORS["surface_alt"],
        foreground=COLORS["navy"],
        bordercolor=COLORS["border"],
        font=("Segoe UI", 9),
        padding=(9, 7),
    )
    style.map("TabNav.TButton", background=[("active", COLORS["blue_soft"])])
    style.configure(
        "SelectedTabNav.TButton",
        background=COLORS["navy_light"],
        foreground="white",
        bordercolor=COLORS["navy_light"],
        font=("Segoe UI", 9, "bold"),
        padding=(9, 7),
    )
    style.map(
        "SelectedTabNav.TButton",
        background=[("active", COLORS["blue"]), ("pressed", COLORS["navy"])],
        foreground=[("active", "white"), ("pressed", "white")],
    )
    style.configure(
        "Treeview",
        background=COLORS["surface"],
        fieldbackground=COLORS["surface"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        rowheight=30,
        font=("Segoe UI", 9),
        padding=(5, 1),
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["blue"])],
        foreground=[("selected", "white")],
    )
    style.configure(
        "Treeview.Heading",
        background="#E5EDF4",
        foreground=COLORS["navy"],
        bordercolor=COLORS["border_strong"],
        lightcolor=COLORS["border_strong"],
        darkcolor=COLORS["border_strong"],
        font=("Segoe UI", 9, "bold"),
        anchor="center",
        padding=(7, 7),
        relief="flat",
    )
    style.map("Treeview.Heading", background=[("active", "#D8E5EF")])
    style.configure("TNotebook", background=COLORS["background"], borderwidth=0, tabmargins=(0, 3, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background="#E4EAF0",
        foreground=COLORS["muted"],
        bordercolor=COLORS["border"],
        font=("Segoe UI", 9),
        padding=(12, 8),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLORS["surface"]), ("active", COLORS["blue_soft"])],
        foreground=[("selected", COLORS["navy"]), ("active", COLORS["navy"])],
        font=[("selected", ("Segoe UI", 9, "bold"))],
        expand=[("selected", (0, 2, 0, 0))],
    )
    style.configure(
        "Vertical.TScrollbar",
        background="#C8D4DE",
        troughcolor=COLORS["background"],
        bordercolor=COLORS["background"],
        arrowcolor=COLORS["navy_light"],
        width=13,
    )
    style.configure(
        "Horizontal.TScrollbar",
        background="#C8D4DE",
        troughcolor=COLORS["background"],
        bordercolor=COLORS["background"],
        arrowcolor=COLORS["navy_light"],
        width=13,
    )
