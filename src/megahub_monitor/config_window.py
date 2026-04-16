"""ConfigWindow — janela de configuracao completa do SDWA.

Permite editar perfis (webhooks), membros da equipe e fontes (URLs)
sem tocar nos arquivos TOML manualmente.
Tambem suporta export/import de um arquivo de configuracao simplificado
para troca com o coordenador.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from .config_io import find_config as _find_config
from .config_io import load_toml as _load_toml
from .config_io import save_toml as _save_toml

# ---------------------------------------------------------------------------
# ConfigWindow
# ---------------------------------------------------------------------------

class ConfigWindow:
    """Janela Toplevel com abas para editar profiles, teams e contexts."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._win = None

    def show(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._win.focus_force()
            return

        win = tk.Toplevel()
        win.title("SDWA — Configuração Completa")
        win.geometry("820x540")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._win = win

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # Tab Notificações
        f_notif = ttk.Frame(nb)
        nb.add(f_notif, text="  Notificações  ")
        self._build_profiles_tab(f_notif)

        # Tab Membros
        f_members = ttk.Frame(nb)
        nb.add(f_members, text="  Membros  ")
        self._build_members_tab(f_members)

        # Tab Filas
        f_sources = ttk.Frame(nb)
        nb.add(f_sources, text="  Filas  ")
        self._build_sources_tab(f_sources)

        # Rodapé export/import
        footer = ttk.Frame(win)
        footer.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(footer, text="Exportar Configuração…", command=self._export_config).pack(
            side="left", padx=4
        )
        ttk.Button(footer, text="Importar Configuração…", command=self._import_config).pack(
            side="left", padx=4
        )
        ttk.Label(
            footer,
            text="Exporte um arquivo para o coordenador preencher e devolva via Importar.",
            foreground="gray",
        ).pack(side="left", padx=8)

        win.wait_window()

    # ------------------------------------------------------------------
    # Tab Notificações
    # ------------------------------------------------------------------

    def _build_profiles_tab(self, parent) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        profiles_path = _find_config(
            self._root, "config/local/profiles.toml", "config/profiles.toml"
        )
        # fallback legado
        if not profiles_path.exists():
            profiles_path = _find_config(
                self._root, "config/local/routing.toml", "config/routing.toml"
            )

        ttk.Label(parent, text=f"Arquivo: {profiles_path.relative_to(self._root)}",
                  foreground="gray").pack(anchor="w", padx=8, pady=(6, 2))

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=6, pady=4)

        cols = ("id", "nome", "funcao", "webhook")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("id",      text="ID")
        tree.heading("nome",    text="Nome")
        tree.heading("funcao",  text="Função")
        tree.heading("webhook", text="Webhook URL")
        tree.column("id",      width=120, anchor="w")
        tree.column("nome",    width=150, anchor="w")
        tree.column("funcao",  width=90,  anchor="w")
        tree.column("webhook", width=360, anchor="w")

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _reload():
            tree.delete(*tree.get_children())
            d = _load_toml(profiles_path)
            ps = d.get("profiles", d.get("recipients", []))
            for p in ps:
                tree.insert("", "end", values=(
                    p.get("id", ""),
                    p.get("name", ""),
                    p.get("role", ""),
                    p.get("webhook_url", ""),
                ))

        _reload()

        def _edit():
            sel = tree.focus()
            if not sel:
                messagebox.showinfo("Aviso", "Selecione um perfil para editar.")
                return
            vals = tree.item(sel, "values")
            profile_id = vals[0]

            dlg = tk.Toplevel(self._win)
            dlg.title(f"Editar Perfil — {profile_id}")
            dlg.geometry("520x200")
            dlg.resizable(False, False)
            dlg.grab_set()

            ttk.Label(dlg, text="Nome:").grid(row=0, column=0, sticky="w", padx=12, pady=8)
            name_var = tk.StringVar(value=vals[1])
            ttk.Entry(dlg, textvariable=name_var, width=45).grid(row=0, column=1, padx=8, pady=8)

            ttk.Label(dlg, text="Função:").grid(row=1, column=0, sticky="w", padx=12, pady=4)
            role_var = tk.StringVar(value=vals[2])
            ttk.Combobox(dlg, textvariable=role_var, values=["coordinator", "developer", "manager", "recipient"],
                         width=20, state="readonly").grid(row=1, column=1, sticky="w", padx=8, pady=4)

            ttk.Label(dlg, text="Webhook URL:").grid(row=2, column=0, sticky="w", padx=12, pady=4)
            wh_var = tk.StringVar(value=vals[3])
            ttk.Entry(dlg, textvariable=wh_var, width=60).grid(row=2, column=1, padx=8, pady=4)

            def _save_edit():
                d = _load_toml(profiles_path)
                ps = d.get("profiles", d.get("recipients", []))
                for p in ps:
                    if p.get("id") == profile_id:
                        p["name"] = name_var.get().strip()
                        p["role"] = role_var.get().strip()
                        p["webhook_url"] = wh_var.get().strip()
                # preserve subscriptions key
                key = "profiles" if "profiles" in d else "recipients"
                d[key] = ps
                _save_toml(profiles_path, d)
                _reload()
                dlg.destroy()

            ttk.Button(dlg, text="Salvar", command=_save_edit).grid(
                row=3, column=0, columnspan=2, pady=12
            )

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(anchor="w", padx=8, pady=4)
        ttk.Button(btn_frame, text="Editar Selecionado", command=_edit).pack(side="left", padx=4)

        ttk.Label(
            parent,
            text="Dica: perfis são destinatários configurados em profiles.toml.",
            foreground="gray",
        ).pack(anchor="w", padx=8, pady=(0, 4))

    # ------------------------------------------------------------------
    # Tab Membros
    # ------------------------------------------------------------------

    def _build_members_tab(self, parent) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        teams_path = _find_config(
            self._root, "config/local/teams.toml", "config/teams.toml"
        )

        ttk.Label(parent, text=f"Arquivo: {teams_path.relative_to(self._root)}",
                  foreground="gray").pack(anchor="w", padx=8, pady=(6, 2))

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=6, pady=4)

        cols = ("id", "nome", "funcao", "ativo", "max", "webhook")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("id",      text="ID")
        tree.heading("nome",    text="Nome")
        tree.heading("funcao",  text="Função")
        tree.heading("ativo",   text="Ativo")
        tree.heading("max",     text="Max.")
        tree.heading("webhook", text="Webhook URL")
        tree.column("id",      width=120, anchor="w")
        tree.column("nome",    width=160, anchor="w")
        tree.column("funcao",  width=90,  anchor="w")
        tree.column("ativo",   width=50,  anchor="center")
        tree.column("max",     width=45,  anchor="center")
        tree.column("webhook", width=280, anchor="w")

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _reload():
            tree.delete(*tree.get_children())
            d = _load_toml(teams_path)
            for m in d.get("members", []):
                tree.insert("", "end", values=(
                    m.get("id", ""),
                    m.get("name", ""),
                    m.get("role", ""),
                    "✓" if m.get("active", True) else "✗",
                    str(m.get("max_concurrent_tickets", 5)),
                    m.get("webhook_url", ""),
                ))

        _reload()

        def _member_dialog(title: str, defaults: dict | None = None):
            dlg = tk.Toplevel(self._win)
            dlg.title(title)
            dlg.geometry("520x280")
            dlg.resizable(False, False)
            dlg.grab_set()
            d = defaults or {}

            fields: dict[str, tk.Variable] = {}

            def _row(label: str, row: int, var: tk.Variable, widget_fn):
                ttk.Label(dlg, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=6)
                w = widget_fn(dlg, var)
                w.grid(row=row, column=1, sticky="w", padx=8, pady=6)
                fields[label] = var

            id_var = tk.StringVar(value=d.get("id", ""))
            _row("ID (slug):", 0, id_var, lambda p, v: ttk.Entry(p, textvariable=v, width=30))

            name_var = tk.StringVar(value=d.get("name", ""))
            _row("Nome:", 1, name_var, lambda p, v: ttk.Entry(p, textvariable=v, width=40))

            role_var = tk.StringVar(value=d.get("role", "developer"))
            _row("Função:", 2, role_var,
                 lambda p, v: ttk.Combobox(p, textvariable=v,
                                           values=["developer", "coordinator", "manager"],
                                           width=20, state="readonly"))

            wh_var = tk.StringVar(value=d.get("webhook_url", ""))
            _row("Webhook URL:", 3, wh_var, lambda p, v: ttk.Entry(p, textvariable=v, width=55))

            active_var = tk.BooleanVar(value=d.get("active", True))
            ttk.Label(dlg, text="Ativo:").grid(row=4, column=0, sticky="w", padx=12, pady=6)
            ttk.Checkbutton(dlg, variable=active_var).grid(row=4, column=1, sticky="w", padx=8)

            max_var = tk.StringVar(value=str(d.get("max_concurrent_tickets", 5)))
            _row("Max. chamados:", 5, max_var, lambda p, v: ttk.Entry(p, textvariable=v, width=6))

            result: dict = {}

            def _ok():
                mid = id_var.get().strip()
                if not mid:
                    messagebox.showerror("Erro", "ID não pode ser vazio.", parent=dlg)
                    return
                try:
                    max_v = int(max_var.get())
                except ValueError:
                    messagebox.showerror("Erro", "Max. chamados deve ser um inteiro.", parent=dlg)
                    return
                result.update({
                    "id": mid,
                    "name": name_var.get().strip(),
                    "role": role_var.get().strip(),
                    "webhook_url": wh_var.get().strip(),
                    "active": active_var.get(),
                    "max_concurrent_tickets": max_v,
                    "skills": d.get("skills", []),
                })
                dlg.destroy()

            ttk.Button(dlg, text="OK", command=_ok).grid(
                row=6, column=0, columnspan=2, pady=12
            )
            dlg.wait_window()
            return result or None

        def _add():
            data = _member_dialog("Adicionar Membro")
            if not data:
                return
            doc = _load_toml(teams_path)
            members = doc.get("members", [])
            if any(m.get("id") == data["id"] for m in members):
                messagebox.showerror("Erro", f"ID '{data['id']}' já existe.")
                return
            members.append(data)
            doc["members"] = members
            _save_toml(teams_path, doc)
            _reload()

        def _edit():
            sel = tree.focus()
            if not sel:
                messagebox.showinfo("Aviso", "Selecione um membro para editar.")
                return
            vals = tree.item(sel, "values")
            member_id = vals[0]
            doc = _load_toml(teams_path)
            members = doc.get("members", [])
            existing = next((m for m in members if m.get("id") == member_id), None)
            if not existing:
                return

            data = _member_dialog(f"Editar Membro — {member_id}", defaults=existing)
            if not data:
                return
            for i, m in enumerate(members):
                if m.get("id") == member_id:
                    members[i] = data
                    break
            doc["members"] = members
            _save_toml(teams_path, doc)
            _reload()

        def _remove():
            sel = tree.focus()
            if not sel:
                messagebox.showinfo("Aviso", "Selecione um membro para remover.")
                return
            vals = tree.item(sel, "values")
            member_id = vals[0]
            if not messagebox.askyesno("Confirmar", f"Remover membro '{member_id}'?"):
                return
            doc = _load_toml(teams_path)
            doc["members"] = [m for m in doc.get("members", []) if m.get("id") != member_id]
            _save_toml(teams_path, doc)
            _reload()

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(anchor="w", padx=8, pady=4)
        ttk.Button(btn_frame, text="Adicionar", command=_add).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Editar Selecionado", command=_edit).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Remover Selecionado", command=_remove).pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Tab Filas
    # ------------------------------------------------------------------

    def _build_sources_tab(self, parent) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        contexts_path = _find_config(
            self._root, "config/local/contexts.toml", "config/contexts.toml"
        )

        ttk.Label(parent, text=f"Arquivo: {contexts_path.relative_to(self._root)}",
                  foreground="gray").pack(anchor="w", padx=8, pady=(6, 2))

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=6, pady=4)

        cols = ("id", "nome", "tipo", "habilitada", "url")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("id",         text="ID")
        tree.heading("nome",       text="Nome")
        tree.heading("tipo",       text="Tipo")
        tree.heading("habilitada", text="Ativa")
        tree.heading("url",        text="URL")
        tree.column("id",         width=120, anchor="w")
        tree.column("nome",       width=140, anchor="w")
        tree.column("tipo",       width=80,  anchor="w")
        tree.column("habilitada", width=50,  anchor="center")
        tree.column("url",        width=360, anchor="w")

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _reload():
            tree.delete(*tree.get_children())
            d = _load_toml(contexts_path)
            for s in d.get("sources", []):
                tree.insert("", "end", values=(
                    s.get("id", ""),
                    s.get("name", ""),
                    s.get("kind", ""),
                    "✓" if s.get("enabled", True) else "✗",
                    s.get("url", ""),
                ))

        _reload()

        def _edit():
            sel = tree.focus()
            if not sel:
                messagebox.showinfo("Aviso", "Selecione uma fila para editar.")
                return
            vals = tree.item(sel, "values")
            source_id = vals[0]
            doc = _load_toml(contexts_path)
            sources = doc.get("sources", [])
            existing = next((s for s in sources if s.get("id") == source_id), None)
            if not existing:
                return

            dlg = tk.Toplevel(self._win)
            dlg.title(f"Editar Fila — {source_id}")
            dlg.geometry("580x180")
            dlg.resizable(False, False)
            dlg.grab_set()

            ttk.Label(dlg, text="URL:").grid(row=0, column=0, sticky="w", padx=12, pady=10)
            url_var = tk.StringVar(value=existing.get("url", ""))
            ttk.Entry(dlg, textvariable=url_var, width=65).grid(row=0, column=1, padx=8, pady=10)

            enabled_var = tk.BooleanVar(value=existing.get("enabled", True))
            ttk.Label(dlg, text="Habilitada:").grid(row=1, column=0, sticky="w", padx=12, pady=6)
            ttk.Checkbutton(dlg, variable=enabled_var).grid(row=1, column=1, sticky="w", padx=8)

            def _save_edit():
                for s in sources:
                    if s.get("id") == source_id:
                        s["url"] = url_var.get().strip()
                        s["enabled"] = enabled_var.get()
                doc["sources"] = sources
                _save_toml(contexts_path, doc)
                _reload()
                dlg.destroy()

            ttk.Button(dlg, text="Salvar", command=_save_edit).grid(
                row=2, column=0, columnspan=2, pady=12
            )

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(anchor="w", padx=8, pady=4)
        ttk.Button(btn_frame, text="Editar URL / Habilitar", command=_edit).pack(
            side="left", padx=4
        )
        ttk.Label(
            parent,
            text="Dica: edite apenas URL e habilitada. Não crie novas filas por aqui.",
            foreground="gray",
        ).pack(anchor="w", padx=8, pady=(0, 4))

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def _export_config(self) -> None:
        from tkinter import filedialog, messagebox

        path = filedialog.asksaveasfilename(
            parent=self._win,
            title="Exportar Configuração",
            defaultextension=".toml",
            initialfile="sdwa-config-export.toml",
            filetypes=[("TOML files", "*.toml"), ("All files", "*.*")],
        )
        if not path:
            return

        profiles_path = _find_config(
            self._root, "config/local/profiles.toml", "config/profiles.toml"
        )
        if not profiles_path.exists():
            profiles_path = _find_config(
                self._root, "config/local/routing.toml", "config/routing.toml"
            )
        teams_path = _find_config(
            self._root, "config/local/teams.toml", "config/teams.toml"
        )
        contexts_path = _find_config(
            self._root, "config/local/contexts.toml", "config/contexts.toml"
        )

        profiles_doc = _load_toml(profiles_path)
        teams_doc = _load_toml(teams_path)
        contexts_doc = _load_toml(contexts_path)

        profiles = profiles_doc.get("profiles", profiles_doc.get("recipients", []))
        members = teams_doc.get("members", [])
        sources = contexts_doc.get("sources", [])

        lines: list[str] = [
            "# SDWA — Arquivo de configuração para troca com o coordenador",
            "# Preencha os campos marcados com TODO e envie de volta.",
            "# Importe no app: ícone bandeja → Configuração Completa → Importar Configuração",
            "",
            "# ===========================================================================",
            "# WEBHOOKS DOS PERFIS DE NOTIFICAÇÃO",
            "# ===========================================================================",
            "",
        ]
        for p in profiles:
            pid = p.get("id", "?")
            name = p.get("name", "?")
            role = p.get("role", "?")
            webhook = p.get("webhook_url", "")
            mark = "" if webhook else "  # TODO: cole a URL do webhook aqui"
            lines.append("[[perfis]]")
            lines.append(f'id = "{pid}"')
            lines.append(f'nome = "{name}"')
            lines.append(f'funcao = "{role}"')
            lines.append(f'webhook = "{webhook}"{mark}')
            lines.append("")

        lines += [
            "# ===========================================================================",
            "# MEMBROS DA EQUIPE",
            "# ===========================================================================",
            "",
        ]
        for m in members:
            mid = m.get("id", "?")
            name = m.get("name", "?")
            role = m.get("role", "developer")
            webhook = m.get("webhook_url", "")
            active = m.get("active", True)
            mark = "  # TODO: cole webhook" if not webhook else ""
            lines.append("[[membros]]")
            lines.append(f'id = "{mid}"')
            lines.append(f'nome = "{name}"')
            lines.append(f'funcao = "{role}"')
            lines.append(f'webhook = "{webhook}"{mark}')
            lines.append(f"ativo = {'true' if active else 'false'}")
            lines.append("")

        lines += [
            "# ===========================================================================",
            "# FILAS / FONTES",
            "# ===========================================================================",
            "",
        ]
        for s in sources:
            sid = s.get("id", "?")
            name = s.get("name", sid)
            url = s.get("url", "")
            enabled = s.get("enabled", True)
            kind = s.get("kind", "fila")
            mark = "  # TODO: cole URL da fila" if not url else ""
            lines.append("[[filas]]")
            lines.append(f'id = "{sid}"')
            lines.append(f'nome = "{name}"')
            lines.append(f'tipo = "{kind}"')
            lines.append(f'url = "{url}"{mark}')
            lines.append(f"habilitada = {'true' if enabled else 'false'}")
            lines.append("")

        Path(path).write_text("\n".join(lines), encoding="utf-8")
        messagebox.showinfo(
            "Exportado",
            f"Arquivo exportado em:\n{path}\n\nPreencha os campos TODO e use 'Importar' para aplicar.",
            parent=self._win,
        )

    def _import_config(self) -> None:
        from tkinter import filedialog, messagebox

        path = filedialog.askopenfilename(
            parent=self._win,
            title="Importar Configuração",
            filetypes=[("TOML files", "*.toml"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "rb") as fh:
                imported = tomllib.load(fh)
        except Exception as exc:
            messagebox.showerror("Erro ao ler arquivo", str(exc), parent=self._win)
            return

        profiles_path = _find_config(
            self._root, "config/local/profiles.toml", "config/profiles.toml"
        )
        if not profiles_path.exists():
            profiles_path = _find_config(
                self._root, "config/local/routing.toml", "config/routing.toml"
            )
        teams_path = _find_config(
            self._root, "config/local/teams.toml", "config/teams.toml"
        )
        contexts_path = _find_config(
            self._root, "config/local/contexts.toml", "config/contexts.toml"
        )

        changes: list[str] = []

        # Perfis
        imported_profiles = imported.get("perfis", [])
        if imported_profiles:
            doc = _load_toml(profiles_path)
            key = "profiles" if "profiles" in doc else "recipients"
            profiles = doc.get(key, [])
            for ip in imported_profiles:
                wh = str(ip.get("webhook", "")).strip()
                if not wh:
                    continue
                for p in profiles:
                    if p.get("id") == ip.get("id"):
                        p["webhook_url"] = wh
                        if ip.get("nome"):
                            p["name"] = str(ip["nome"]).strip()
                        if ip.get("funcao"):
                            p["role"] = str(ip["funcao"]).strip()
                        changes.append(f"Perfil '{p['id']}': webhook atualizado")
            doc[key] = profiles
            _save_toml(profiles_path, doc)

        # Membros
        imported_members = imported.get("membros", [])
        if imported_members:
            doc = _load_toml(teams_path)
            members = doc.get("members", [])
            existing_ids = {m.get("id") for m in members}
            for im in imported_members:
                mid = str(im.get("id", "")).strip()
                if not mid:
                    continue
                webhook = str(im.get("webhook", "")).strip()
                name = str(im.get("nome", "")).strip()
                role = str(im.get("funcao", "")).strip()
                if mid in existing_ids:
                    for m in members:
                        if m.get("id") == mid:
                            if webhook:
                                m["webhook_url"] = webhook
                            if name:
                                m["name"] = name
                            if role:
                                m["role"] = role
                            if "ativo" in im:
                                m["active"] = bool(im["ativo"])
                            changes.append(f"Membro '{mid}': atualizado")
                else:
                    members.append({
                        "id": mid,
                        "name": name or mid,
                        "role": role or "developer",
                        "webhook_url": webhook,
                        "active": bool(im.get("ativo", True)),
                        "skills": [],
                        "max_concurrent_tickets": 5,
                    })
                    changes.append(f"Membro '{mid}': adicionado")
            doc["members"] = members
            _save_toml(teams_path, doc)

        # Filas
        imported_sources = imported.get("filas", [])
        if imported_sources:
            doc = _load_toml(contexts_path)
            sources = doc.get("sources", [])
            for isrc in imported_sources:
                sid = str(isrc.get("id", "")).strip()
                url = str(isrc.get("url", "")).strip()
                if not sid:
                    continue
                for s in sources:
                    if s.get("id") == sid:
                        if url:
                            s["url"] = url
                        if "habilitada" in isrc:
                            s["enabled"] = bool(isrc["habilitada"])
                        changes.append(f"Fila '{sid}': atualizada")
            doc["sources"] = sources
            _save_toml(contexts_path, doc)

        if changes:
            messagebox.showinfo(
                "Importado",
                "Configuração aplicada com sucesso:\n\n" + "\n".join(f"• {c}" for c in changes),
                parent=self._win,
            )
        else:
            messagebox.showinfo(
                "Importado",
                "Arquivo importado, mas nenhuma alteração foi aplicada.\n"
                "Verifique se os IDs correspondem e os campos TODO foram preenchidos.",
                parent=self._win,
            )
