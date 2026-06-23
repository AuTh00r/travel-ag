from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class TourParams(TypedDict, total=False):
    destination: str
    dates: str
    budget: str
    travelers: int
    tour_type: str


class DialogState(TypedDict):
    messages: Annotated[list, add_messages]
    client_id: str
    client_name: str | None
    client_phone: str | None
    client_email: str | None
    request_type: (
        Literal[
            "tour_search",
            "faq",
            "complaint",
            "talk_to_manager",
            "booking",
            "greeting",
            "unknown",
        ]
        | None
    )
    tour_params: TourParams
    found_tours: list[dict]
    selected_tour: str | None
    faq_answer: str | None
    needs_escalation: bool
    escalation_reason: str | None
    current_step: str
    awaiting_field: str | None
    conversation_history: list[dict]
    next_action: str | None
