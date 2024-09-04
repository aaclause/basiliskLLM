from logging import getLogger
from typing import Optional

import wx
from more_itertools import first, locate
from pydantic import SecretStr

from basilisk.account import (
	Account,
	AccountOrganization,
	AccountSource,
	KeyStorageMethodEnum,
	get_account_source_labels,
)
from basilisk.config import conf
from basilisk.provider import get_provider, providers

log = getLogger(__name__)

key_storage_methods = {
	# Translators: A label for the API key storage method in the account dialog
	KeyStorageMethodEnum.plain: _("Plain text"),
	# Translators: A label for the API key storage method in the account dialog
	KeyStorageMethodEnum.system: _("System keyring"),
}


class EditAccountOrganizationDialog(wx.Dialog):
	def __init__(
		self,
		parent: wx.Window,
		title: str,
		organization: Optional[AccountOrganization] = None,
		size: tuple = (400, 200),
	):
		wx.Dialog.__init__(self, parent, title=title, size=size)
		self.parent = parent
		self.organization = organization
		self.init_ui()
		self.init_data()
		self.update_data()
		self.Centre()
		self.Show()
		self.name.SetFocus()

	def init_ui(self):
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		panel.SetSizer(sizer)

		label = wx.StaticText(
			panel,
			# Translators: A label in account dialog
			label=_("&Name:"),
			style=wx.ALIGN_LEFT,
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.name = wx.TextCtrl(panel)
		sizer.Add(self.name, 0, wx.EXPAND)

		label = wx.StaticText(
			panel,
			# Translators: A label in account dialog
			label=_("Organisation key storage &method:"),
			style=wx.ALIGN_LEFT,
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.key_storage_method = wx.ComboBox(
			panel,
			choices=list(key_storage_methods.values()),
			style=wx.CB_READONLY,
		)
		sizer.Add(self.key_storage_method, 0, wx.EXPAND)
		label = wx.StaticText(
			panel,
			# Translators: A label in account dialog
			label=_("Organisation &Key:"),
			style=wx.ALIGN_LEFT,
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.key = wx.TextCtrl(panel)
		sizer.Add(self.key, 0, wx.EXPAND)

		bSizer = wx.BoxSizer(wx.HORIZONTAL)

		btn = wx.Button(panel, wx.ID_OK)
		btn.SetDefault()
		btn.Bind(wx.EVT_BUTTON, self.on_ok)
		bSizer.Add(btn, 0, wx.ALL, 5)

		btn = wx.Button(panel, wx.ID_CANCEL)
		btn.Bind(wx.EVT_BUTTON, self.on_cancel)
		bSizer.Add(btn, 0, wx.ALL, 5)

		sizer.Add(bSizer, 0, wx.ALL, 5)

	def init_data(self):
		if not self.organization:
			self.key_storage_method.SetSelection(0)
			return

		self.name.SetValue(self.organization.name)
		index = first(
			locate(
				key_storage_methods.keys(),
				lambda x: x == self.organization.key_storage_method,
			),
			-1,
		)
		self.key_storage_method.SetSelection(index)
		self.key.SetValue(self.organization.key.get_secret_value())

	def update_data(self):
		pass

	def on_ok(self, event):
		if not self.name.GetValue():
			msg = _("Please enter a name")
			wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
			self.name.SetFocus()
			return
		if self.key_storage_method.GetSelection() == -1:
			msg = _("Please select a key storage method")
			wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
			self.key_storage_method.SetFocus()
			return
		if not self.key.GetValue():
			msg = _("Please enter a key")
			wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
			self.key.SetFocus()
			return
		key_storage_method = list(key_storage_methods.keys())[
			self.key_storage_method.GetSelection()
		]
		if self.organization:
			self.organization.name = self.name.GetValue()
			self.organization.key_storage_method = key_storage_method
			self.organization.key = SecretStr(self.key.GetValue())
		else:
			self.organization = AccountOrganization(
				name=self.name.GetValue(),
				key_storage_method=key_storage_method,
				key=SecretStr(self.key.GetValue()),
			)
		self.EndModal(wx.ID_OK)

	def on_cancel(self, event):
		self.EndModal(wx.ID_CANCEL)


class AccountOrganizationDialog(wx.Dialog):
	def __init__(
		self, parent: wx.Window, title: str, account: Account, size=(400, 400)
	):
		wx.Dialog.__init__(self, parent, title=title, size=size)
		self.account_source_labels = get_account_source_labels()
		self.parent = parent
		self.account = account
		self.init_ui()
		self.init_data()
		self.update_data()
		self.Centre()
		self.Show()

	def init_ui(self):
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		panel.SetSizer(sizer)

		label = wx.StaticText(
			panel, label=_("Organizations"), style=wx.ALIGN_LEFT
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.organization_list = wx.ListCtrl(panel, style=wx.LC_REPORT)
		self.organization_list.InsertColumn(
			0,
			# Translators: A label in account dialog
			_("Name"),
		)
		self.organization_list.InsertColumn(
			1,
			# Translators: A label in account dialog
			_("Key"),
		)
		self.organization_list.InsertColumn(
			2,
			# Translators: A label in account dialog
			_("Source"),
		)
		self.organization_list.Bind(
			wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected
		)
		self.organization_list.Bind(wx.EVT_KEY_DOWN, self.on_org_list_key_down)
		sizer.Add(self.organization_list, 1, wx.EXPAND)

		add_btn = wx.Button(panel, label=_("&Add"))
		sizer.Add(add_btn, 0, wx.ALL, 5)
		self.edit_btn = wx.Button(panel, label=_("&Edit"))
		self.edit_btn.Disable()
		sizer.Add(self.edit_btn, 0, wx.ALL, 5)
		self.remove_btn = wx.Button(panel, label=_("&Remove"))
		self.remove_btn.Disable()
		sizer.Add(self.remove_btn, 0, wx.ALL, 5)

		self.Bind(wx.EVT_BUTTON, self.on_add, add_btn)
		self.Bind(wx.EVT_BUTTON, self.on_edit, self.edit_btn)
		self.Bind(wx.EVT_BUTTON, self.on_remove, self.remove_btn)

		bSizer = wx.BoxSizer(wx.HORIZONTAL)

		btn = wx.Button(panel, wx.ID_OK)
		btn.Bind(wx.EVT_BUTTON, self.onOK)
		bSizer.Add(btn, 0, wx.ALL, 5)

		btn = wx.Button(panel, wx.ID_CANCEL)
		btn.Bind(wx.EVT_BUTTON, self.onCancel)
		bSizer.Add(btn, 0, wx.ALL, 5)

		sizer.Add(bSizer, 0, wx.ALL, 5)

	def init_data(self):
		self.organizations = self.account.organizations or []

	def update_data(self):
		for organization in self.organizations:
			self.organization_list.Append(
				(
					organization.name,
					organization.key.get_secret_value(),
					self.account_source_labels.get(
						organization.source, _("Unknown")
					),
				)
			)

	def update_ui(self):
		selected_item = self.organization_list.GetFirstSelected()
		if selected_item == -1:
			self.edit_btn.Disable()
			self.remove_btn.Disable()
			return
		organization = self.organizations[selected_item]
		if organization.source == AccountSource.ENV_VAR:
			self.edit_btn.Disable()
			self.remove_btn.Disable()
			return
		self.edit_btn.Enable()
		self.remove_btn.Enable()

	def on_item_selected(self, event):
		self.update_ui()

	def on_add(self, event):
		dialog = EditAccountOrganizationDialog(self, _("Add organization"))
		if dialog.ShowModal() == wx.ID_OK:
			organization = dialog.organization
			self.organizations.append(organization)
			self.organization_list.Append(
				(
					organization.name,
					organization.key.get_secret_value(),
					self.account_source_labels.get(
						organization.source, _("Unknown")
					),
				)
			)
		dialog.Destroy()
		self.organization_list.SetItemState(
			self.organization_list.GetItemCount() - 1,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
		)
		self.organization_list.EnsureVisible(
			self.organization_list.GetItemCount() - 1
		)

	def on_edit(self, event):
		selected_item = self.organization_list.GetFirstSelected()
		organization = self.organizations[selected_item]
		dialog = EditAccountOrganizationDialog(
			self, _("Edit organization"), organization
		)
		if dialog.ShowModal() == wx.ID_OK:
			organization = dialog.organization
			self.organizations[selected_item] = organization
			self.organization_list.SetItem(selected_item, 0, organization.name)
			self.organization_list.SetItem(
				selected_item, 1, organization.key.get_secret_value()
			)
			self.organization_list.SetItem(
				selected_item,
				2,
				self.account_source_labels.get(
					organization.source, _("Unknown")
				),
			)
		dialog.Destroy()
		self.organization_list.SetItemState(
			selected_item,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
		)
		self.organization_list.EnsureVisible(selected_item)

	def on_remove(self, event):
		index = self.organization_list.GetFirstSelected()
		organization = self.organizations[index]
		# Translators: A confirmation message in account dialog for removing organization
		msg = _("Are you sure you want to remove the organization {}?").format(
			organization.name
		)
		if wx.MessageBox(msg, _("Confirmation"), wx.YES_NO) != wx.YES:
			return
		organization.delete_keyring_password()
		self.organization_list.Select(index - 1)
		self.organization_list.DeleteItem(index)
		if self.account.active_organization_id == organization.id:
			self.account.active_organization_id = None
		self.organizations.pop(index)
		self.update_ui()

	def onOK(self, event):
		self.account.organizations = self.organizations
		self.EndModal(wx.ID_OK)

	def onCancel(self, event):
		self.EndModal(wx.ID_CANCEL)

	def on_org_list_key_down(self, event: wx.KeyEvent):
		if event.GetKeyCode() == wx.WXK_RETURN:
			self.on_edit(event)
		elif event.GetKeyCode() == wx.WXK_DELETE:
			self.on_remove(event)
		else:
			event.Skip()


class EditAccountDialog(wx.Dialog):
	def __init__(self, parent, title, size=(400, 400), account: Account = None):
		wx.Dialog.__init__(self, parent, title=title, size=size)
		self.parent = parent
		self.account = account
		self.init_ui()
		if account:
			self.init_data()
			self.update_ui()
		self.Centre()
		self.Show()
		self.name.SetFocus()

	def init_ui(self):
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		panel.SetSizer(sizer)

		label = wx.StaticText(
			panel,
			# Translators: A label in account dialog
			label=_("&Name:"),
			style=wx.ALIGN_LEFT,
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.name = wx.TextCtrl(panel)
		sizer.Add(self.name, 0, wx.EXPAND)

		label = wx.StaticText(
			panel,
			# Translators: A label in account dialog
			label=_("&Provider:"),
			style=wx.ALIGN_LEFT,
		)
		sizer.Add(label, 0, wx.ALL, 5)
		provider_choices = [provider.name for provider in providers]
		self.provider = wx.ComboBox(
			panel, choices=provider_choices, style=wx.CB_READONLY
		)
		self.provider.Bind(wx.EVT_COMBOBOX, lambda e: self.update_ui())
		sizer.Add(self.provider, 0, wx.EXPAND)

		label = wx.StaticText(
			panel,
			style=wx.ALIGN_LEFT,
			# Translators: A label in account dialog
			label=_("API &key storage method:"),
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.api_key_storage_method = wx.ComboBox(
			panel,
			choices=list(key_storage_methods.values()),
			style=wx.CB_READONLY,
		)
		sizer.Add(self.api_key_storage_method, 0, wx.EXPAND)
		self.api_key_storage_method.Disable()
		label = wx.StaticText(
			panel,
			style=wx.ALIGN_LEFT,
			# Translators: A label in account dialog
			label=_("API &key:"),
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.api_key = wx.TextCtrl(panel)
		self.api_key.Disable()
		sizer.Add(self.api_key, 0, wx.EXPAND)

		label = wx.StaticText(
			panel, label=_("&Organization to use:"), style=wx.ALIGN_LEFT
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.organization = wx.ComboBox(panel, style=wx.CB_READONLY)
		self.organization.Disable()
		sizer.Add(self.organization, 0, wx.EXPAND)

		bSizer = wx.BoxSizer(wx.HORIZONTAL)

		btn = wx.Button(panel, wx.ID_OK)
		btn.SetDefault()
		btn.Bind(wx.EVT_BUTTON, self.on_ok)
		bSizer.Add(btn, 0, wx.ALL, 5)

		btn = wx.Button(panel, wx.ID_CANCEL)
		btn.Bind(wx.EVT_BUTTON, self.on_cancel)
		bSizer.Add(btn, 0, wx.ALL, 5)

		sizer.Add(bSizer, 0, wx.ALL, 5)

	def init_data(self):
		if not self.account:
			self.api_key_storage_method.SetSelection(0)
			return
		self.name.SetValue(self.account.name)
		index = first(
			locate(providers, lambda x: x.name == self.account.provider.name),
			-1,
		)
		self.provider.SetSelection(index)
		if self.account.api_key and self.account.api_key_storage_method:
			index = first(
				locate(
					key_storage_methods.keys(),
					lambda x: x == self.account.api_key_storage_method,
				),
				-1,
			)
			self.api_key_storage_method.SetSelection(index)
			self.api_key.SetValue(self.account.api_key.get_secret_value())
		self.organization.Enable(
			self.account.provider.organization_mode_available
		)
		if not self.account.provider.organization_mode_available:
			return
		if self.account.organizations:
			choices = [_("Personal")] + [
				organization.name for organization in self.account.organizations
			]
			self.organization.SetItems(choices)
		if self.account.active_organization_id:
			index = (
				first(
					locate(
						self.account.organizations,
						lambda x: x.id == self.account.active_organization_id,
					),
					-1,
				)
				+ 1
			)
			self.organization.SetSelection(index)

	def update_ui(self):
		provider_index = self.provider.GetSelection()
		if provider_index == -1:
			log.debug("No provider selected")
			return
		provider_name = self.provider.GetValue()
		provider = get_provider(name=provider_name)
		self.api_key.Enable(provider.require_api_key)
		self.api_key_storage_method.Enable(provider.require_api_key)

		if self.account:
			self.organization.Enable(provider.organization_mode_available)

	def on_ok(self, event):
		if not self.name.GetValue():
			msg = _("Please enter a name")
			wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
			self.name.SetFocus()
			return
		provider_index = self.provider.GetSelection()
		if provider_index == -1:
			msg = _("Please select a provider")
			wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
			self.provider.SetFocus()
			return
		provider_name = self.provider.GetValue()
		provider = get_provider(name=provider_name)
		if provider.require_api_key:
			if self.api_key_storage_method.GetSelection() == -1:
				msg = _("Please select an API key storage method")
				wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
				self.api_key_storage_method.SetFocus()
				return
			if not self.api_key.GetValue():
				msg = _(
					"Please enter an API key. It is required for this provider"
				)
				wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
				self.api_key.SetFocus()
				return
		organization_index = self.organization.GetSelection()
		active_organization = None
		if organization_index > 0:
			active_organization = self.account.organizations[
				organization_index - 1
			].id
		api_key_storage_method = None
		api_key = None
		if provider.require_api_key:
			api_key_storage_method = list(key_storage_methods.keys())[
				self.api_key_storage_method.GetSelection()
			]
			api_key = SecretStr(self.api_key.GetValue())
		if self.account:
			self.account.name = self.name.GetValue()
			self.account.provider = provider
			self.account.api_key_storage_method = api_key_storage_method
			self.account.api_key = api_key
			self.account.active_organization_id = active_organization
		else:
			self.account = Account(
				name=self.name.GetValue(),
				provider=provider,
				api_key_storage_method=api_key_storage_method,
				api_key=api_key,
				active_organization_id=active_organization,
				source=AccountSource.CONFIG,
			)
		self.EndModal(wx.ID_OK)

	def on_cancel(self, event):
		self.EndModal(wx.ID_CANCEL)


class AccountDialog(wx.Dialog):
	"""Manage account settings"""

	def __init__(self, parent, title, size=(400, 400)):
		wx.Dialog.__init__(self, parent, title=title, size=size)
		self.account_source_labels = get_account_source_labels()
		self.parent = parent
		self.init_ui()
		self.init_data()
		self.update_data()
		self.Centre()
		self.Show()

	def init_ui(self):
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		panel.SetSizer(sizer)

		label = wx.StaticText(panel, label=_("Accounts"), style=wx.ALIGN_LEFT)
		sizer.Add(label, 0, wx.ALL, 5)
		self.account_list = wx.ListCtrl(panel, style=wx.LC_REPORT)
		self.account_list.InsertColumn(
			0,
			# Translators: A label in account dialog
			_("Name"),
		)
		self.account_list.InsertColumn(
			1,
			# Translators: A label in account dialog
			_("Provider"),
		)
		self.account_list.InsertColumn(
			2,
			# Translators: A label in account dialog
			_("Active organization"),
		)
		self.account_list.InsertColumn(
			3,
			# Translators: A label in account dialog
			_("Source"),
		)
		self.account_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
		self.account_list.Bind(wx.EVT_KEY_DOWN, self.on_account_list_key_down)
		sizer.Add(self.account_list, 1, wx.EXPAND)

		add_btn = wx.Button(panel, label=_("&Add..."))
		sizer.Add(add_btn, 0, wx.ALL, 5)

		self.manage_organizations = wx.Button(
			panel, label=_("&Manage organizations...")
		)
		self.manage_organizations.Disable()
		sizer.Add(self.manage_organizations, 0, wx.ALL, 5)

		self.edit_btn = wx.Button(panel, label=_("&Edit"))
		self.edit_btn.Disable()
		sizer.Add(self.edit_btn, 0, wx.ALL, 5)

		self.remove_btn = wx.Button(panel, label=_("&Remove"))
		self.remove_btn.Disable()
		sizer.Add(self.remove_btn, 0, wx.ALL, 5)

		self.Bind(
			wx.EVT_BUTTON,
			self.on_manage_organizations,
			self.manage_organizations,
		)
		self.Bind(wx.EVT_BUTTON, self.on_add, add_btn)
		self.Bind(wx.EVT_BUTTON, self.on_edit, self.edit_btn)
		self.Bind(wx.EVT_BUTTON, self.on_remove, self.remove_btn)

		bSizer = wx.BoxSizer(wx.HORIZONTAL)

		btn = wx.Button(panel, wx.ID_SAVE)
		btn.Bind(wx.EVT_BUTTON, self.on_save)
		bSizer.Add(btn, 0, wx.ALL, 5)

		btn = wx.Button(panel, wx.ID_CANCEL)
		btn.Bind(wx.EVT_BUTTON, self.onCancel)
		bSizer.Add(btn, 0, wx.ALL, 5)

		sizer.Add(bSizer, 0, wx.ALL, 5)

	def init_data(self):
		self.account_manager = conf.accounts.model_copy(deep=True)

	def _get_organization_name(self, account):
		if not account.active_organization:
			return _("No (personal)")
		return account.active_organization.name

	def update_data(self):
		for account in self.account_manager:
			self.account_list.Append(
				(
					account.name,
					account.provider.name,
					self._get_organization_name(account),
					self.account_source_labels.get(
						account.source, _("Unknown")
					),
				)
			)

	def update_ui(self):
		account = self.account_manager[self.account_list.GetFirstSelected()]
		log.debug(f"Selected account: {account}")
		editable = account.source != AccountSource.ENV_VAR
		self.edit_btn.Enable(editable)
		self.remove_btn.Enable(editable)
		self.manage_organizations.Enable(
			editable and account.provider.organization_mode_available
		)

	def on_item_selected(self, event):
		self.update_ui()

	def on_account_list_key_down(self, event: wx.KeyEvent):
		if event.GetKeyCode() == wx.WXK_RETURN:
			self.on_edit(event)
		elif event.GetKeyCode() == wx.WXK_DELETE:
			self.on_remove(event)
		else:
			event.Skip()

	def on_manage_organizations(self, event):
		index = self.account_list.GetFirstSelected()
		account = self.account_manager[index]
		dialog = AccountOrganizationDialog(
			self, _("Manage organizations"), account
		)
		if dialog.ShowModal() == wx.ID_OK:
			dialog.account.reset_active_organization()
			self.account_manager[index] = dialog.account
			self.account_list.SetItem(
				index, 2, self._get_organization_name(dialog.account)
			)
		dialog.Destroy()
		self.account_list.SetItemState(
			index,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
		)
		self.account_list.EnsureVisible(index)

	def on_add(self, event):
		dialog = EditAccountDialog(self, _("Add account"))
		if dialog.ShowModal() == wx.ID_OK:
			account = dialog.account
			self.account_manager.add(account)
			self.account_list.Append(
				(
					account.name,
					account.provider.name,
					self._get_organization_name(account),
					self.account_source_labels.get(
						account.source, _("Unknown")
					),
				)
			)
		dialog.Destroy()
		for i in range(self.account_list.GetItemCount()):
			self.account_list.Select(i, False)
		self.account_list.SetItemState(
			self.account_list.GetItemCount() - 1,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
		)
		self.account_list.EnsureVisible(self.account_list.GetItemCount() - 1)
		self.update_ui()

	def on_edit(self, event):
		index = self.account_list.GetFirstSelected()
		if index == -1:
			return
		account = self.account_manager[index]
		if account.source == AccountSource.ENV_VAR:
			msg = _("Cannot edit account from environment variable")
			wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
			return
		dialog = EditAccountDialog(self, _("Edit account"), account=account)
		if dialog.ShowModal() == wx.ID_OK:
			account = dialog.account
			account.reset_active_organization()
			self.account_manager[index] = account
			self.account_list.SetItem(index, 0, account.name)
			self.account_list.SetItem(index, 1, account.provider.name)
			self.account_list.SetItem(
				index, 2, self._get_organization_name(account)
			)
			self.account_list.SetItem(
				index,
				3,
				self.account_source_labels.get(account.source, _("Unknown")),
			)
		dialog.Destroy()
		self.account_list.SetItemState(
			index,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
		)
		self.account_list.EnsureVisible(index)
		self.update_ui()

	def on_remove(self, event):
		index = self.account_list.GetFirstSelected()
		if index == -1:
			return
		account = self.account_manager[index]
		account_name = account.name
		# Translators: A confirmation message in account dialog
		msg = _("Are you sure you want to remove the account {}?").format(
			account_name
		)
		if wx.MessageBox(msg, _("Confirmation"), wx.YES_NO) != wx.YES:
			return
		if account.source == AccountSource.ENV_VAR:
			msg = _("Cannot remove account from environment variable")
			wx.MessageBox(msg, _("Error"), wx.OK | wx.ICON_ERROR)
			return
		self.account_manager.remove(account)
		self.account_list.DeleteItem(index)

	def on_save(self, event):
		conf.accounts.clear()
		for account in self.account_manager:
			conf.accounts.add(account)
		conf.save()
		self.EndModal(wx.ID_OK)

	def onCancel(self, event):
		self.EndModal(wx.ID_CANCEL)
