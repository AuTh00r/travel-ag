from pydantic import BaseModel, Field


class Tour(BaseModel):
    title: str = Field(alias="Название")
    destination: str = Field(alias="Направление")
    tour_type: str = Field(alias="Тип")
    dates: str = Field(alias="Даты")
    price: str = Field(alias="Цена")
    duration: str = Field(alias="Длительность")
    keywords: str = Field(alias="Ключевые слова")
    link: str = Field(alias="Ссылка")
    available: str = Field(alias="Доступно")
