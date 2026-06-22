from abc import ABC, abstractmethod


class ChannelBase(ABC):
    """Абстрактный интерфейс канала связи."""

    @abstractmethod
    async def send_message(self, recipient_id: str, text: str) -> None:
        """Отправить сообщение клиенту."""

    ...

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> list[tuple[str, str]]:
        """Обработать входящий webhook.

        Возвращает список (sender_id, text) для каждого сообщения.
        """

    ...
