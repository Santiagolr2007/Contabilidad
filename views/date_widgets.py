from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk


class DateEntry(ttk.Frame):
    """Campo de fecha con calendario, sin dependencias externas."""

    def __init__(self, parent, variable: tk.StringVar, width: int = 20) -> None:
        super().__init__(parent)
        self.variable = variable
        ttk.Entry(self, textvariable=variable, width=width).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(self, text="📅", width=3, command=self.open_calendar).pack(
            side="left", padx=(4, 0)
        )

    def open_calendar(self) -> None:
        initial = date.today()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                initial = datetime.strptime(self.variable.get(), fmt).date()
                break
            except ValueError:
                continue
        CalendarDialog(self, initial, self._set_date)

    def _set_date(self, selected: date) -> None:
        self.variable.set(selected.strftime("%d/%m/%Y"))


class CalendarDialog(tk.Toplevel):
    def __init__(self, parent, initial: date, callback) -> None:
        super().__init__(parent)
        self.title("Seleccionar fecha")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.year = initial.year
        self.month = initial.month
        self.callback = callback
        self.header = ttk.Frame(self, padding=8)
        self.header.pack(fill="x")
        ttk.Button(self.header, text="‹", width=3, command=lambda: self.move(-1)).pack(
            side="left"
        )
        self.title_label = ttk.Label(self.header, anchor="center", font=("Segoe UI", 10, "bold"))
        self.title_label.pack(side="left", fill="x", expand=True)
        ttk.Button(self.header, text="›", width=3, command=lambda: self.move(1)).pack(
            side="right"
        )
        self.days = ttk.Frame(self, padding=(8, 0, 8, 8))
        self.days.pack()
        self.render()

    def move(self, delta: int) -> None:
        month = self.year * 12 + self.month - 1 + delta
        self.year, zero_based = divmod(month, 12)
        self.month = zero_based + 1
        self.render()

    def render(self) -> None:
        for child in self.days.winfo_children():
            child.destroy()
        month_names = (
            "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        )
        self.title_label.configure(text=f"{month_names[self.month]} {self.year}")
        for column, name in enumerate(("Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do")):
            ttk.Label(self.days, text=name, anchor="center", width=4).grid(
                row=0, column=column, pady=3
            )
        for row_index, week in enumerate(calendar.monthcalendar(self.year, self.month), 1):
            for column, day in enumerate(week):
                if day:
                    ttk.Button(
                        self.days,
                        text=str(day),
                        width=4,
                        command=lambda selected=day: self.select(selected),
                    ).grid(row=row_index, column=column, padx=1, pady=1)

    def select(self, day: int) -> None:
        self.callback(date(self.year, self.month, day))
        self.destroy()
