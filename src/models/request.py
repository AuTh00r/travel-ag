from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

MINSK_TZ = timezone(timedelta(hours=3))


class BookingRequest(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(MINSK_TZ))
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
