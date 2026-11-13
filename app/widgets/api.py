"""Small compatibility layer until aiogram supports Bot API 10.4 natively."""

from aiogram.methods.base import TelegramMethod
from aiogram.types import Chat, Message, TelegramObject, User
from pydantic import Field


class SendWidget(TelegramMethod[Message]):
    __api_method__ = "sendWidget"
    __returning__ = Message
    chat_id: int
    html: str
    chat_data: str
    public_data: str
    allow_queries: bool = True
    caption: str = "Расписание ФГУ"


class EditMessageWidgetData(TelegramMethod[bool]):
    __api_method__ = "editMessageWidgetData"
    __returning__ = bool
    chat_id: int
    message_id: int
    chat_data: str
    public_data: str


class AnswerWidgetQuery(TelegramMethod[bool]):
    __api_method__ = "answerWidgetQuery"
    __returning__ = bool
    widget_query_id: str
    data: str | None = None


class WidgetQuery(TelegramObject):
    id: str
    from_user: User = Field(alias="from")
    chat: Chat
    message_id: int
    data: str
