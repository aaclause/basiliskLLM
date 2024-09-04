from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict

from .image_file import ImageFile
from .provider_ai_model import ProviderAIModel


class MessageRoleEnum(Enum):
	ASSISTANT = "assistant"
	USER = "user"
	SYSTEM = "system"


class Message(BaseModel):
	model_config = SettingsConfigDict(arbitrary_types_allowed=True)
	role: MessageRoleEnum
	content: list[ImageFile | str] | str = Field(default="")


class MessageBlock(BaseModel):
	request: Message
	response: Message | None = Field(default=None)
	model: ProviderAIModel
	temperature: float = Field(default=1)
	max_tokens: int = Field(default=4096)
	top_p: float = Field(default=1)
	stream: bool = Field(default=False)
	created_at: datetime = Field(default_factory=datetime.now)
	updated_at: datetime = Field(default_factory=datetime.now)


class Conversation(BaseModel):
	system: Message | None = Field(default=None)
	messages: list[MessageBlock] = Field(default_factory=list)


class RequestParams(Enum):
	MAX_TOKENS = "max_tokens"
	STREAM = "stream"
	TEMPERATURE = "temperature"
	TOP_P = "top_p"
