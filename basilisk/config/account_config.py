from __future__ import annotations

import logging
from functools import cache, cached_property
from os import getenv
from typing import Any, Iterable, Optional
from uuid import uuid4

import keyring
from pydantic import (
	UUID4,
	BaseModel,
	ConfigDict,
	Field,
	FieldSerializationInfo,
	OnErrorOmit,
	SecretStr,
	SerializerFunctionWrapHandler,
	ValidationInfo,
	field_serializer,
	field_validator,
	model_validator,
)

import basilisk.global_vars as global_vars
from basilisk.consts import APP_NAME
from basilisk.provider import Provider, get_provider, providers

from .config_enums import AccountSource, KeyStorageMethodEnum
from .config_helper import (
	BasiliskBaseSettings,
	get_settings_config_dict,
	save_config_file,
)

log = logging.getLogger(__name__)


class AccountOrganization(BaseModel):
	model_config = ConfigDict(populate_by_name=True)
	id: UUID4 = Field(default_factory=uuid4)
	name: str
	key_storage_method: KeyStorageMethodEnum = Field(
		default=KeyStorageMethodEnum.plain
	)
	key: SecretStr
	source: AccountSource = Field(default=AccountSource.CONFIG, exclude=True)

	@field_validator("key", mode="before")
	@classmethod
	def validate_key(
		cls, value: Optional[Any], info: ValidationInfo
	) -> SecretStr:
		if isinstance(value, SecretStr):
			return value
		data = info.data
		if data["key_storage_method"] == KeyStorageMethodEnum.plain:
			if not isinstance(value, str):
				raise ValueError("Key must be a string")
			return SecretStr(value)
		elif data["key_storage_method"] == KeyStorageMethodEnum.system:
			value = keyring.get_password(APP_NAME, str(data["id"]))
			if not value:
				raise ValueError("Key not found in keyring")
			return SecretStr(value)
		else:
			raise ValueError("Invalid key storage method")

	@field_serializer("key", when_used="json")
	def dump_secret(self, value: SecretStr) -> str:
		if self.key_storage_method == KeyStorageMethodEnum.plain:
			return value.get_secret_value()
		elif self.key_storage_method == KeyStorageMethodEnum.system:
			keyring.set_password(
				APP_NAME, str(self.id), value.get_secret_value()
			)
		return None

	def delete_keyring_password(self):
		if self.key_storage_method == KeyStorageMethodEnum.system:
			keyring.delete_password(APP_NAME, str(self.id))


class Account(BaseModel):
	"""
	Manage API key and organization key
	"""

	model_config = ConfigDict(populate_by_name=True)
	id: UUID4 = Field(default_factory=uuid4)
	name: str
	provider: Provider = Field(
		validation_alias="provider_id", serialization_alias="provider_id"
	)
	api_key_storage_method: Optional[KeyStorageMethodEnum] = Field(
		default=KeyStorageMethodEnum.plain
	)
	api_key: Optional[SecretStr] = Field(default=None)
	organizations: Optional[list[AccountOrganization]] = Field(default=None)
	active_organization_id: Optional[UUID4] = Field(default=None)
	source: AccountSource = Field(default=AccountSource.CONFIG, exclude=True)

	def __init__(self, **data: Any):
		try:
			super().__init__(**data)
		except Exception as e:
			log.error(
				f"Error in account {e} the account will not be accessible",
				exc_info=e,
			)
			raise e

	@field_serializer("provider", when_used="always")
	def serialize_provider(value: Provider) -> str:
		return value.id

	@field_validator("api_key", mode="before")
	@classmethod
	def validate_api_key(
		cls, value: Optional[Any], info: ValidationInfo
	) -> Optional[SecretStr]:
		if isinstance(value, SecretStr):
			return value
		data = info.data
		if data["api_key_storage_method"] == KeyStorageMethodEnum.plain:
			if not isinstance(value, str):
				raise ValueError("API key must be a string")
			return SecretStr(value)
		elif data["api_key_storage_method"] == KeyStorageMethodEnum.system:
			value = keyring.get_password(APP_NAME, str(data["id"]))
			if not value:
				raise ValueError("API key not found in keyring")
			return SecretStr(value)
		else:
			raise ValueError("Invalid API key storage method")

	@field_serializer("api_key", when_used="json")
	def dump_secret(self, value: SecretStr) -> Optional[str]:
		if self.api_key_storage_method == KeyStorageMethodEnum.plain:
			return value.get_secret_value()
		elif self.api_key_storage_method == KeyStorageMethodEnum.system:
			keyring.set_password(
				APP_NAME, str(self.id), value.get_secret_value()
			)
		return None

	@field_validator("provider", mode="plain")
	@classmethod
	def validate_provider(cls, value: Any) -> Provider:
		if isinstance(value, Provider):
			return value
		if isinstance(value, str):
			return get_provider(id=value)

	@model_validator(mode="after")
	def require_keys(self) -> Account:
		if self.provider.require_api_key and not self.api_key:
			raise ValueError(f"API key for {self.provider.name} is required")
		if (
			not self.provider.organization_mode_available
			and self.active_organization_id
		):
			raise ValueError(
				f"Organization mode is not available for {self.provider.name}"
			)
		return self

	@model_validator(mode="after")
	def validate_active_organization(self) -> Account:
		if not self.active_organization_id:
			return self
		if not self.organizations:
			raise ValueError(
				f"No organizations found for {self.provider.name} account"
			)
		if not any(
			org.id == self.active_organization_id for org in self.organizations
		):
			raise ValueError(
				f"Organization '{self.active_organization_id}' not found for {self.provider.name} account"
			)
		return self

	@cached_property
	def active_organization(self) -> Optional[AccountOrganization]:
		if not self.active_organization_id:
			return None
		return next(
			filter(
				lambda x: x.id == self.active_organization_id,
				self.organizations,
			),
			None,
		)

	def reset_active_organization(self):
		try:
			del self.active_organization
		except AttributeError:
			pass

	@property
	def active_organization_name(self) -> Optional[str]:
		return (
			self.active_organization.name if self.active_organization else None
		)

	@property
	def active_organization_key(self) -> Optional[SecretStr]:
		return (
			self.active_organization.key if self.active_organization else None
		)

	def delete_keyring_password(self):
		if self.organizations:
			for org in self.organizations:
				org.delete_keyring_password()
		if self.api_key_storage_method == KeyStorageMethodEnum.system:
			keyring.delete_password(APP_NAME, str(self.id))


