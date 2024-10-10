import logging
from datetime import datetime
from functools import cache

from pydantic import BaseModel, Field, model_validator

from .config_enums import (
	AutomaticUpdateModeEnum,
	LogLevelEnum,
	ReleaseChannelEnum,
)
from .config_helper import (
	BasiliskBaseSettings,
	get_settings_config_dict,
	save_config_file,
)

log = logging.getLogger(__name__)

config_file_name = "config.yml"


class GeneralSettings(BaseModel):
	language: str = Field(default="auto")
	advanced_mode: bool = Field(default=False)
	log_level: LogLevelEnum = Field(default=LogLevelEnum.INFO)
	automatic_update_mode: AutomaticUpdateModeEnum = Field(
		default=AutomaticUpdateModeEnum.NOTIFY
	)
	release_channel: ReleaseChannelEnum = Field(default=ReleaseChannelEnum.BETA)
	last_update_check: datetime | None = Field(default=None)
	quit_on_close: bool = Field(default=False)


class ConversationSettings(BaseModel):
	role_label_user: str | None = Field(default=None)
	role_label_assistant: str | None = Field(default=None)
	nav_msg_select: bool = Field(default=False)
	shift_enter_mode: bool = Field(default=False)


class ImagesSettings(BaseModel):
	max_height: int = Field(default=720)
	max_width: int = Field(default=0)
	quality: int = Field(default=85, ge=1, le=100)
	resize: bool = Field(default=False)


class RecordingsSettings(BaseModel):
	sample_rate: int = Field(default=16000, ge=8000, le=48000)
	channels: int = Field(default=1, ge=1, le=2)
	dtype: str = Field(default="int16")


class ServerSettings(BaseModel):
	port: int = Field(default=4242)
	enable: bool = Field(default=True)


class NetworkSettings(BaseModel):
	use_system_cert_store: bool = Field(default=True)


class BasiliskConfig(BasiliskBaseSettings):
	model_config = get_settings_config_dict(config_file_name)

	general: GeneralSettings = Field(default_factory=GeneralSettings)
	conversation: ConversationSettings = Field(
		default_factory=ConversationSettings
	)
	images: ImagesSettings = Field(default_factory=ImagesSettings)
	recordings: RecordingsSettings = Field(default_factory=RecordingsSettings)
	network: NetworkSettings = Field(default_factory=NetworkSettings)
	server: ServerSettings = Field(default_factory=ServerSettings)

	@model_validator(mode="before")
	@classmethod
	def migrate_accounts(cls, value: dict) -> dict:
		accounts = value.pop("accounts", None)
		if not accounts:
			return value
		log.info("Migrating accounts to its own config file")
		from .account_config import AccountManager

		account_dict = {"accounts": accounts}
		account_manager = AccountManager.model_validate(account_dict)
		account_manager.save()
		save_config_file(value, config_file_name)
		return value

	def save(self):
		save_config_file(
			self.model_dump(
				mode="json",
				by_alias=True,
				exclude_defaults=True,
				exclude_none=True,
			),
			config_file_name,
		)


@cache
def get_basilisk_config() -> BasiliskConfig:
	log.debug("Loading Basilisk config")
	return BasiliskConfig()
