from datetime import datetime

from pydantic import BaseModel, Field


class BookingRequest(BaseModel):
    created_at: datetime = Field(default_factory=datetime.now)
    name: str
    phone: str
    email: str
    destination: str = ""
    budget: str = ""
    travelers: int = 1
    selected_tour: str = ""
    status: str = "Новая"
    source: str = "Instagram"
    tag: str = ""
