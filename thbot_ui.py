"""Componentes visuais reutilizáveis do Thbot."""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

BACKGROUND = ("#f2f5f8", "#111820")
SURFACE = ("#ffffff", "#1b2530")
TEXT = ("#253548", "#e4edf5")
MUTED = ("#617286", "#a6b6c7")
BORDER = ("#dbe3ec", "#344454")
ACCENT = ("#168269", "#208e76")


def configurar_tema():
    ctk.set_default_color_theme("green")
    theme = ctk.ThemeManager.theme
    theme["CTkLabel"]["text_color"] = TEXT
    for tipo in ("CTkEntry", "CTkComboBox", "CTkTextbox"):
        theme[tipo]["fg_color"] = ("#f7f9fb", "#141e28")
        theme[tipo]["text_color"] = TEXT
        theme[tipo]["border_color"] = BORDER
    for tipo in ("CTkButton", "CTkSwitch"):
        theme[tipo]["progress_color" if tipo == "CTkSwitch" else "fg_color"] = ACCENT
    theme["CTkButton"]["hover_color"] = ("#106951", "#18745f")
    theme["CTkButton"]["text_color_disabled"] = ("#b8d2ca", "#8ca59f")
    theme["CTkComboBox"]["button_color"] = ("#e0e8ef", "#344454")
    theme["CTkComboBox"]["button_hover_color"] = ("#cdd9e4", "#44586c")
    theme["DropdownMenu"]["fg_color"] = SURFACE
    theme["DropdownMenu"]["text_color"] = TEXT
    theme["DropdownMenu"]["hover_color"] = ("#e4efe9", "#2a443e")


class Button(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("height", 34)
        kwargs.setdefault("width", 140)
        kwargs.setdefault("corner_radius", 7)
        kwargs.setdefault("font", ("Segoe UI", 13, "bold"))
        super().__init__(master, **kwargs)


class Entry(ctk.CTkEntry):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("height", 34)
        kwargs.setdefault("corner_radius", 7)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("font", ("Segoe UI", 13))
        super().__init__(master, **kwargs)


class Card(ctk.CTkFrame):
    def __init__(self, master, text, compact=False, center_content=True):
        super().__init__(master, fg_color=SURFACE, bg_color=BACKGROUND, corner_radius=12,
                         border_width=1, border_color=BORDER)
        self.pack_propagate(True)
        titulo = ctk.CTkLabel(self, text=text, anchor="w", text_color=TEXT,
                             font=("Segoe UI", 14, "bold"))
        titulo.configure(height=20)
        titulo.pack(fill="x", padx=16, pady=(8, 4) if compact else (12, 10))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x" if center_content else "both", expand=True,
                       padx=16, pady=(0, 8 if compact else 16))


class MenuButton(Button):
    def __init__(self, master, **kwargs):
        super().__init__(master, command=self._abrir, **kwargs)
        self.menu = None

    def _abrir(self):
        if self.menu is not None:
            index = 1 if ctk.get_appearance_mode() == "Dark" else 0
            self.menu.configure(background=SURFACE[index], foreground=TEXT[index],
                                activebackground=ACCENT[index], activeforeground="white")
            try:
                self.menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
            finally:
                self.menu.grab_release()


class CampaignCombo(ctk.CTkComboBox):
    def __init__(self, master, postcommand=None, **kwargs):
        self.postcommand = postcommand
        kwargs.setdefault("height", 34)
        kwargs.setdefault("corner_radius", 7)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("font", ("Segoe UI", 13))
        if 'values' in kwargs:
            kwargs['values'] = list(kwargs['values'])
        else:
            kwargs['values'] = []
        super().__init__(master, **kwargs)

    def _open_dropdown_menu(self):
        if self.postcommand:
            self.postcommand()
        super()._open_dropdown_menu()


class NumberInput(ctk.CTkFrame):
    def __init__(self, master, from_, to, textvariable, width=90):
        super().__init__(master, fg_color="transparent")
        self.variable = textvariable
        self.minimum, self.maximum = from_, to
        self.columnconfigure(1, weight=1)
        Button(self, text="−", width=28, command=lambda: self._alterar(-1)).grid(row=0, column=0)
        Entry(self, textvariable=textvariable, width=width, justify="center").grid(
            row=0, column=1, sticky="ew", padx=4
        )
        Button(self, text="+", width=28, command=lambda: self._alterar(1)).grid(row=0, column=2)

    def _alterar(self, passo):
        try:
            valor = self.variable.get()
        except (tk.TclError, ValueError):
            valor = self.minimum
        self.variable.set(max(self.minimum, min(self.maximum, valor + passo)))


class Table(ttk.Treeview):
    """Separadores por coluna, sem criar um widget para cada célula."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._lines = [tk.Frame(self, width=1, borderwidth=0) for _ in self["columns"][:-1]]
        self._pending = None
        for event in ("<Configure>", "<B1-Motion>", "<ButtonRelease-1>", "<Map>"):
            self.bind(event, self._schedule_lines, add="+")
        self.update_theme()

    def update_theme(self):
        dark = ctk.get_appearance_mode() == "Dark"
        for line in self._lines:
            line.configure(background=BORDER[int(dark)])
        self.tag_configure("ok", foreground="#6dd7ac" if dark else "#18724f")
        self.tag_configure("erro", foreground="#ff9999" if dark else "#b63440")
        self._schedule_lines()

    def _schedule_lines(self, _event=None):
        if self._pending is None:
            self._pending = self.after_idle(self._draw_lines)

    def _draw_lines(self):
        self._pending = None
        columns = self["columns"]
        total = sum(self.column(column, "width") for column in columns)
        x = -round(self.xview()[0] * total)
        # Keep the heading free so native resizing and sorting remain available.
        heading_height = 0
        while heading_height < self.winfo_height() and self.identify_region(5, heading_height) in ("nothing", "heading", "separator"):
            heading_height += 1
            if heading_height > 60:
                heading_height = 36
                break
        for column, line in zip(columns, self._lines):
            x += self.column(column, "width")
            if 0 < x < self.winfo_width() - 2:
                line.place(x=x, y=heading_height, width=1, relheight=1, height=-heading_height)
            else:
                line.place_forget()

    def xview(self, *args):
        result = super().xview(*args)
        if args:
            self._schedule_lines()
        return result

    def destroy(self):
        if self._pending is not None:
            self.after_cancel(self._pending)
        super().destroy()
