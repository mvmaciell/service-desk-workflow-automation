class MonitorError(Exception):
    """Erro base do monitor."""


class ConfigurationError(MonitorError):
    """Configuracao obrigatoria ausente ou invalida."""


class AuthenticationRequiredError(MonitorError):
    """Sessao expirada ou autenticacao nao disponivel no perfil salvo."""


class CollectionError(MonitorError):
    """Falha ao capturar a grade da fila."""


class NotificationError(MonitorError):
    """Falha ao enviar notificacao."""


class LockUnavailableError(MonitorError):
    """Execucao concorrente detectada."""


class InvalidStateTransitionError(MonitorError):
    """Transicao de estado invalida no workflow."""
