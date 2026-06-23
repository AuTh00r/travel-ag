from langgraph.graph import END, START, StateGraph

from src.ai.faq import faq_search
from src.ai.nodes import (
    book,
    clarify,
    classify_node,
    escalate,
    greet,
    handle_tour_selection,
    present_tours,
    search_tours_node,
)
from src.ai.states import DialogState

_BOOKING_STEPS = {"AWAIT_NAME", "AWAIT_PHONE", "AWAIT_EMAIL", "CONFIRM"}


def route_from_start(state: DialogState) -> str:
    cs = state.get("current_step")
    if cs in _BOOKING_STEPS:
        return "book"
    if cs == "awaiting_selection":
        return "handle_tour_selection"
    if state.get("messages"):
        return "classify"
    return "greeting"


def route_by_request_type(state: DialogState) -> str:
    request_type = state.get("request_type", "unknown")
    return request_type


def route_after_presentation(state: DialogState) -> str:
    if state.get("needs_escalation"):
        return "escalate"
    return "handle_tour_selection"


def route_after_selection(state: DialogState) -> str:
    cs = state.get("current_step")
    if cs == "ASK_NAME" or state.get("selected_tour"):
        return "book"
    if cs == "clarify":
        return "clarify"
    if state.get("needs_escalation"):
        return "escalate"
    return "end"


def route_after_faq(state: DialogState) -> str:
    if state.get("needs_escalation"):
        return "escalate"
    return "end"


def build_graph() -> StateGraph:
    graph = StateGraph(DialogState)

    graph.add_node("greeting", greet)
    graph.add_node("classify", classify_node)
    graph.add_node("clarify", clarify)
    graph.add_node("search_tours", search_tours_node)
    graph.add_node("present_tours", present_tours)
    graph.add_node("handle_tour_selection", handle_tour_selection)
    graph.add_node("book", book)
    graph.add_node("faq_search", faq_search)
    graph.add_node("escalate", escalate)

    graph.add_conditional_edges(
        START,
        route_from_start,
        {
            "greeting": "greeting",
            "book": "book",
            "handle_tour_selection": "handle_tour_selection",
            "classify": "classify",
        },
    )

    graph.add_edge("greeting", "classify")

    graph.add_conditional_edges(
        "classify",
        route_by_request_type,
        {
            "tour_search": "clarify",
            "faq": "faq_search",
            "complaint": "escalate",
            "talk_to_manager": "escalate",
            "booking": "book",
            "greeting": "clarify",
            "unknown": "clarify",
        },
    )

    graph.add_conditional_edges(
        "clarify",
        lambda s: "search" if s.get("current_step") == "search" else "ask",
        {"search": "search_tours", "ask": END},
    )

    graph.add_edge("search_tours", "present_tours")

    graph.add_conditional_edges(
        "present_tours",
        route_after_presentation,
        {"escalate": "escalate", "handle_tour_selection": "handle_tour_selection"},
    )

    graph.add_conditional_edges(
        "handle_tour_selection",
        route_after_selection,
        {"book": "book", "clarify": "clarify", "escalate": "escalate", "end": END},
    )

    graph.add_conditional_edges(
        "faq_search",
        route_after_faq,
        {"escalate": "escalate", "end": END},
    )

    graph.add_edge("book", END)
    graph.add_edge("escalate", END)

    return graph.compile()
