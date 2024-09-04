from __future__ import annotations

import logging
import time
from enum import Enum
from functools import cached_property
from typing import Any, Iterable, Optional, Type

from pydantic import BaseModel, Field, HttpUrl

from .provider_engine.base_engine import BaseEngine

log = logging.getLogger(__name__)


class ProviderAPIType(Enum):
	OPENAI = "openai"
	ANTHROPIC = "anthropic"
	OLLAMA = "ollama"
	GEMINI = "gemini"


class Provider(BaseModel):
	"""
	Manage API key
	"""

	id: str
	name: str
	base_url: Optional[HttpUrl] = Field(default=None)
	api_type: ProviderAPIType
	organization_mode_available: bool = Field(default=False)
	require_api_key: bool = Field(default=True)
	env_var_name_api_key: Optional[str] = Field(default=None)
	env_var_name_organization_key: Optional[str] = Field(default=None)
	engine_cls_path: str
	custom: bool = Field(default=False)

	@cached_property
	def engine_cls(self) -> Type[BaseEngine]:
		"""
		Get engine class
		"""
		start = time.time()
		try:
			module_path, class_name = self.engine_cls_path.rsplit(".", 1)
			module = __import__(module_path, fromlist=[class_name])
			end = time.time()
			cls = getattr(module, class_name)
			log.debug(
				f"Loaded engine class '{class_name}' in {end - start:.3f} seconds"
			)
			return cls
		except ImportError as e:
			log.error(f"Error importing engine class: {e}")
			raise e
		except AttributeError as e:
			log.error(f"Error getting engine class: {e}")
			raise e


providers = [
	Provider(
		id="anthropic",
		name="Anthropic",
		api_type=ProviderAPIType.ANTHROPIC,
		organization_mode_available=False,
		require_api_key=True,
		env_var_name_api_key="ANTHROPIC_API_KEY",
		env_var_name_organization_key="ANTHROPIC_ORG_KEY",
		engine_cls_path="basilisk.provider_engine.anthropic_engine.AnthropicEngine",
	),
	Provider(
		id="gemini",
		name="Gemini",
		base_url="https://generativelanguage.googleapis.com",
		api_type=ProviderAPIType.GEMINI,
		organization_mode_available=False,
		require_api_key=True,
		env_var_name_api_key="GOOGLE_API_KEY",
		engine_cls_path="basilisk.provider_engine.gemini_engine.GeminiEngine",
	),
	Provider(
		id="mistralai",
		name="MistralAI",
		base_url="https://api.mistral.ai/v1",
		api_type=ProviderAPIType.OPENAI,
		organization_mode_available=False,
		require_api_key=True,
		env_var_name_api_key="MISTRAL_API_KEY",
		engine_cls_path="basilisk.provider_engine.mistralai_engine.MistralAIEngine",
	),
	Provider(
		id="openai",
		name="OpenAI",
		base_url="https://api.openai.com/v1",
		api_type=ProviderAPIType.OPENAI,
		organization_mode_available=True,
		require_api_key=True,
		env_var_name_api_key="OPENAI_API_KEY",
		env_var_name_organization_key="OPENAI_ORG_KEY",
		engine_cls_path="basilisk.provider_engine.openai_engine.OpenAIEngine",
	),
	Provider(
		id="openrouter",
		name="OpenRouter",
		base_url="https://openrouter.ai/api/v1",
		api_type=ProviderAPIType.OPENAI,
		organization_mode_available=False,
		require_api_key=True,
		env_var_name_api_key="OPENROUTER_API_KEY",
		engine_cls_path="basilisk.provider_engine.openrouter_engine.OpenRouterEngine",
	),
	Provider(
		id="ollama",
		name="Ollama",
		base_url="http://127.0.0.1:11434/",
		api_type=ProviderAPIType.OLLAMA,
		organization_mode_available=False,
		require_api_key=False,
		engine_cls_path="basilisk.provider_engine.ollama_engine.OllamaEngine",
		custom=True,
	),
]


def get_providers(**kwargs: dict[str, Any]) -> Iterable[Provider]:
	"""
	Get provider by criteria
	"""
	match_providers = providers
	for k, v in kwargs.items():
		match_providers = filter(
			lambda x: getattr(x, k, None) == v, match_providers
		)
	return match_providers


def get_provider(**kwargs: dict[str, Any]) -> Provider:
	"""
	Get provider by criteria
	"""
	match_providers = list(get_providers(**kwargs))
	if not match_providers or len(match_providers) == 0:
		raise ValueError("No provider found")
	if len(match_providers) > 1:
		raise ValueError("Multiple providers found")
	return match_providers[0]
