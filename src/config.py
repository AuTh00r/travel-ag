from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Google Sheets
    google_sheets_credentials_file: str = "credentials.json"
    google_tours_sheet_id: str = ""
    google_requests_sheet_id: str = ""

    # Telegram Bot (уведомления менеджерам)
    telegram_bot_token: str = ""
    telegram_manager_chat_id: str = ""
    telegram_secondary_chat_id: str = ""
    telegram_tertiary_chat_id: str = ""

    # ChromaDB (RAG FAQ)
    chroma_db_dir: str = "data/chroma"

    # Ссылка на форму бронирования / оплаты
    booking_form_url: str = ""

    # Security
    max_message_length: int = 1000
    max_messages_per_minute: int = 5

    # Пауза бота при вмешательстве живого менеджера
    # Сколько бот молчит в чате после последней реплики менеджера. 10080 = 7 дней.
    manager_takeover_ttl_minutes: int = 10080

    # Настройки сервера
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
