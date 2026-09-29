from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config import settings
from src.exceptions import LLMError


def get_llm() -> BaseChatModel:
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY не задан")

    # 2048, не 1024: промпт требует перечислить ВСЕ подходящие туры со ВСЕМИ
    # датами, а на каждый тур обязательны две ссылки (тур + бронирование).
    # Замер 2026-09-29: ~146 токенов на тур, подборка по 8 турам с контактной
    # строкой ≈ 1200 токенов — в 1024 не влезала, и модель обрывала ответ на
    # полуслове. Терялся как раз хвост: последние туры и обязательная
    # контактная строка. _split_reply такое не спасает — он делит уже
    # полученный текст, а здесь генерация останавливалась на середине.
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.7,
        max_tokens=2048,
        timeout=120,
    )


def get_llm_json() -> BaseChatModel:
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY не задан")

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.1,
        max_tokens=2048,
        timeout=120,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
