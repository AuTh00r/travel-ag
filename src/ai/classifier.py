import json

from langchain_core.messages import HumanMessage
from structlog import get_logger

from src.ai.prompts import CLASSIFICATION_PROMPT
from src.ai.states import DialogState
from src.services.llm import get_llm_json

logger = get_logger()


async def classify(state: DialogState) -> dict:
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    last_message = last_human.content if last_human else ""

    llm = get_llm_json()
    response = await llm.ainvoke(
        [HumanMessage(content=CLASSIFICATION_PROMPT.format(message=last_message))]
    )

    try:
        result = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("classify.json_parse_failed", raw=response.content)
        return {
            "request_type": "unknown",
            "needs_escalation": True,
            "escalation_reason": "Ошибка обработки ответа от классификатора",
        }

    return {
        "request_type": result["request_type"],
        "needs_escalation": result.get("needs_escalation", False),
        "escalation_reason": result.get("escalation_reason"),
    }
