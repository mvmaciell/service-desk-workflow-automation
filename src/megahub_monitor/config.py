from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigurationError


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def _resolve_path(project_root: Path, raw_value: str | None, default_relative: str) -> Path:
    chosen = raw_value.strip() if raw_value and raw_value.strip() else default_relative
    path = Path(chosen)
    if not path.is_absolute():
        path = project_root / path
    return path


def _resolve_existing_path(
    project_root: Path,
    raw_value: str | None,
    default_relative: str,
    fallback_relative: str | None = None,
) -> Path:
    if raw_value and raw_value.strip():
        return _resolve_path(project_root, raw_value, default_relative)

    preferred = project_root / default_relative
    if preferred.exists():
        return preferred

    if fallback_relative:
        fallback = project_root / fallback_relative
        if fallback.exists():
            return fallback

    return preferred


def _normalize_filter_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [value.strip().lower() for value in values if value and value.strip()]


@dataclass(slots=True)
class BrowserContextConfig:
    id: str
    name: str
    profile_dir: Path
    enabled: bool = True


@dataclass(slots=True)
class SourceConfig:
    id: str
    name: str
    kind: str
    context_id: str
    url: str
    enabled: bool = True
    first_page_only: bool = True
    consultant_name: str = ""
    only_open: bool = True
    only_assigned_to_me: bool = True
    include_closed: bool = False
    include_assigned: bool = True


@dataclass(slots=True)
class NotificationProfileConfig:
    id: str
    name: str
    role: str
    webhook_url: str
    enabled: bool = True


