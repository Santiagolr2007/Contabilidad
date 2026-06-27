from __future__ import annotations

from tkinter import ttk


class RegimeView(ttk.Frame):
    def __init__(self, parent, app, title: str, regime: str) -> None:
        super().__init__(parent,padding=22); self.app=app
        ttk.Label(self,text=title,style="Title.TLabel").pack(anchor="w")
        ttk.Label(self,text="Clientes activos asignados a este régimen fiscal.",style="Subtitle.TLabel").pack(anchor="w",pady=(2,12))
        toolbar=ttk.Frame(self);toolbar.pack(fill="x",pady=(0,8));ttk.Button(toolbar,text="+ Registrar cliente",style="Primary.TButton",command=lambda:app.show_view("clientes",action="new")).pack(side="left")
        tree=ttk.Treeview(self,columns=("cuit","rubro","telefono","email"),show="tree headings");tree.heading("#0",text="Cliente");tree.column("#0",width=260)
        for key,label,width in (("cuit","CUIT/CUIL",120),("rubro","Rubro",200),("telefono","Teléfono",130),("email","Email",220)):tree.heading(key,text=label);tree.column(key,width=width)
        tree.pack(fill="both",expand=True)
        for client in app.client_service.list_clients():
            if client.get("regimen_principal")==regime:tree.insert("","end",text=client["nombre_razon_social"],values=(client["cuit_cuil"],client.get("rubro_display",""),client["telefono"],client["email"]))
