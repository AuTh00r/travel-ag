class TravelBotError(Exception):
    """Базовое исключение приложения."""


class ConfigError(TravelBotError):
    """Ошибка конфигурации."""


class InstagramError(TravelBotError):
    """Ошибка взаимодействия с Instagram API."""

    def __init__(self, message, *, delivery_status="blocked", retry_after_seconds=None):
        super().__init__(message)
        self.delivery_status = delivery_status
        self.retry_after_seconds = retry_after_seconds


class InstagramRateLimitError(InstagramError):
    """Meta сигнализирует rate-limit (код 4/17/32/613/80002 внутри тела ответа).

    Throttling у Graph API не всегда отдаётся отдельным HTTP-статусом — код
    ошибки может прийти в JSON-теле при формально успешном HTTP 200.

    retry_after_seconds — оценка времени до снятия троттлинга (переведено из
    `estimated_time_to_regain_access`, если Meta прислала заголовок
    X-Business-Use-Case-Usage). None, если заголовка не было или он не
    распарсился — тогда решение о повторной попытке остаётся за вызывающим
    кодом.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds


class LLMError(TravelBotError):
    """Ошибка взаимодействия с LLM API."""


class ProviderResponseError(LLMError):
    """Invalid provider envelope, without retaining its content."""

    def __init__(self, reason: str, response: object) -> None:
        self.reason = reason
        self.response_type = type(response).__name__[:64]
        super().__init__(reason)


class StoryMediaError(TravelBotError):
    """Безопасный код ошибки медиа, без URL, токена или ответа провайдера."""


class TelegramError(TravelBotError):
    """Ошибка взаимодействия с Telegram Bot API."""

    def __init__(self, message, *, delivery_status="unknown", retry_after_seconds=None):
        super().__init__(message)
        self.delivery_status = delivery_status
        self.retry_after_seconds = retry_after_seconds


class VoiceMediaError(TravelBotError):
    """Безопасный код ошибки голосового, без ссылки или текста клиента."""
