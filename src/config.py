from datetime import timedelta, timezone

from pydantic_settings import BaseSettings, SettingsConfigDict

MINSK_TZ = timezone(timedelta(hours=3))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # Instagram (Meta Graph API)
    instagram_app_secret: str = ""
    instagram_access_token: str = ""
    instagram_verify_token: str = ""
    instagram_page_id: str = ""
    instagram_ig_user_id: str = ""
    instagram_app_id: str = ""  # для распознавания собственных эхо (опционально)

    # Telegram Bot (уведомления менеджерам)
    telegram_bot_token: str = ""
    telegram_manager_chat_id: str = ""
    telegram_secondary_chat_id: str = ""
    telegram_tertiary_chat_id: str = ""

    # ChromaDB (RAG FAQ)
    chroma_db_dir: str = "data/chroma"

    # Security
    max_message_length: int = 1000
    max_messages_per_minute: int = 5

    # Токен для служебных /api/admin/* роутов. Они доступны из интернета через
    # Cloudflare Tunnel, а reset-takeover снимает паузу бота — то есть пишет
    # в сессию. Пока поле пустое, admin-роуты отдают 404: незаданный токен не
    # должен означать «пускать всех».
    admin_api_token: str = ""

    # Пауза бота при вмешательстве живого менеджера
    # Сколько бот молчит в чате после последней реплики менеджера. 10080 = 7 дней.
    manager_takeover_ttl_minutes: int = 10080

    # Сколько последних реплик диалога уходит в LLM. Без лимита история растёт
    # бессрочно: у постоянного клиента каждое сообщение тянет за собой всю
    # переписку за месяцы — это и деньги (input-токены), и латентность.
    # 50 реплик ≈ 25 обменов. Важно: кэш DeepSeek на историю НЕ работает —
    # как только диалог перевалил за лимит, окно съезжает на каждом сообщении
    # и меняет префикс после базы туров (замер 2026-09-29: cache hit падает
    # с 78% при 20 репликах до 59% при 50).
    max_history_messages: int = 50

    # Через сколько часов молчания сбрасывается счётчик эскалаций.
    # Без сброса клиент, которого трижды передали менеджеру в июле, в декабре
    # получит «ваш запрос уже передан, ожидайте» и к живому человеку не попадёт.
    # 720 = 30 дней.
    escalation_reset_hours: int = 720

    # Очередь недоставленных сообщений (pending_messages)
    default_retry_seconds: int = 60
    max_retry_attempts: int = 5
    pending_worker_interval_seconds: int = 30

    # Проактивный мониторинг Instagram usage
    instagram_usage_warn_pct: int = 85

    # Сколько ближайших дат заезда показывать по каждому туру. Раньше промпт
    # требовал перечислять ВСЕ будущие даты — у «Французского поцелуя» их 11,
    # ответ раздувался и рвался по max_tokens.
    max_tour_dates: int = 3

    # Синхронизация туров из Google Drive (см. .kiro/specs/tour-sync/).
    # Главный рубильник; пока выключено или не заданы folder_id/ключ —
    # воркер спит, бот работает по локальным tours/*.docx как раньше.
    tour_sync_enabled: bool = True
    tour_sync_folder_id: str = ""
    google_drive_api_key: str = ""
    # Интервал опроса папки. Опрос дешёвый; публикация в память — только
    # при изменении хэша, чтобы не инвалидировать кэш DeepSeek каждые N минут.
    tour_sync_interval_seconds: int = 300
    # Валидация перед публикацией: пустой результат не публикуется никогда;
    # ниже порога или просадка больше доли относительно текущей базы —
    # не публикуем, шлём алерт, остаётся last-good.
    tour_sync_min_tours: int = 1
    tour_sync_max_drop_ratio: float = 0.5
    # Персистентный last-good: переживает рестарт, когда Google недоступен.
    tour_sync_snapshot_path: str = "data/tours_snapshot.json"
    # Уведомления в Telegram: изменения цен/дат/ссылок/состава + ошибки.
    tour_sync_notify: bool = True
    # После скольких подряд провалов слать алерт (4xx — сразу, без счёта).
    tour_sync_alert_after_failures: int = 3

    # Настройки сервера
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
