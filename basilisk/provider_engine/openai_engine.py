from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, Generator, Union

from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from basilisk.conversation import (
	Conversation,
	Message,
	MessageBlock,
	MessageRoleEnum,
)
from basilisk.image_file import ImageFile

if TYPE_CHECKING:
	from basilisk.account import Account
from .base_engine import BaseEngine, ProviderAIModel, ProviderCapability

log = logging.getLogger(__name__)


class OpenAIEngine(BaseEngine):
	capabilities: set[ProviderCapability] = {
		ProviderCapability.IMAGE,
		ProviderCapability.TEXT,
		ProviderCapability.STT,
		ProviderCapability.TTS,
	}

	def __init__(self, account: Account) -> None:
		super().__init__(account)

	@cached_property
	def client(self) -> OpenAI:
		"""
		Property to return the client object
		"""
		super().client
		organization_key = (
			self.account.active_organization_key.get_secret_value()
			if self.account.active_organization_key
			else None
		)
		log.debug("Initializing new OpenAI client")
		return OpenAI(
			api_key=self.account.api_key.get_secret_value(),
			organization=organization_key,
			base_url=str(self.account.provider.base_url),
		)

	@cached_property
	def models(self) -> list[ProviderAIModel]:
		"""
		Get models
		"""
		super().models
		log.debug("Getting openAI models")
		# See <https://platform.openai.com/docs/models>
		return [
			ProviderAIModel(
				id="gpt-4o-mini",
				# Translators: This is a model description
				description=_(
					"Points to one of the most recent iterations of gpt-4o-mini model"
				),
				context_window=128000,
				max_output_tokens=16384,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4o",
				# Translators: This is a model description
				description=_(
					"Points to one of the most recent iterations of gpt-4o-mini model"
				),
				context_window=128000,
				max_output_tokens=16384,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="chatgpt-4o-latest",
				# Translators: This is a model description
				description=_(
					"Dynamic model continuously updated to the current version of GPT-4o in ChatGPT"
				),
				context_window=128000,
				max_output_tokens=16384,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4o-mini-2024-07-18",
				# Translators: This is a model description
				description=_(
					"Our affordable and intelligent small model for fast, lightweight tasks. GPT-4o mini is cheaper and more capable than GPT-3.5 Turbo"
				),
				context_window=128000,
				max_output_tokens=16384,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4o-2024-08-06",
				# Translators: This is a model description
				description=_(
					"Latest snapshot that supports Structured Outputs"
				),
				context_window=128000,
				max_output_tokens=16384,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4o-2024-05-13",
				# Translators: This is a model description
				description=_(
					"Our high-intelligence flagship model for complex, multi-step tasks"
				),
				context_window=128000,
				max_output_tokens=4096,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4-turbo",
				# Translators: This is a model description
				description=_(
					"The latest GPT-4 Turbo model with vision capabilities"
				),
				context_window=128000,
				max_output_tokens=4096,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-3.5-turbo",
				# Translators: This is a model description
				description=_(
					"Points to one of the most recent iterations of gpt-3.5 model"
				),
				context_window=16385,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-3.5-turbo-0125",
				# Translators: This is a model description
				description=_(
					"The latest GPT-3.5 Turbo model with higher accuracy at responding in requested formats and a fix for a bug which caused a text encoding issue for non-English language function calls"
				),
				context_window=16385,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4-turbo-preview",
				# Translators: This is a model description
				description=_(
					"Points to one of the most recent iterations of gpt-4 model"
				),
				context_window=128000,
				max_output_tokens=4096,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4-0125-preview",
				# Translators: This is a model description
				description=_(
					"The latest GPT-4 model intended to reduce cases of “laziness” where the model doesn’t complete a task"
				),
				context_window=128000,
				max_output_tokens=4096,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4-1106-preview",
				# Translators: This is a model description
				description=_(
					"GPT-4 Turbo model featuring improved instruction following, JSON mode, reproducible outputs, parallel function calling, and more"
				),
				context_window=128000,
				max_output_tokens=4096,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4-vision-preview",
				# Translators: This is a model description
				description=_(
					"GPT-4 Turbo with vision. Ability to understand images, in addition to all other GPT-4 Turbo capabilities"
				),
				context_window=128000,
				max_output_tokens=4096,
				vision=True,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4-0613",
				# Translators: This is a model description
				description=_(
					"More capable than any GPT-3.5 model, able to do more complex tasks, and optimized for chat"
				),
				max_output_tokens=8192,
				max_temperature=2.0,
			),
			ProviderAIModel(
				id="gpt-4-32k-0613",
				# Translators: This is a model description
				description=_(
					"Same capabilities as the standard gpt-4 mode but with 4x the context length"
				),
				context_window=32768,
				max_output_tokens=8192,
				max_temperature=2.0,
			),
		]

	def handle_message(self, message: Message) -> dict[str, Any]:
		if isinstance(message.content, list):
			output = []
			for part in message.content:
				if isinstance(part, str):
					output.append({"type": "text", "text": part})
				elif isinstance(part, ImageFile):
					output.append(
						{
							"type": "image_url",
							"image_url": {"url": part.get_url()},
						}
					)
				else:
					raise ValueError(f"Unsupported message part: {part}")
			return {"role": message.role.value, "content": output}
		if isinstance(message.content, str):
			return {"role": message.role.value, "content": message.content}
		raise ValueError(f"Unsupported message content: {message.content}")

	def completion(
		self,
		new_block: MessageBlock,
		conversation: Conversation,
		system_message: Message | None,
		**kwargs,
	) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
		super().completion(new_block, conversation, system_message, **kwargs)
		params = {
			"model": new_block.model.id,
			"messages": self.get_messages(
				new_block, conversation, system_message
			),
			"temperature": new_block.temperature,
			"top_p": new_block.top_p,
			"stream": new_block.stream,
		}
		if new_block.max_tokens:
			params["max_tokens"] = new_block.max_tokens
		params.update(kwargs)
		response = self.client.chat.completions.create(**params)
		return response

	def completion_response_with_stream(
		self, stream: Generator[ChatCompletionChunk, None, None]
	):
		for chunk in stream:
			delta = chunk.choices[0].delta
			if delta and delta.content:
				yield self.normalize_linesep(delta.content)

	def completion_response_without_stream(
		self, response: ChatCompletion, new_block: MessageBlock, **kwargs
	) -> MessageBlock:
		new_block.response = Message(
			role=MessageRoleEnum.ASSISTANT,
			content=self.normalize_linesep(response.choices[0].message.content),
		)
		return new_block

	def get_transcription(
		self, audio_file_path: str, response_format: str = "json"
	) -> str:
		"""
		Get transcription from audio file
		"""
		file = open(audio_file_path, "rb")
		transcription = self.client.audio.transcriptions.create(
			model="whisper-1", file=file, response_format=response_format
		)
		file.close()
		return transcription