config_file_name = "accounts.yml"


class AccountManager(BasiliskBaseSettings):
	"""
	Manage multiple accounts for different providers
	A provider can have several accounts
	"""

	model_config = get_settings_config_dict(config_file_name)

	accounts: list[OnErrorOmit[Account]] = Field(default=list())

	@field_validator("accounts", mode="after")
	@classmethod
	def add_accounts_from_env_vars(
		cls, accounts: list[Account]
	) -> list[Account]:
		"""Load accounts from environment variables"""
		if global_vars.args.no_env_account:
			return accounts
		for provider in providers:
			organizations = []
			api_key = None
			if not provider.env_var_name_api_key:
				continue
			api_key = getenv(provider.env_var_name_api_key)
			if not api_key:
				continue
			active_organization = None
			if (
				provider.organization_mode_available
				and provider.env_var_name_organization_key
				and getenv(provider.env_var_name_organization_key)
			):
				active_organization = uuid4()
				organizations.append(
					AccountOrganization(
						id=active_organization,
						name=_("From environment variable"),
						key=SecretStr(
							getenv(provider.env_var_name_organization_key)
						),
						source=AccountSource.ENV_VAR,
					)
				)
			else:
				active_organization = None
			accounts.append(
				Account(
					name=f"{provider.name} account",
					provider=provider,
					api_key=api_key,
					organizations=organizations,
					active_organization_id=active_organization,
					source=AccountSource.ENV_VAR,
				)
			)
		return accounts

	@field_serializer("accounts", mode="wrap", when_used="json")
	@classmethod
	def serialize_accounts(
		cls,
		accounts: list[Account],
		handler: SerializerFunctionWrapHandler,
		info: FieldSerializationInfo,
	) -> list[dict[str, Any]]:
		accounts_config = filter(
			lambda x: x.source == AccountSource.CONFIG, accounts
		)
		return handler(list(accounts_config), info)

	def add(self, account: Account):
		if not isinstance(account, Account):
			raise ValueError("Account must be an instance of Account")
		self.accounts.append(account)
		log.debug(
			f"Added account for {account.provider.name} ({account.name}, source: {account.source})"
		)

	def get_accounts_by_provider(
		self, provider_name: Optional[str] = None
	) -> Iterable[Account]:
		return filter(lambda x: x.provider.name == provider_name, self.accounts)

	def remove(self, account: Account):
		account.delete_keyring_password()
		self.accounts.remove(account)

	def clear(self):
		self.accounts.clear()

	def __len__(self):
		return len(self.accounts)

	def __iter__(self):
		return iter(self.accounts)

	def __getitem__(self, index) -> Account:
		return self.accounts[index]

	def __setitem__(self, index, value):
		self.accounts[index] = value

	def save(self):
		save_config_file(
			self.model_dump(mode="json", by_alias=True),
			file_path=config_file_name,
		)


@cache
def get_account_config() -> AccountManager:
	log.debug("Loading account config")
	return AccountManager()
