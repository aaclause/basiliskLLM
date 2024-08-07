from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field, RootModel


class ConversationProfile(BaseModel):
	name: str
	system_prompt: str = Field(default="")

	@classmethod
	def get_default(cls) -> ConversationProfile:
		return cls(name="default", system_prompt="default system prompt")


class ConversationProfileManager(RootModel):
	root: list[ConversationProfile] = Field(
		default_factory=lambda: [ConversationProfile.get_default()]
	)

	def __iter__(self) -> Iterable[ConversationProfile]:
		return iter(self.root)

	def add(self, profile: ConversationProfile):
		self.root.append(profile)
