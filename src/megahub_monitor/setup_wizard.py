"""Setup Wizard — assistente de primeiro uso do SDWA.

Janela tkinter de 4 etapas que coleta identidade, webhook, faz login
no MegaHub e valida a coleta antes de iniciar o monitor.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from logging import getLogger
from pathlib import Path
from typing import Any

from .config_io import save_toml

logger = getLogger(__name__)

# URLs padrao do MegaHub
MEGAHUB_MINHA_FILA_URL = "https://megahub.megawork.com/Chamado/MinhaFila"
MEGAHUB_FILA_URL = "https://megahub.megawork.com/Chamado/Index"
VALIDATION_TEXT_MINHA_FILA = "Minha Fila"
VALIDATION_TEXT_FILA = "Fila"


def is_first_run(project_root: Path) -> bool:
    return not (project_root / "config" / "local" / "contexts.toml").exists()


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    ascii_only = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug or "perfil"


def _generate_configs(
    project_root: Path,
    full_name: str,
    role: str,
    webhook_url: str,
    enable_minha_fila: bool = True,
    enable_fila: bool = False,
) -> None:
    """Gera config/local/contexts.toml e profiles.toml a partir dos dados do wizard."""
    local_dir = project_root / "config" / "local"
    local_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "data" / "browser-profile-main").mkdir(parents=True, exist_ok=True)

    # --- contexts.toml ---
    contexts_data: dict[str, Any] = {
        "contexts": [
            {
                "id": "main-session",
                "name": "Sessao Principal",
                "enabled": True,
                "profile_dir": "data/browser-profile-main",
            },
        ],
        "sources": [],
    }

    if enable_minha_fila:
        contexts_data["sources"].append({
            "id": "minha-fila-principal",
            "name": "Minha Fila Principal",
            "kind": "minha_fila",
            "context_id": "main-session",
            "url": MEGAHUB_MINHA_FILA_URL,
            "enabled": True,
            "first_page_only": True,
            "consultant_name": full_name,
            "only_open": True,
            "only_assigned_to_me": True,
        })

    if enable_fila:
        contexts_data["sources"].append({
            "id": "fila-principal",
            "name": "Fila Principal",
            "kind": "fila",
            "context_id": "main-session",
            "url": MEGAHUB_FILA_URL,
            "enabled": True,
            "first_page_only": True,
            "include_closed": False,
            "include_assigned": True,
        })

    save_toml(local_dir / "contexts.toml", contexts_data)

    # --- profiles.toml ---
    profile_id = _slugify(full_name)
    profiles_data: dict[str, Any] = {
        "profiles": [
            {
                "id": profile_id,
                "name": full_name,
                "role": role,
                "enabled": True,
                "webhook_url": webhook_url,
            },
        ],
        "subscriptions": [],
    }

    if enable_minha_fila:
        profiles_data["subscriptions"].append({
            "id": "alerta-minha-fila",
            "name": "Alerta Minha Fila",
            "enabled": True,
            "source_ids": ["minha-fila-principal"],
            "profile_ids": [profile_id],
            "title_prefix": "Alerta da Minha Fila",
            "include_load": False,
            "ticket_types": [],
            "priorities": [],
            "companies": [],
            "consultants": [],
        })

    if enable_fila:
        profiles_data["subscriptions"].append({
            "id": "alerta-fila",
            "name": "Alerta Fila",
            "enabled": True,
            "source_ids": ["fila-principal"],
            "profile_ids": [profile_id],
            "title_prefix": "Novo chamado na Fila",
            "include_load": True,
            "ticket_types": [],
            "priorities": [],
            "companies": [],
            "consultants": [],
        })

    save_toml(local_dir / "profiles.toml", profiles_data)
    logger.info("Configuracao local gerada em %s", local_dir)


class SetupWizard:
    """Wizard tkinter de 4 etapas para configuracao inicial."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._completed = False
        # Playwright handles (managed during login step)
        self._pw = None
        self._browser_context = None
        self._page = None

    def run(self) -> bool:
        """Mostra o wizard. Retorna True se setup completo, False se cancelado."""
        import tkinter as tk
        from tkinter import ttk

        self._tk_root = tk.Tk()
        self._tk_root.title("MegaHub Monitor — Configuracao Inicial")
        self._tk_root.geometry("620x480")
        self._tk_root.resizable(False, False)
        self._tk_root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("Status.TLabel", font=("Segoe UI", 9))

        self._container = ttk.Frame(self._tk_root, padding=20)
        self._container.pack(fill="both", expand=True)

        self._step_1_identity()
        self._tk_root.mainloop()
        return self._completed

    # ------------------------------------------------------------------
    # Etapa 1: Identidade
    # ------------------------------------------------------------------

    def _step_1_identity(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._clear()

        ttk.Label(self._container, text="Bem-vindo ao MegaHub Monitor", style="Title.TLabel").pack(pady=(0, 5))
        ttk.Label(
            self._container,
            text="Vamos configurar o monitor para voce. Preencha seus dados abaixo.",
            style="Subtitle.TLabel",
        ).pack(pady=(0, 20))

        form = ttk.Frame(self._container)
        form.pack(fill="x", pady=10)

        ttk.Label(form, text="Nome completo (como aparece no MegaHub):").grid(
            row=0, column=0, sticky="w", pady=8
        )
        self._name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._name_var, width=50).grid(row=0, column=1, padx=10, pady=8)

        ttk.Label(form, text="Seu papel:").grid(row=1, column=0, sticky="w", pady=8)
        self._role_var = tk.StringVar(value="consultor")
        ttk.Combobox(
            form,
            textvariable=self._role_var,
            values=["consultor", "coordenador", "gestor"],
            width=20,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=10, pady=8)

        # Fontes
        ttk.Label(form, text="Monitorar:").grid(row=2, column=0, sticky="w", pady=8)
        source_frame = ttk.Frame(form)
        source_frame.grid(row=2, column=1, sticky="w", padx=10, pady=8)

        self._enable_minha_fila = tk.BooleanVar(value=True)
        ttk.Checkbutton(source_frame, text="Minha Fila", variable=self._enable_minha_fila).pack(
            side="left", padx=(0, 15)
        )
        self._enable_fila = tk.BooleanVar(value=False)
        ttk.Checkbutton(source_frame, text="Fila (gerencial)", variable=self._enable_fila).pack(side="left")

        self._step1_error = tk.StringVar()
        ttk.Label(self._container, textvariable=self._step1_error, foreground="red").pack(pady=5)

        ttk.Button(self._container, text="Proximo  >>", command=self._validate_step1).pack(pady=15)

    def _validate_step1(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            self._step1_error.set("Informe seu nome completo.")
            return
        if not self._enable_minha_fila.get() and not self._enable_fila.get():
            self._step1_error.set("Selecione pelo menos uma fila para monitorar.")
            return
        self._step_2_webhook()

    # ------------------------------------------------------------------
    # Etapa 2: Webhook
    # ------------------------------------------------------------------

    def _step_2_webhook(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._clear()

        ttk.Label(self._container, text="Notificacoes do Teams", style="Title.TLabel").pack(pady=(0, 5))
        ttk.Label(
            self._container,
            text="Informe a URL do webhook do Power Automate / Teams para receber alertas.",
            style="Subtitle.TLabel",
        ).pack(pady=(0, 20))

        form = ttk.Frame(self._container)
        form.pack(fill="x", pady=10)

        ttk.Label(form, text="Webhook URL:").grid(row=0, column=0, sticky="w", pady=8)
        self._webhook_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._webhook_var, width=60).grid(row=0, column=1, padx=10, pady=8)

        self._webhook_status = tk.StringVar()
        ttk.Label(self._container, textvariable=self._webhook_status, style="Status.TLabel").pack(pady=5)

        btn_frame = ttk.Frame(self._container)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Testar Webhook", command=self._test_webhook).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Proximo  >>", command=self._validate_step2).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="<< Voltar", command=self._step_1_identity).pack(side="left", padx=5)

    def _test_webhook(self) -> None:
        import requests

        url = self._webhook_var.get().strip()
        if not url.startswith("http"):
            self._webhook_status.set("URL invalida. Deve comecar com https://")
            return

        self._webhook_status.set("Enviando teste...")
        self._tk_root.update()

        payload = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {"type": "TextBlock", "text": "Teste MegaHub Monitor", "weight": "Bolder", "size": "Medium"},
                {"type": "TextBlock", "text": "Se voce esta vendo esta mensagem, o webhook esta funcionando!"},
            ],
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            if 200 <= resp.status_code < 300:
                self._webhook_status.set("Webhook OK! Verifique o Teams.")
            else:
                self._webhook_status.set(f"Falha: HTTP {resp.status_code}")
        except Exception as exc:
            self._webhook_status.set(f"Erro: {exc}")

    def _validate_step2(self) -> None:
        url = self._webhook_var.get().strip()
        if not url.startswith("http"):
            self._webhook_status.set("Informe uma URL valida antes de continuar.")
            return
        # Gerar configs antes do login para que o BrowserSession funcione
        _generate_configs(
            self._root,
            self._name_var.get().strip(),
            self._role_var.get().strip(),
            url,
            enable_minha_fila=self._enable_minha_fila.get(),
            enable_fila=self._enable_fila.get(),
        )
        self._step_3_login()

    # ------------------------------------------------------------------
    # Etapa 3: Login no MegaHub
    # ------------------------------------------------------------------

    def _step_3_login(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._clear()

        ttk.Label(self._container, text="Login no MegaHub", style="Title.TLabel").pack(pady=(0, 5))
        ttk.Label(
            self._container,
            text=(
                "Clique em 'Abrir Navegador' para fazer login no MegaHub.\n"
                "Faca o login manualmente e depois clique 'Concluir Login'."
            ),
            style="Subtitle.TLabel",
            justify="center",
        ).pack(pady=(0, 20))

        self._login_status = tk.StringVar(value="Aguardando...")
        ttk.Label(self._container, textvariable=self._login_status, style="Status.TLabel").pack(pady=10)

        btn_frame = ttk.Frame(self._container)
        btn_frame.pack(pady=10)
        self._btn_open = ttk.Button(btn_frame, text="Abrir Navegador", command=self._open_browser)
        self._btn_open.pack(side="left", padx=5)
        self._btn_finish_login = ttk.Button(
            btn_frame, text="Concluir Login", command=self._finish_login, state="disabled"
        )
        self._btn_finish_login.pack(side="left", padx=5)

        ttk.Button(self._container, text="Pular Login (configurar depois)", command=self._step_4_done).pack(pady=20)

    def _open_browser(self) -> None:
        self._login_status.set("Abrindo navegador...")
        self._btn_open.configure(state="disabled")
        self._tk_root.update()

        def _launch():
            try:
                from .adapters.itsm.megahub.browser_session import BrowserSession
                from .config import Settings

                settings = Settings.load()
                sources = settings.enabled_sources()
                if not sources:
                    self._tk_root.after(0, lambda: self._login_status.set("Nenhuma fonte habilitada."))
                    return

                source = sources[0]
                ctx = settings.get_context(source.context_id)
                session = BrowserSession(settings, ctx, getLogger("wizard.login"))

                url = source.url
                validation = VALIDATION_TEXT_MINHA_FILA if source.kind == "minha_fila" else VALIDATION_TEXT_FILA

                self._pw, self._browser_context, self._page = session.open_login_browser(url)
                self._validation_text = validation

                self._tk_root.after(0, lambda: self._login_status.set(
                    "Navegador aberto. Faca login e clique 'Concluir Login'."
                ))
                self._tk_root.after(0, lambda: self._btn_finish_login.configure(state="normal"))
            except Exception as err:
                msg = str(err)
                self._tk_root.after(0, lambda: self._login_status.set(f"Erro: {msg}"))
                self._tk_root.after(0, lambda: self._btn_open.configure(state="normal"))

        threading.Thread(target=_launch, daemon=True).start()

    def _finish_login(self) -> None:
        if not self._page:
            self._login_status.set("Navegador nao foi aberto.")
            return

        self._login_status.set("Verificando autenticacao...")
        self._tk_root.update()

        try:
            from .adapters.itsm.megahub.browser_session import BrowserSession

            authenticated = BrowserSession.is_authenticated(None, self._page, self._validation_text)
        except Exception:
            authenticated = False

        self._close_browser()

        if authenticated:
            self._login_status.set("Login confirmado!")
            self._tk_root.after(1000, self._step_4_done)
        else:
            self._login_status.set("Falha na validacao. Tente novamente.")
            self._btn_open.configure(state="normal")
            self._btn_finish_login.configure(state="disabled")

    def _close_browser(self) -> None:
        try:
            if self._browser_context:
                self._browser_context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self._browser_context = None
        self._page = None

    # ------------------------------------------------------------------
    # Etapa 4: Validacao e conclusao
    # ------------------------------------------------------------------

    def _step_4_done(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._clear()

        ttk.Label(self._container, text="Tudo pronto!", style="Title.TLabel").pack(pady=(0, 5))

        self._done_status = tk.StringVar(value="Configuracao salva com sucesso.")
        ttk.Label(self._container, textvariable=self._done_status, style="Subtitle.TLabel").pack(pady=10)

        info_frame = ttk.Frame(self._container)
        info_frame.pack(fill="x", pady=10)

        name = self._name_var.get().strip()
        role = self._role_var.get().strip()
        sources = []
        if self._enable_minha_fila.get():
            sources.append("Minha Fila")
        if self._enable_fila.get():
            sources.append("Fila Gerencial")

        ttk.Label(info_frame, text=f"Nome: {name}").pack(anchor="w", padx=20)
        ttk.Label(info_frame, text=f"Papel: {role}").pack(anchor="w", padx=20)
        ttk.Label(info_frame, text=f"Fontes: {', '.join(sources)}").pack(anchor="w", padx=20)
        ttk.Label(info_frame, text="Webhook: configurado").pack(anchor="w", padx=20)

        ttk.Label(
            self._container,
            text=(
                "O monitor sera iniciado na bandeja do sistema.\n"
                "Use o icone para ver status, chamados e configuracoes."
            ),
            style="Subtitle.TLabel",
            justify="center",
        ).pack(pady=20)

        ttk.Button(self._container, text="Iniciar Monitor", command=self._finish).pack(pady=10)

    def _finish(self) -> None:
        self._completed = True
        self._tk_root.destroy()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear(self) -> None:
        for widget in self._container.winfo_children():
            widget.destroy()

    def _on_cancel(self) -> None:
        self._close_browser()
        self._completed = False
        self._tk_root.destroy()
