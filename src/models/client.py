from pydantic import BaseModel


class Client(BaseModel):
    client_id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None
