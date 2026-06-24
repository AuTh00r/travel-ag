import re
import time
from collections import defaultdict

from structlog import get_logger

from src.config import settings

logger = get_logger()

INJECTION_PATTERNS = [
    r"ignore (all |previous |prior |your |all previous |all prior )?(instructions|rules|prompt)",
    r"forget (everything|all|your instructions)",
    r"you are now",
    r"pretend (you are|to be|you're)",
    r"act as (if you are|a|an)",
    r"new (instructions|rules|persona|role|system prompt)",
    r"jailbreak",
    r"dan mode",
    r"developer mode",
    r"без ограничений",
    r"забудь (все|свои|предыдущие)",
    r"ты теперь",
    r"притворись что ты",
    r"сыграй роль",
    r"system prompt",
    r"покажи (свои )?инструкции",
]

_INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

OUTPUT_RED_FLAGS = [
    r"я языковая модель",
    r"я ии",
    r"я искусственный интеллект",
    r"как chatgpt",
    r"openai",
    r"anthropic",
    r"ignore (all |previous |all previous )?instructions",
]

_OUTPUT_RED_FLAGS_REGEX = re.compile("|".join(OUTPUT_RED_FLAGS), re.IGNORECASE)

FALLBACK_RESPONSE = "Я могу помочь только с вопросами о наших турах 😊 Напишите что вас интересует!"

_user_timestamps: dict[str, list[float]] = defaultdict(list)


def check_input(text: str) -> tuple[bool, str]:
    if len(text) > settings.max_message_length:
        return False, "too_long"

    if not text.strip():
        return False, "empty"

    if _INJECTION_REGEX.search(text):
        return False, "injection"

    return True, ""


def check_output(text: str) -> str:
    if _OUTPUT_RED_FLAGS_REGEX.search(text):
        logger.warning("guard.output_red_flag_detected")
        return FALLBACK_RESPONSE
    return text


def is_rate_limited(user_id: str) -> bool:
    now = time.time()
    minute_ago = now - 60

    _user_timestamps[user_id] = [
        t for t in _user_timestamps[user_id] if t > minute_ago
    ]

    if len(_user_timestamps[user_id]) >= settings.max_messages_per_minute:
        return True

    _user_timestamps[user_id].append(now)
    return False
