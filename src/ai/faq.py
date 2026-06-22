from langchain_core.messages import AIMessage, HumanMessage

from src.ai.prompts import FAQ_PROMPT
from src.ai.states import DialogState
from src.db.faq_db import search_faq
from src.services.llm import get_llm


async def faq_search(state: DialogState) -> dict:
    last_message = state["messages"][-1].content if state["messages"] else ""

    relevant_entries = await search_faq(last_message)

    if relevant_entries:
        faq_context = "\n\n".join(f"---\n{e['document']}" for e in relevant_entries)
    else:
        faq_context = "(Релевантные записи не найдены)"

    llm = get_llm()
    response = await llm.ainvoke(
        [
            HumanMessage(
                content=FAQ_PROMPT.format(
                    faq_context=faq_context, question=last_message
                )
            )
        ]
    )

    result: dict = {
        "faq_answer": response.content,
        "messages": [AIMessage(content=response.content)],
    }

    if not relevant_entries:
        result["needs_escalation"] = True
        result["escalation_reason"] = "FAQ: нет релевантного ответа в базе знаний"

    return result
