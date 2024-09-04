from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Union

import ollama

from basilisk.conversation import (
	Conversation,
	Message,
	MessageBlock,
	MessageRoleEnum,
	RequestParams,
)
from basilisk.image_file import ImageFile, ImageFileTypes

from .base_engine import BaseEngine, ProviderAIModel, ProviderCapability

if TYPE_CHECKING:
	from basilisk.account import Account


logger = logging.getLogger(__name__)


class OllamaEngine(BaseEngine):
	capabilities: set[ProviderCapability] = {
		ProviderCapability.TEXT,
		ProviderCapability.IMAGE,
	}
	unsupported_request_params: set[RequestParams] = {
		RequestParams.MAX_TOKENS,
		RequestParams.TEMPERATURE,
		RequestParams.TOP_P,
	}

	def __init__(self, account: Account):
		super().__init__(account)

	@cached_property
	def client(self) -> ollama.Client:
		"""
		Property to return the client object
		"""
		super().client
		logger.debug("Initializing new Ollama client")
		return ollama.Client(host=str(self.account.provider.base_url))

	@cached_property
	def models(self) -> list[ProviderAIModel]:
		"""
		Get models
		"""
		# TODO: should be fetched from user account
		return [
			ProviderAIModel(
				id="llama3.1",
				context_window=1048576,
				max_output_tokens=8192,
				vision=False,
			),
			ProviderAIModel(
				id="llava-llama3",
				context_window=1048576,
				max_output_tokens=8192,
				vision=True,
			),
		]

	def handle_message(self, message: Message) -> dict[str, Any]:
		content = ""
		images = []
		if isinstance(message.content, list):
			for part in message.content:
				if isinstance(part, str):
					content += part
				elif isinstance(part, ImageFile):
					if part.type == ImageFileTypes.IMAGE_LOCAL:
						images.append(part._location)
					elif part.type == ImageFileTypes.IMAGE_URL:
						raise ValueError("Image URLs are not supported")
				else:
					raise ValueError(f"Unsupported message part: {part}")

			output = {"role": message.role.value}
			if content:
				output["content"] = content
			if images:
				output["images"] = images
			return output
		if isinstance(message.content, str):
			return {"role": message.role.value, "content": message.content}
		raise ValueError(f"Unsupported message content: {message.content}")

	def completion(
		self,
		new_block: MessageBlock,
		conversation: Conversation,
		system_message: Message | None,
		**kwargs,
	) -> Union[Mapping[str, Any], Iterator[Mapping[str, Any]]]:
		super().completion(new_block, conversation, system_message, **kwargs)
		params = {
			"model": new_block.model.id,
			"messages": self.get_messages(
				new_block, conversation, system_message
			),
			"stream": new_block.stream,
		}
		params.update(kwargs)
		response = self.client.chat(**params)
		return response

	def completion_response_with_stream(
		self, stream: Iterator[Mapping[str, Any]]
	):
		for chunk in stream:
			content = chunk["message"]["content"]
			if content:
				yield self.normalize_linesep(content)

	def completion_response_without_stream(
		self, response, new_block, **kwargs
	) -> MessageBlock:
		new_block.response = Message(
			role=MessageRoleEnum.ASSISTANT,
			content=self.normalize_linesep(response["message"]["content"]),
		)
		return new_block