@dataclass(slots=True)
class SubscriptionConfig:
    id: str
    name: str
    source_ids: list[str]
    profile_ids: list[str]
    title_prefix: str
    enabled: bool = True
    include_load: bool = False
    ticket_types: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    consultants: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Settings:
    project_root: Path
    monitor_interval_seconds: int
    browser_headless: bool
    playwright_channel: str | None
    playwright_timeout_ms: int
    database_path: Path
    log_file_path: Path
    lock_file_path: Path
    contexts_path: Path
    profiles_path: Path
    teams_request_timeout_seconds: int
    contexts: dict[str, BrowserContextConfig]
    sources: dict[str, SourceConfig]
    profiles: dict[str, NotificationProfileConfig]
    subscriptions: list[SubscriptionConfig]
    # Team catalog & allocation (all optional — fallback when teams.toml absent)
    teams_path: Path = field(default_factory=lambda: Path("config/teams.toml"))
    allocation_enabled: bool = False
    novo_status_labels: list[str] = field(default_factory=lambda: ["NOVO"])
    completion_status_labels: list[str] = field(default_factory=lambda: ["Fechado", "Resolvido"])
    return_to_developer_labels: list[str] = field(default_factory=lambda: ["Em Processamento"])
    approval_timeout_minutes: int = 60

    @classmethod
    def load(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[2]
        load_dotenv(project_root / ".env", override=False)

        contexts_path = _resolve_existing_path(
            project_root,
            os.getenv("CONTEXTS_CONFIG_PATH"),
            "config/local/contexts.toml",
            "config/contexts.toml",
        )
        profiles_env = os.getenv("PROFILES_CONFIG_PATH") or os.getenv("ROUTING_CONFIG_PATH")
        profiles_path = _resolve_existing_path(
            project_root,
            profiles_env,
            "config/local/profiles.toml",
            "config/routing.toml",
        )
        contexts, sources = cls._load_contexts(project_root, contexts_path)
        profiles, subscriptions = cls._load_profiles(profiles_path)
        teams_path = _resolve_existing_path(
            project_root,
            os.getenv("TEAMS_CONFIG_PATH"),
            "config/local/teams.toml",
            "config/teams.toml",
        )
        alloc = cls._load_teams_config(teams_path)

        channel = os.getenv("PLAYWRIGHT_CHANNEL", "msedge").strip()
        settings = cls(
            project_root=project_root,
            monitor_interval_seconds=_to_int(os.getenv("MONITOR_INTERVAL_SECONDS"), 120),
            browser_headless=_to_bool(os.getenv("BROWSER_HEADLESS"), True),
            playwright_channel=channel or None,
            playwright_timeout_ms=_to_int(os.getenv("PLAYWRIGHT_TIMEOUT_MS"), 30000),
            database_path=_resolve_path(project_root, os.getenv("DATABASE_PATH"), "data/megahub-monitor.db"),
            log_file_path=_resolve_path(project_root, os.getenv("LOG_FILE_PATH"), "data/logs/monitor.log"),
            lock_file_path=_resolve_path(project_root, os.getenv("LOCK_FILE_PATH"), "data/megahub-monitor.lock"),
            contexts_path=contexts_path,
            profiles_path=profiles_path,
            teams_request_timeout_seconds=_to_int(os.getenv("TEAMS_REQUEST_TIMEOUT_SECONDS"), 15),
            contexts=contexts,
            sources=sources,
            profiles=profiles,
            subscriptions=subscriptions,
            teams_path=teams_path,
            allocation_enabled=alloc["enabled"],
            novo_status_labels=alloc["novo_status_labels"],
            completion_status_labels=alloc["completion_status_labels"],
            return_to_developer_labels=alloc["return_to_developer_labels"],
            approval_timeout_minutes=alloc["approval_timeout_minutes"],
        )
        settings.ensure_directories()
        settings.validate()
        return settings

    @staticmethod
    def _load_contexts(
        project_root: Path,
        contexts_path: Path,
    ) -> tuple[dict[str, BrowserContextConfig], dict[str, SourceConfig]]:
        if not contexts_path.exists():
            raise ConfigurationError(f"Arquivo de contextos nao encontrado: {contexts_path}")

        with contexts_path.open("rb") as handle:
            document = tomllib.load(handle)

        contexts: dict[str, BrowserContextConfig] = {}
        for raw in document.get("contexts", []):
            context_id = str(raw["id"]).strip()
            if context_id in contexts:
                raise ConfigurationError(f"Contexto duplicado no arquivo de configuracao: {context_id}")

            profile_dir = _resolve_path(project_root, raw.get("profile_dir"), f"data/browser-profile/{context_id}")
            contexts[context_id] = BrowserContextConfig(
                id=context_id,
                name=str(raw.get("name", context_id)).strip(),
                enabled=bool(raw.get("enabled", True)),
                profile_dir=profile_dir,
            )

        sources: dict[str, SourceConfig] = {}
        for raw in document.get("sources", []):
            source_id = str(raw["id"]).strip()
            if source_id in sources:
                raise ConfigurationError(f"Fonte duplicada no arquivo de configuracao: {source_id}")

            context_id = str(raw["context_id"]).strip()
            if context_id not in contexts:
                raise ConfigurationError(f"Fonte '{source_id}' referencia contexto inexistente: {context_id}")

            kind = str(raw["kind"]).strip().lower()
            sources[source_id] = SourceConfig(
                id=source_id,
                name=str(raw.get("name", source_id)).strip(),
                kind=kind,
                context_id=context_id,
                url=str(raw["url"]).strip(),
                enabled=bool(raw.get("enabled", True)),
                first_page_only=bool(raw.get("first_page_only", True)),
                consultant_name=str(raw.get("consultant_name", "")).strip(),
                only_open=bool(raw.get("only_open", True)),
                only_assigned_to_me=bool(raw.get("only_assigned_to_me", True)),
                include_closed=bool(raw.get("include_closed", False)),
                include_assigned=bool(raw.get("include_assigned", True)),
            )

        return contexts, sources

    @staticmethod
    def _load_profiles(
        profiles_path: Path,
    ) -> tuple[dict[str, NotificationProfileConfig], list[SubscriptionConfig]]:
        if not profiles_path.exists():
            raise ConfigurationError(f"Arquivo de perfis nao encontrado: {profiles_path}")

        with profiles_path.open("rb") as handle:
            document = tomllib.load(handle)

        profiles: dict[str, NotificationProfileConfig] = {}
        raw_profiles = document.get("profiles", document.get("recipients", []))
        for raw in raw_profiles:
            profile_id = str(raw["id"]).strip()
            if profile_id in profiles:
                raise ConfigurationError(f"Perfil duplicado no arquivo de configuracao: {profile_id}")

            webhook_env = str(raw.get("webhook_env", "")).strip()
            webhook_url = str(raw.get("webhook_url", "")).strip()
            if webhook_env:
                webhook_url = os.getenv(webhook_env, "").strip() or webhook_url

            profiles[profile_id] = NotificationProfileConfig(
                id=profile_id,
                name=str(raw.get("name", profile_id)).strip(),
                role=str(raw.get("role", "recipient")).strip(),
                enabled=bool(raw.get("enabled", True)),
                webhook_url=webhook_url,
            )

        subscriptions: list[SubscriptionConfig] = []
        raw_subscriptions = document.get("subscriptions", document.get("rules", []))
        for raw in raw_subscriptions:
            subscription = SubscriptionConfig(
                id=str(raw["id"]).strip(),
                name=str(raw.get("name", raw["id"])).strip(),
                enabled=bool(raw.get("enabled", True)),
                source_ids=[str(item).strip() for item in raw.get("source_ids", [])],
                profile_ids=[
                    str(item).strip()
                    for item in raw.get("profile_ids", raw.get("recipient_ids", []))
                ],
                title_prefix=str(raw.get("title_prefix", "Novo chamado detectado")).strip(),
                include_load=bool(raw.get("include_load", False)),
                ticket_types=_normalize_filter_values(raw.get("ticket_types")),
                priorities=_normalize_filter_values(raw.get("priorities")),
                companies=_normalize_filter_values(raw.get("companies")),
                consultants=_normalize_filter_values(raw.get("consultants")),
            )
            subscriptions.append(subscription)

        return profiles, subscriptions

    @staticmethod
    def _load_teams_config(teams_path: Path) -> dict:
        """Load allocation settings from teams.toml. Returns safe defaults if file absent."""
        defaults: dict = {
            "enabled": False,
            "novo_status_labels": ["NOVO"],
            "completion_status_labels": ["Fechado", "Resolvido"],
            "return_to_developer_labels": ["Em Processamento"],
            "approval_timeout_minutes": 60,
        }
        if not teams_path.exists():
            return defaults
        with teams_path.open("rb") as fh:
            document = tomllib.load(fh)
        alloc = document.get("allocation", {})
        return {
            "enabled": bool(alloc.get("enabled", defaults["enabled"])),
            "novo_status_labels": [
                str(v).strip()
                for v in alloc.get("novo_status_labels", defaults["novo_status_labels"])
                if str(v).strip()
            ],
            "completion_status_labels": [
                str(v).strip()
                for v in alloc.get("completion_status_labels", defaults["completion_status_labels"])
                if str(v).strip()
            ],
            "return_to_developer_labels": [
                str(v).strip()
                for v in alloc.get("return_to_developer_labels", defaults["return_to_developer_labels"])
                if str(v).strip()
            ],
            "approval_timeout_minutes": int(
                alloc.get("approval_timeout_minutes", defaults["approval_timeout_minutes"])
            ),
        }

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        for context in self.contexts.values():
            context.profile_dir.mkdir(parents=True, exist_ok=True)

    def validate(self) -> None:
        if not self.sources:
            raise ConfigurationError("Nenhuma fonte foi configurada em contexts.toml.")
        if not self.profiles:
            raise ConfigurationError("Nenhum perfil foi configurado em profiles.toml.")
        if not self.subscriptions:
            raise ConfigurationError("Nenhuma subscricao foi configurada em profiles.toml.")

        valid_source_ids = set(self.sources)
        valid_profile_ids = set(self.profiles)
        valid_context_ids = set(self.contexts)
        valid_kinds = {"minha_fila", "fila"}

        for source in self.sources.values():
            if source.kind not in valid_kinds:
                raise ConfigurationError(f"Fonte '{source.id}' possui tipo invalido: {source.kind}")
            if source.context_id not in valid_context_ids:
                raise ConfigurationError(f"Fonte '{source.id}' referencia contexto inexistente: {source.context_id}")
            if source.enabled and not self.contexts[source.context_id].enabled:
                raise ConfigurationError(
                    f"Fonte habilitada '{source.id}' usa contexto desabilitado: {source.context_id}"
                )

        for subscription in self.subscriptions:
            missing_sources = [
                source_id
                for source_id in subscription.source_ids
                if source_id not in valid_source_ids
            ]
            if missing_sources:
                raise ConfigurationError(
                    f"Subscricao '{subscription.id}' referencia fonte(s) inexistente(s): {', '.join(missing_sources)}"
                )

            missing_profiles = [
                profile_id
                for profile_id in subscription.profile_ids
                if profile_id not in valid_profile_ids
            ]
            if missing_profiles:
                raise ConfigurationError(
                    f"Subscricao '{subscription.id}' referencia perfil(is) "
                    f"inexistente(s): {', '.join(missing_profiles)}"
                )

    def enabled_sources(self) -> list[SourceConfig]:
        return [source for source in self.sources.values() if source.enabled]

    def get_context(self, context_id: str) -> BrowserContextConfig:
        try:
            return self.contexts[context_id]
        except KeyError as exc:
            raise ConfigurationError(f"Contexto nao encontrado: {context_id}") from exc

    def get_source(self, source_id: str) -> SourceConfig:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise ConfigurationError(f"Fonte nao encontrada: {source_id}") from exc

    def get_profile(self, profile_id: str) -> NotificationProfileConfig:
        try:
            return self.profiles[profile_id]
        except KeyError as exc:
            raise ConfigurationError(f"Perfil nao encontrado: {profile_id}") from exc
