from __future__ import annotations

import logging
from base64 import b64decode
from functools import cached_property
from typing import TYPE_CHECKING

import google.generativeai as genai

from basilisk.conversation import (
	Conversation,
	Message,
	MessageBlock,
	MessageRoleEnum,
)
from basilisk.image_file import ImageFile

from .base_engine import BaseEngine, ProviderAIModel, ProviderCapability

if TYPE_CHECKING:
	from basilisk.account import Account

logger = logging.getLogger(__name__)


class GeminiEngine(BaseEngine):
	capabilities: set[ProviderCapability] = {
		ProviderCapability.TEXT,
		ProviderCapability.IMAGE,
	}

	def __init__(self, account: Account) -> None:
		super().__init__(account)
		genai.configure(api_key=self.account.api_key.get_secret_value())

	@property
	def client(self) -> None:
		"""
		Property to return the client object
		"""
		raise NotImplementedError("Getting client not supported for Gemini")

	@cached_property
	def models(self) -> list[ProviderAIModel]:
		"""
		Get models
		"""
		return [
			ProviderAIModel(
				id="gemini-1.5-flash-latest",
				# Translators: This is a model description
				description=_(
					'Fast and versatile multimodal model for scaling across diverse tasks'
				),
				context_window=1048576,
				max_output_tokens=8192,
				vision=True,
				default_temperature=1.0,
			),
			ProviderAIModel(
				id="gemini-1.5-pro-latest",
				# Translators: This is a model description
				description=_(
					"Mid-size multimodal model that supports up to 1 million tokens"
				),
				context_window=2097152,
				max_output_tokens=8192,
				vision=True,
				default_temperature=1.0,
			),
			ProviderAIModel(
				id="gemini-1.5-flash",
				# Translators: This is a model description
				description=_(
					"Fast and versatile multimodal model for scaling across diverse tasks"
				),
				context_window=1048576,
				max_output_tokens=8192,
				vision=True,
				default_temperature=1.0,
			),
			ProviderAIModel(
				id="gemini-1.5-pro",
				# Translators: This is a model description
				description=_(
					"Mid-size multimodal model that supports up to 1 million tokens"
				),
				context_window=2097152,
				max_output_tokens=8192,
				vision=True,
				default_temperature=1.0,
			),
			ProviderAIModel(
				id="gemini-1.0-pro-latest",
				# Translators: This is a model description
				description=_(
					"The best model for scaling across a wide range of tasks. This is the latest model."
				),
				context_window=30720,
				max_output_tokens=2048,
				default_temperature=0.9,
			),
			ProviderAIModel(
				id="gemini-1.0-pro",
				# Translators: This is a model description
				description=_(
					"The best model for scaling across a wide range of tasks"
				),
				context_window=30720,
				max_output_tokens=2048,
				default_temperature=0.9,
			),
			ProviderAIModel(
				id="gemini-1.0-pro-vision-latest",
				# Translators: This is a model description
				description=_(
					'The best image understanding model to handle a broad range of applications'
				),
				context_window=12288,
				max_output_tokens=4096,
				vision=True,
				default_temperature=0.4,
			),
		]

	def convert_role(self, role: MessageRoleEnum) -> str:
		if role == MessageRoleEnum.ASSISTANT:
			return "model"
		elif role == MessageRoleEnum.USER:
			return "user"
		elif role == MessageRoleEnum.SYSTEM:
			raise NotImplementedError(
				"System role must be set on the model instance"
			)

	def convert_image(self, image: dict[str, str]) -> genai.protos.Part:
		url = image.get_url()
		if url.startswith("data:"):
			image_media_type, image_data = url.split(";", 1)
			image_media_type = image_media_type.split(":", 1)[1]
			image_data = image_data.split(",", 1)[1]
			return genai.protos.Part(
				inline_data=genai.protos.Blob(
					mime_type=image_media_type, data=b64decode(image_data)
				)
			)
		else:
			raise ValueError("Unsupported content type")

	def convert_message_content(
		self, message: Message
	) -> list[genai.protos.Part]:
		parts = []
		for content in message.content:
			if isinstance(content, ImageFile):
				parts.append(self.convert_image(content))
			elif isinstance(content, str):
				parts.append(genai.protos.Part(text=content))
			else:
				raise ValueError(f"Unsupported message part: {content}")
		return parts

	def handle_message(self, message: Message) -> Message:
		pass

	def get_messages(
		self, new_block: MessageBlock, conversation: Conversation, **kwargs
	) -> list[genai.types.ContentsType]:
		"""
		Get messages
		"""
		messages = []
		for message_block in conversation.messages:
			if not message_block.response:
				continue
			messages.extend(
				[
					genai.protos.Content(
						role=self.convert_role(message_block.request.role),
						parts=self.convert_message_content(
							message_block.request
						),
					),
					genai.protos.Content(
						role=self.convert_role(message_block.response.role),
						parts=self.convert_message_content(
							message_block.response
						),
					),
				]
			)
		messages.append(
			genai.protos.Content(
				role=self.convert_role(new_block.request.role),
				parts=self.convert_message_content(new_block.request),
			)
		)
		return messages

	def completion(
		self,
		new_block: MessageBlock,
		conversation: Conversation,
		system_message: Message | None,
		**kwargs,
	) -> genai.types.GenerateContentResponse:
		super().completion(new_block, conversation, system_message, **kwargs)
		model = genai.GenerativeModel(
			model_name=new_block.model.id,
			system_instruction=system_message.content
			if system_message
			else None,
		)

		generation_config = genai.GenerationConfig(
			max_output_tokens=new_block.max_tokens
			if new_block.max_tokens
			else None,
			temperature=new_block.temperature,
			top_p=new_block.top_p,
		)
		return model.generate_content(
			contents=self.get_messages(new_block, conversation),
			generation_config=generation_config,
			stream=new_block.stream,
		)

	def completion_response_without_stream(
		self,
		response: genai.types.GenerateContentResponse,
		new_block: MessageBlock,
		**kwargs,
	) -> MessageBlock:
		new_block.response = Message(
			role=MessageRoleEnum.ASSISTANT,
			content=self.normalize_linesep(response.text),
		)
		return new_block

	def completion_response_with_stream(
		self, stream: genai.types.GenerateContentResponse, **kwargs
	):
		for chunk in stream:
			chunk_text = chunk.text
			if chunk_text:
				yield self.normalize_linesep(chunk_text)
