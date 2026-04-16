from __future__ import annotations

from ..adapters.itsm.megahub.collector_fila import FilaCollector
from ..adapters.itsm.megahub.collector_minha_fila import MinhaFilaCollector
from ..config import Settings, SourceConfig


def build_collector(settings: Settings, source: SourceConfig, logger):
    if source.kind == "minha_fila":
        return MinhaFilaCollector(settings, source, logger)
    if source.kind == "fila":
        return FilaCollector(settings, source, logger)
    raise ValueError(f"Tipo de fonte nao suportado: {source.kind}")


__all__ = ["FilaCollector", "MinhaFilaCollector", "build_collector"]
