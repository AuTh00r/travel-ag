from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config import settings
from src.exceptions import LLMError


def get_llm() -> BaseChatModel:
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY не задан")

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1",
        temperature=0.7,
        max_tokens=1024,
    )


def get_llm_json() -> BaseChatModel:
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY не задан")

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1",
        temperature=0.1,
        max_tokens=2048,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
