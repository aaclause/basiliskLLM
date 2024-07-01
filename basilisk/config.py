import logging
import yaml
import basilisk.global_vars as global_vars
from datetime import datetime
from enum import Enum
from pathlib import Path
from platformdirs import user_config_path
from pydantic import BaseModel, Extra, Field
from pydantic_settings import (
	BaseSettings,
	PydanticBaseSettingsSource,
	SettingsConfigDict,
	YamlConfigSettingsSource,
)
from .account import AccountManager

log = logging.getLogger(__name__)


class LogLevelEnum(Enum):
	NOTSET = "off"
	DEBUG = "debug"
	INFO = "info"
	WARNING = "warning"
	ERROR = "error"
	CRITICAL = "critical"


class ReleaseChannelEnum(Enum):
	STABLE = "stable"
	BETA = "beta"
	DEV = "dev"


class AutomaticUpdateModeEnum(Enum):
	OFF = "off"
	NOTIFY = "notify"
	DOWNLOAD = "download"
	INSTALL = "install"


config_file_path = Path("config.yml")
search_config_paths = []
if global_vars.user_data_path:
	search_config_paths.append(global_vars.user_data_path / config_file_path)
search_config_paths.append(
	user_config_path(
		"basilisk", "basilisk_llm", roaming=True, ensure_exists=True
	)
	/ config_file_path
)


def search_existing_path(paths: list[Path]) -> Path:
	for p in paths:
		if p.exists() or p.parent.exists():
			return p
	return paths[-1]


class GeneralSettings(BaseModel):
	language: str = Field(default="auto")
	advanced_mode: bool = Field(default=False)
	log_level: LogLevelEnum = Field(default=LogLevelEnum.DEBUG)
	automatic_update_mode: AutomaticUpdateModeEnum = Field(
		default=AutomaticUpdateModeEnum.NOTIFY
	)
	release_channel: ReleaseChannelEnum = Field(
		default=ReleaseChannelEnum.STABLE
	)
	last_update_check: datetime | None = Field(default=None)
	quit_on_close: bool = Field(default=False)


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


class BasiliskConfig(BaseSettings):
	model_config = SettingsConfigDict(
		env_prefix="BASILISK_",
		extra=Extra.allow,
		yaml_file=search_existing_path(search_config_paths),
		yaml_file_encoding="UTF-8",
	)
	general: GeneralSettings = Field(default_factory=GeneralSettings)
	accounts: AccountManager = Field(
		default_factory=lambda: AccountManager(list())
	)
	images: ImagesSettings = Field(default_factory=ImagesSettings)
	recordings: RecordingsSettings = Field(default_factory=RecordingsSettings)
	server: ServerSettings = Field(default_factory=ServerSettings)

	@classmethod
	def settings_customise_sources(
		cls,
		settings_cls: BaseSettings,
		init_settings: PydanticBaseSettingsSource,
		env_settings: PydanticBaseSettingsSource,
		dotenv_settings: PydanticBaseSettingsSource,
		file_secret_settings: PydanticBaseSettingsSource,
	) -> tuple[PydanticBaseSettingsSource, ...]:
		return (
			YamlConfigSettingsSource(settings_cls),
			env_settings,
			init_settings,
		)

	def save(self) -> None:
		basilisk_dict = self.model_dump(mode="json", by_alias=True)
		log.debug("Saving config: %s", basilisk_dict)
		conf_save_path = search_existing_path(search_config_paths)
		with conf_save_path.open(mode='w', encoding="UTF-8") as config_file:
			yaml.dump(basilisk_dict, config_file, indent=2, sort_keys=False)
		log.debug("Config saved to %s", conf_save_path)


conf = None


def initialize_config() -> BasiliskConfig:
	global conf
	conf = BasiliskConfig()
	return conf
