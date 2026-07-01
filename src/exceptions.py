class TravelBotError(Exception):
    """Базовое исключение приложения."""


class ConfigError(TravelBotError):
    """Ошибка конфигурации."""


class InstagramError(TravelBotError):
    """Ошибка взаимодействия с Instagram API."""


class LLMError(TravelBotError):
    """Ошибка взаимодействия с LLM API."""


class TelegramError(TravelBotError):
    """Ошибка взаимодействия с Telegram Bot API."""
