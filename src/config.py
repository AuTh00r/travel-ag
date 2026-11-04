from datetime import timedelta, timezone
from typing import Literal

from pydantic import model_validator

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
    deepseek_vision_model: str = "deepseek-flash"
    story_media_enabled: bool = False
    image_media_enabled: bool = False
    shared_media_enabled: bool = False
    ads_media_enabled: bool = False
    instagram_ads_account_id: str = ""
    instagram_ads_account_ids: str = ""  # Дополнительные явно разрешённые кабинеты, CSV.
    instagram_ads_token_file: str = ""  # Отдельный приватный файл; не PAGE messaging token.
    voice_media_enabled: bool = False
    voice_python_executable: str = ""
    voice_model_dir: str = ""

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
    # Дополнительный чат для уведомлений (новый менеджер и т.п.).
    telegram_extra_chat_id: str = ""

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

    # One bounded verification call for a proposed consultation, before any send.
    manager_review_enabled: bool = True
    manager_review_timeout_seconds: float = 25

    # Очередь недоставленных сообщений (pending_messages)
    default_retry_seconds: int = 60
    max_retry_attempts: int = 5
    pending_worker_interval_seconds: int = 30

    # Durable inbound recovery. Separate API switch; both are off for rollout.
    inbound_recovery_enabled: bool = False
    inbound_recovery_scope: Literal["allowlist", "all"] = "allowlist"
    inbound_recovery_client_ids: str = ""
    # Independent model transport canary; empty means installed JSON for everyone.
    deepseek_tool_client_ids: str = ""
    deepseek_tool_scope: Literal['allowlist', 'all'] = 'allowlist'
    instagram_reconcile_enabled: bool = False
    inbound_watchdog_seconds: int = 60
    inbound_retry_first_seconds: int = 120
    inbound_retry_second_seconds: int = 480
    inbound_semantic_recheck_seconds: int = 120
    inbound_lease_seconds: int = 180
    inbound_heartbeat_seconds: int = 15
    instagram_reconcile_interval_seconds: int = 120
    instagram_reconcile_timeout_seconds: int = 15
    instagram_reconcile_deadline_seconds: int = 90
    instagram_reconcile_max_requests: int = 100

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
    # Файл ключа сервисного аккаунта (приоритетнее API-ключа). Лежит только
    # на сервере, в репозиторий не попадает (см. .gitignore: credentials/).
    google_drive_credentials_file: str = ""
    # Явные связки «имя документа = URL брони» для случаев, где совпадением
    # по имени не обойтись («Эльбрус 2027» vs «Горнолыжный отдых на Эльбрусе»).
    # Значение — сразу URL: seed для подхвата может быть собран из снапшота
    # (имена из папки), а не из DOCX-базы, и привязка к имени базы тогда
    # отравляет прямое совпадение (прод-кейс 2026-10-04).
    # Формат: "Имя в папке=https://...;...".
    tour_sync_name_aliases: str = ""
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
    deepseek_response_log_enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    def recovery_allows(self, client_id: str) -> bool:
        if self.inbound_recovery_scope == "all":
            return True
        return str(client_id) in self.recovery_clients()

    def recovery_clients(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(part.strip() for part in self.inbound_recovery_client_ids.split(",") if part.strip()))

    @model_validator(mode="after")
    def validate_tool_scope(self):
        if self.deepseek_tool_client_ids.strip():
            parts = self.deepseek_tool_client_ids.split(',')
            if any(not part.strip().isascii() or not part.strip().isdigit()
                   or len(part.strip()) > 128 or int(part.strip()) == 0 for part in parts):
                raise ValueError('Tool canary requires numeric Instagram client IDs')
        return self

    def tool_clients(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(part.strip() for part in self.deepseek_tool_client_ids.split(',') if part.strip()))

    @model_validator(mode="after")
    def validate_recovery_scope(self):
        if self.inbound_recovery_enabled and self.inbound_recovery_scope == "allowlist":
            parts = self.inbound_recovery_client_ids.split(",")
            if not parts or any(not part.strip().isascii() or not part.strip().isdigit()
                                or len(part.strip()) > 128 for part in parts):
                raise ValueError("Enabled recovery allowlist requires numeric Instagram client IDs")
        return self


settings = Settings()
