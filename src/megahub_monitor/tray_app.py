"""SDWA Tray App — ícone na bandeja do sistema com painel de status.

Inicie com:  pythonw.exe main.py tray
Ou via VBS:  wscript.exe scripts\\start-tray.vbs
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pystray
from dotenv import dotenv_values
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
TASK_NAME = "SDWA Monitor"
ICON_SIZE = 64
COLOR_GREEN = "#2ecc40"
COLOR_YELLOW = "#ffdc00"
COLOR_RED = "#ff4136"
REFRESH_INTERVAL = 30  # segundos


# ---------------------------------------------------------------------------
# TrayDbReader — acesso read-only ao SQLite sem instanciar Settings
# ---------------------------------------------------------------------------
class TrayDbReader:
    """Lê dados do banco de forma read-only, sem instanciar Settings completo."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection | None:
        if not self._db_path.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError:
            return None

    def get_source_states(self) -> list[dict]:
        conn = self._connect()
        if not conn:
            return []
        with conn:
            try:
                rows = conn.execute(
                    "SELECT source_id, last_run_at, last_success_at FROM source_states"
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                return []

    def get_active_workflow_items(self) -> list[dict]:
        conn = self._connect()
        if not conn:
            return []
        with conn:
            try:
                rows = conn.execute(
                    """
                    SELECT ticket_number, source_id, current_state,
                           detected_at, last_state_change_at,
                           COALESCE(last_known_itsm_status, '') AS last_known_itsm_status
                    FROM workflow_items
                    WHERE current_state NOT IN (
                        'COMPLETED', 'COMPLETION_NOTIFIED'
                    )
                    ORDER BY detected_at DESC
                    LIMIT 200
                    """
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                return []

    def get_recent_audit_events(self, limit: int = 20) -> list[dict]:
        conn = self._connect()
        if not conn:
            return []
        with conn:
            try:
                rows = conn.execute(
                    """
                    SELECT timestamp, action, ticket_number,
                           source_id, actor
                    FROM audit_events
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                return []

    def get_last_success_at(self) -> str | None:
        conn = self._connect()
        if not conn:
            return None
        with conn:
            try:
                row = conn.execute(
                    "SELECT MAX(last_success_at) AS t FROM source_states"
                ).fetchone()
                return row["t"] if row else None
            except sqlite3.OperationalError:
                return None


# ---------------------------------------------------------------------------
# IconFactory — ícone circular PIL gerado programaticamente
# ---------------------------------------------------------------------------
class IconFactory:
    @staticmethod
    def make(color: str) -> Image.Image:
        img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        m = 4
        draw.ellipse(
            [(m, m), (ICON_SIZE - m, ICON_SIZE - m)],
            fill=color,
            outline=(255, 255, 255, 200),
            width=2,
        )
        return img

    @staticmethod
    def color_for(last_success_at: str | None) -> str:
        if not last_success_at:
            return COLOR_RED
        try:
            ts = datetime.fromisoformat(last_success_at.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - ts
            minutes = delta.total_seconds() / 60
            if minutes < 10:
                return COLOR_GREEN
            if minutes < 30:
                return COLOR_YELLOW
            return COLOR_RED
        except (ValueError, TypeError):
            return COLOR_RED


# ---------------------------------------------------------------------------
# StatusWindow — janela Tkinter com 4 tabs
# ---------------------------------------------------------------------------
class StatusWindow:
    def __init__(self, db: TrayDbReader, project_root: Path) -> None:
        self._db = db
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
        win.title("SDWA — Painel de Controle")
        win.geometry("750x480")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._win = win

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # --- Tab Status ---
        f_status = ttk.Frame(nb)
        nb.add(f_status, text="  Status  ")
        self._status_widgets: dict = {}
        self._build_status_tab(f_status)

        # --- Tab Chamados ---
        f_tickets = ttk.Frame(nb)
        nb.add(f_tickets, text="  Chamados  ")
        self._tickets_tree = None
        self._build_tickets_tab(f_tickets)

        # --- Tab Eventos ---
        f_events = ttk.Frame(nb)
        nb.add(f_events, text="  Eventos  ")
        self._events_tree = None
        self._build_events_tab(f_events)

        # --- Tab Configurações ---
        f_cfg = ttk.Frame(nb)
        nb.add(f_cfg, text="  Configurações  ")
        self._build_settings_tab(f_cfg)

        self._refresh()
        self._schedule_refresh()

    # ------------------------------------------------------------------
    def _build_status_tab(self, parent) -> None:
        import tkinter as tk
        from tkinter import ttk

        pad = {"padx": 12, "pady": 4}

        ttk.Label(parent, text="Tarefa Agendada:", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", **pad
        )
        lbl_task = ttk.Label(parent, text="—")
        lbl_task.grid(row=0, column=1, sticky="w", **pad)
        self._status_widgets["task"] = lbl_task

        ttk.Label(parent, text="Última execução:", font=("", 10, "bold")).grid(
            row=1, column=0, sticky="w", **pad
        )
        lbl_last = ttk.Label(parent, text="—")
        lbl_last.grid(row=1, column=1, sticky="w", **pad)
        self._status_widgets["last"] = lbl_last

        ttk.Separator(parent, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=6, padx=8
        )

        ttk.Label(parent, text="Fontes:", font=("", 10, "bold")).grid(
            row=3, column=0, sticky="nw", **pad
        )
        frame_sources = tk.Frame(parent)
        frame_sources.grid(row=3, column=1, sticky="w", **pad)
        self._status_widgets["sources_frame"] = frame_sources

        btn = ttk.Button(
            parent,
            text="Executar Agora",
            command=self._run_once,
        )
        btn.grid(row=5, column=0, columnspan=2, pady=16, padx=12, sticky="w")

    def _build_tickets_tab(self, parent) -> None:
        from tkinter import ttk

        cols = ("ticket", "fonte", "estado", "detectado", "status_itsm")
        tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        tree.heading("ticket",      text="Chamado")
        tree.heading("fonte",       text="Fonte")
        tree.heading("estado",      text="Estado")
        tree.heading("detectado",   text="Detectado")
        tree.heading("status_itsm", text="Status ITSM")
        tree.column("ticket",      width=90,  anchor="w")
        tree.column("fonte",       width=100, anchor="w")
        tree.column("estado",      width=160, anchor="w")
        tree.column("detectado",   width=140, anchor="w")
        tree.column("status_itsm", width=120, anchor="w")

        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb.pack(side="right", fill="y", pady=6)
        self._tickets_tree = tree

    def _build_events_tab(self, parent) -> None:
        from tkinter import ttk

        cols = ("ts", "acao", "chamado", "fonte", "ator")
        tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        tree.heading("ts",      text="Timestamp")
        tree.heading("acao",    text="Ação")
        tree.heading("chamado", text="Chamado")
        tree.heading("fonte",   text="Fonte")
        tree.heading("ator",    text="Ator")
        tree.column("ts",      width=150, anchor="w")
        tree.column("acao",    width=180, anchor="w")
        tree.column("chamado", width=90,  anchor="w")
        tree.column("fonte",   width=100, anchor="w")
        tree.column("ator",    width=120, anchor="w")

        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb.pack(side="right", fill="y", pady=6)
        self._events_tree = tree

    def _build_settings_tab(self, parent) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        pad = {"padx": 12, "pady": 6}

        ttk.Label(
            parent,
            text="Editar configurações básicas do .env",
            font=("", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))

        ttk.Label(parent, text="Navegador headless (sem janela):").grid(
            row=1, column=0, sticky="w", **pad
        )
        headless_var = tk.BooleanVar()
        ttk.Checkbutton(parent, variable=headless_var).grid(
            row=1, column=1, sticky="w", **pad
        )

        ttk.Label(parent, text="Intervalo do monitor (segundos):").grid(
            row=2, column=0, sticky="w", **pad
        )
        interval_var = tk.StringVar()
        ttk.Entry(parent, textvariable=interval_var, width=8).grid(
            row=2, column=1, sticky="w", **pad
        )

        ttk.Label(parent, text="Timeout Teams (segundos):").grid(
            row=3, column=0, sticky="w", **pad
        )
        timeout_var = tk.StringVar()
        ttk.Entry(parent, textvariable=timeout_var, width=8).grid(
            row=3, column=1, sticky="w", **pad
        )

        # Carregar valores atuais
        env_path = self._root / ".env"
        env_vals = dotenv_values(str(env_path))
        headless_val = env_vals.get("BROWSER_HEADLESS", "true").strip().lower()
        headless_var.set(headless_val in {"1", "true", "yes", "y", "on"})
        interval_var.set(env_vals.get("MONITOR_INTERVAL_SECONDS", "120"))
        timeout_var.set(env_vals.get("TEAMS_REQUEST_TIMEOUT_SECONDS", "15"))

        def save():
            from dotenv import set_key as dotenv_set_key

            # Validar tipos
            try:
                int_val = int(interval_var.get())
                if int_val < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Erro", "Intervalo deve ser um número inteiro positivo.")
                return

            try:
                to_val = int(timeout_var.get())
                if to_val < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Erro", "Timeout deve ser um número inteiro positivo.")
                return

            dotenv_set_key(str(env_path), "BROWSER_HEADLESS", "true" if headless_var.get() else "false")
            dotenv_set_key(str(env_path), "MONITOR_INTERVAL_SECONDS", str(int_val))
            dotenv_set_key(str(env_path), "TEAMS_REQUEST_TIMEOUT_SECONDS", str(to_val))
            messagebox.showinfo(
                "Salvo",
                "Configurações salvas com sucesso.\nAs mudanças entram em vigor no próximo ciclo.",
            )

        ttk.Button(parent, text="Salvar", command=save).grid(
            row=4, column=0, columnspan=2, pady=16, padx=12, sticky="w"
        )

        ttk.Label(
            parent,
            text="Webhook URLs e credenciais devem ser editados diretamente no arquivo .env",
            foreground="gray",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 4))

        ttk.Separator(parent, orient="horizontal").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=8, padx=8
        )
        ttk.Button(
            parent,
            text="Configuração Completa (membros, webhooks, filas) →",
            command=self._open_config_window,
        ).grid(row=7, column=0, columnspan=2, pady=4, padx=12, sticky="w")

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        import tkinter as tk

        # --- Status tab ---
        task_exists, task_state = _detect_task()
        if task_exists:
            label = f"Ativa ({task_state})"
            color = "green" if task_state.lower() in ("ready", "running") else "orange"
        else:
            label = "Não registrada"
            color = "red"
        self._status_widgets["task"].config(text=label, foreground=color)

        last = self._db.get_last_success_at()
        self._status_widgets["last"].config(
            text=_fmt_ts(last) if last else "Nunca executou"
        )

        # Recria labels de fontes
        frame = self._status_widgets["sources_frame"]
        for w in frame.winfo_children():
            w.destroy()
        sources = self._db.get_source_states()
        if not sources:
            tk.Label(frame, text="Sem dados ainda.", foreground="gray").pack(anchor="w")
        for i, s in enumerate(sources):
            ok = bool(s.get("last_success_at"))
            dot = "●"
            c = "green" if ok else "red"
            tk.Label(
                frame,
                text=f"{dot} {s['source_id']}  —  {_fmt_ts(s.get('last_success_at'))}",
                foreground=c,
            ).pack(anchor="w")

        # --- Chamados tab ---
        if self._tickets_tree:
            self._tickets_tree.delete(*self._tickets_tree.get_children())
            for item in self._db.get_active_workflow_items():
                self._tickets_tree.insert(
                    "",
                    "end",
                    values=(
                        item["ticket_number"],
                        item["source_id"],
                        item["current_state"],
                        _fmt_ts(item.get("detected_at")),
                        item.get("last_known_itsm_status") or "—",
                    ),
                )

        # --- Eventos tab ---
        if self._events_tree:
            self._events_tree.delete(*self._events_tree.get_children())
            for ev in self._db.get_recent_audit_events(limit=30):
                self._events_tree.insert(
                    "",
                    "end",
                    values=(
                        _fmt_ts(ev.get("timestamp")),
                        ev.get("action", "—"),
                        ev.get("ticket_number") or "—",
                        ev.get("source_id") or "—",
                        ev.get("actor") or "—",
                    ),
                )

    def _schedule_refresh(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.after(REFRESH_INTERVAL * 1000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        if self._win and self._win.winfo_exists():
            self._refresh()
            self._schedule_refresh()

    def _run_once(self) -> None:
        project_root = self._root
        pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
        python = project_root / ".venv" / "Scripts" / "python.exe"
        exe = pythonw if pythonw.exists() else python
        main_py = project_root / "main.py"
        subprocess.Popen(
            [str(exe), str(main_py), "run-once"],
            cwd=str(project_root),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def _open_config_window(self) -> None:
        from .config_window import ConfigWindow  # noqa: PLC0415
        ConfigWindow(self._root).show()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return ts[:16] if ts else "—"


def _detect_task(task_name: str = TASK_NAME) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/fo", "LIST"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return False, "Not found"
        for line in result.stdout.splitlines():
            if line.strip().lower().startswith("status:"):
                state = line.split(":", 1)[1].strip()
                return True, state
        return True, "Unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, "Error"


# ---------------------------------------------------------------------------
# TrayApp — orquestrador principal
# ---------------------------------------------------------------------------
class TrayApp:
    def __init__(self, db_path: Path, project_root: Path) -> None:
        self._db = TrayDbReader(db_path)
        self._root = project_root
        self._icon: pystray.Icon | None = None
        self._window: StatusWindow | None = None
        self._running = True

    def run(self) -> None:
        import tkinter as tk

        # Tkinter DEVE rodar na thread principal — criar root oculto aqui
        self._tk_root = tk.Tk()
        self._tk_root.withdraw()

        menu = pystray.Menu(
            pystray.MenuItem("Ver Status", self._open_status, default=True),
            pystray.MenuItem("Configuração Completa", self._open_config),
            pystray.MenuItem("Executar Agora", self._run_once),
            pystray.MenuItem("Abrir Log", self._open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", self._quit),
        )

        last = self._db.get_last_success_at()
        color = IconFactory.color_for(last)
        self._icon = pystray.Icon(
            name="sdwa",
            icon=IconFactory.make(color),
            title=self._tooltip_text(),
            menu=menu,
        )

        # pystray em thread separada; thread principal fica para Tkinter
        icon_thread = threading.Thread(target=self._icon.run, daemon=True)
        icon_thread.start()
        self._start_icon_refresh()

        # mainloop do Tkinter na thread principal (mantém processo vivo)
        self._tk_root.mainloop()

    def _tooltip_text(self) -> str:
        last = self._db.get_last_success_at()
        if not last:
            return "SDWA — Sem execuções"
        return f"SDWA — Última execução: {_fmt_ts(last)}"

    def _start_icon_refresh(self) -> None:
        def _refresh_loop() -> None:
            while self._running:
                time.sleep(REFRESH_INTERVAL)
                if self._icon and self._running:
                    last = self._db.get_last_success_at()
                    self._icon.icon = IconFactory.make(IconFactory.color_for(last))
                    self._icon.title = self._tooltip_text()

        t = threading.Thread(target=_refresh_loop, daemon=True)
        t.start()

    def _open_status(self, icon=None, item=None) -> None:
        # Schedule na thread principal (Tkinter)
        self._tk_root.after(0, self._show_status)

    def _show_status(self) -> None:
        self._window = StatusWindow(self._db, self._root)
        self._window.show()

    def _open_config(self, icon=None, item=None) -> None:
        self._tk_root.after(0, self._show_config)

    def _show_config(self) -> None:
        from .config_window import ConfigWindow  # noqa: PLC0415
        ConfigWindow(self._root).show()

    def _run_once(self, icon=None, item=None) -> None:
        pythonw = self._root / ".venv" / "Scripts" / "pythonw.exe"
        python = self._root / ".venv" / "Scripts" / "python.exe"
        exe = pythonw if pythonw.exists() else python
        main_py = self._root / "main.py"
        subprocess.Popen(
            [str(exe), str(main_py), "run-once"],
            cwd=str(self._root),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def _open_log(self, icon=None, item=None) -> None:
        log = self._root / "data" / "logs" / "monitor.log"
        if log.exists():
            os.startfile(str(log))

    def _quit(self, icon=None, item=None) -> None:
        self._running = False
        if self._icon:
            self._icon.stop()
        self._tk_root.after(0, self._tk_root.destroy)


# ---------------------------------------------------------------------------
# Função de resolução do db_path (usada pelo cli.py)
# ---------------------------------------------------------------------------
def resolve_db_path(project_root: Path) -> Path:
    """Resolve o caminho do banco sem instanciar Settings completo."""
    env_path = project_root / ".env"
    env_vals = dotenv_values(str(env_path))
    raw = env_vals.get("DATABASE_PATH", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else project_root / p
    return project_root / "data" / "megahub-monitor.db"
