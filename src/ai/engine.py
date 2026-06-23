from langgraph.graph import END, START, StateGraph

from src.ai.faq import faq_search
from src.ai.nodes import (
    book,
    converse,
    escalate,
    present_tours,
    search_tours_node,
)
from src.ai.states import DialogState

_BOOKING_STEPS = {"AWAIT_NAME", "AWAIT_PHONE", "AWAIT_EMAIL", "CONFIRM"}


def route_from_start(state: DialogState) -> str:
    cs = state.get("current_step")
    if cs in _BOOKING_STEPS:
        return "book"
    return "converse"


def route_after_converse(state: DialogState) -> str:
    action = state.get("next_action", "respond")
    return action


def route_after_search(state: DialogState) -> str:
    if state.get("needs_escalation"):
        return "escalate"
    return "present_tours"


def route_after_presentation(state: DialogState) -> str:
    if state.get("needs_escalation"):
        return "escalate"
    return END


def route_after_faq(state: DialogState) -> str:
    if state.get("needs_escalation"):
        return "escalate"
    return END


def build_graph() -> StateGraph:
    graph = StateGraph(DialogState)

    graph.add_node("converse", converse)
    graph.add_node("search_tours", search_tours_node)
    graph.add_node("present_tours", present_tours)
    graph.add_node("book", book)
    graph.add_node("faq_search", faq_search)
    graph.add_node("escalate", escalate)

    graph.add_conditional_edges(
        START,
        route_from_start,
        {
            "converse": "converse",
            "book": "book",
        },
    )

    graph.add_conditional_edges(
        "converse",
        route_after_converse,
        {
            "respond": END,
            "search": "search_tours",
            "book": "book",
            "escalate": "escalate",
            "faq": "faq_search",
        },
    )

    graph.add_conditional_edges(
        "search_tours",
        route_after_search,
        {"present_tours": "present_tours", "escalate": "escalate"},
    )

    graph.add_conditional_edges(
        "present_tours",
        route_after_presentation,
        {"escalate": "escalate", END: END},
    )

    graph.add_conditional_edges(
        "faq_search",
        route_after_faq,
        {"escalate": "escalate", END: END},
    )

    graph.add_edge("book", END)
    graph.add_edge("escalate", END)

    return graph.compile()
