import json

from langchain_core.messages import HumanMessage

from src.ai.prompts import CLASSIFICATION_PROMPT, build_context
from src.ai.states import DialogState
from src.services.llm import get_llm_json


async def classify(state: DialogState) -> dict:
    last_message = state["messages"][-1].content if state["messages"] else ""
    context = build_context(state["messages"])

    llm = get_llm_json()
    response = await llm.ainvoke(
        [
            HumanMessage(
                content=CLASSIFICATION_PROMPT.format(
                    message=last_message, context=context
                )
            )
        ]
    )

    result = json.loads(response.content)

    return {
        "request_type": result["request_type"],
        "needs_escalation": result.get("needs_escalation", False),
        "escalation_reason": result.get("escalation_reason"),
    }
