from abc import ABC, abstractmethod


class ChannelBase(ABC):
    """Абстрактный интерфейс канала связи."""

    @abstractmethod
    async def send_message(self, recipient_id: str, text: str) -> None:
        """Отправить сообщение клиенту."""

    ...

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> list[dict]:
        """Обработать входящий webhook.

        Возвращает список событий-словарей для каждого сообщения.
        """

    ...
