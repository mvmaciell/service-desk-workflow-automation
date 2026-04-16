"""Helpers compartilhados para leitura e escrita de arquivos TOML.

Usado por config_window.py e setup_wizard.py.
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# TOML writer minimo (sem dependencia de tomli_w)
# ---------------------------------------------------------------------------

def toml_scalar(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def toml_list(items: list) -> str:
    return "[" + ", ".join(toml_scalar(v) for v in items) + "]"


def write_toml(data: dict, comment_header: str = "") -> str:
    """Serializa um dict em TOML basico — suporta os padroes usados nos configs."""
    lines: list[str] = []
    if comment_header:
        for line in comment_header.splitlines():
            lines.append(f"# {line}" if line.strip() else "#")
        lines.append("")

    # 1. Escalares no topo
    for key, val in data.items():
        if not isinstance(val, (dict, list)) or (isinstance(val, list) and (not val or not isinstance(val[0], dict))):
            if isinstance(val, list):
                lines.append(f"{key} = {toml_list(val)}")
            else:
                lines.append(f"{key} = {toml_scalar(val)}")

    # 2. [[array of tables]]
    for key, val in data.items():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            for item in val:
                lines.append("")
                lines.append(f"[[{key}]]")
                for k, v in item.items():
                    if isinstance(v, list):
                        lines.append(f"{k} = {toml_list(v)}")
                    elif not isinstance(v, dict):
                        lines.append(f"{k} = {toml_scalar(v)}")

    # 3. [section]
    for key, val in data.items():
        if isinstance(val, dict):
            lines.append("")
            lines.append(f"[{key}]")
            for k, v in val.items():
                if isinstance(v, list):
                    lines.append(f"{k} = {toml_list(v)}")
                elif not isinstance(v, dict):
                    lines.append(f"{k} = {toml_scalar(v)}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Helpers de localizacao de arquivos
# ---------------------------------------------------------------------------

def find_config(project_root: Path, local: str, base: str) -> Path:
    local_path = project_root / local
    if local_path.exists():
        return local_path
    return project_root / base


def load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def save_toml(path: Path, data: dict, header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(write_toml(data, header), encoding="utf-8")
