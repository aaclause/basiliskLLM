from logging import getLogger

import wx

from basilisk.conversation_profile import (
	ConversationProfile,
	ConversationProfileManager,
)

log = getLogger(__name__)


class EditConversationProfileDialog(wx.Dialog):
	def __init__(
		self, parent, title, size=(400, 400), profil: ConversationProfile = None
	):
		super().__init__(parent, title=title, size=size)
		self.profil = profil or ConversationProfile.get_default()
		self.init_ui()
		self.init_data()

	def init_ui(self):
		self.panel = wx.Panel(self)
		self.sizer = wx.BoxSizer(wx.VERTICAL)

		self.name_label = wx.StaticText(self.panel, label="Name:")
		self.name_text = wx.TextCtrl(self.panel, value=self.profil.name)
		self.sizer.Add(self.name_label, 0, wx.ALL, 5)
		self.sizer.Add(self.name_text, 0, wx.ALL | wx.EXPAND, 5)

		self.prompt_label = wx.StaticText(self.panel, label="System Prompt:")
		self.prompt_text = wx.TextCtrl(
			self.panel, value=self.profil.system_prompt, style=wx.TE_MULTILINE
		)
		self.sizer.Add(self.prompt_label, 0, wx.ALL, 5)
		self.sizer.Add(self.prompt_text, 1, wx.ALL | wx.EXPAND, 5)

		self.ok_button = wx.Button(self.panel, wx.ID_OK, label="OK")
		self.cancel_button = wx.Button(self.panel, wx.ID_CANCEL, label="Cancel")
		self.sizer.Add(self.ok_button, 0, wx.ALL | wx.ALIGN_CENTER, 5)
		self.sizer.Add(self.cancel_button, 0, wx.ALL | wx.ALIGN_CENTER, 5)

		self.panel.SetSizerAndFit(self.sizer)
		self.Bind(wx.EVT_BUTTON, self.on_ok, self.ok_button)
		self.Bind(wx.EVT_BUTTON, self.on_cancel, self.cancel_button)

	def init_data(self):
		self.name_text.SetValue(self.profil.name)
		self.prompt_text.SetValue(self.profil.system_prompt)

	def on_ok(self, event):
		self.profil.name = self.name_text.GetValue()
		self.profil.system_prompt = self.prompt_text.GetValue()
		self.EndModal(wx.ID_OK)

	def on_cancel(self, event):
		self.EndModal(wx.ID_CANCEL)


class ConversationProfileDialog(wx.Dialog):
	"""Manage conversation profiles"""

	def __init__(self, parent, title, size=(400, 400)):
		super().__init__(parent, title=title, size=size)
		self.profil_manager = ConversationProfileManager()
		self.init_ui()
		self.init_data()

	def init_ui(self):
		self.panel = wx.Panel(self)
		self.sizer = wx.BoxSizer(wx.VERTICAL)

		self.list_ctrl = wx.ListCtrl(self.panel, style=wx.LC_REPORT)
		self.list_ctrl.InsertColumn(0, "Name", width=140)
		self.list_ctrl.InsertColumn(1, "System Prompt", width=240)
		self.sizer.Add(self.list_ctrl, 1, wx.ALL | wx.EXPAND, 5)

		self.add_button = wx.Button(self.panel, label="Add")
		self.edit_button = wx.Button(self.panel, label="Edit")
		self.remove_button = wx.Button(self.panel, label="Remove")
		self.save_button = wx.Button(self.panel, label="Save")
		self.cancel_button = wx.Button(self.panel, label="Cancel")

		self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.button_sizer.Add(self.add_button, 0, wx.ALL, 5)
		self.button_sizer.Add(self.edit_button, 0, wx.ALL, 5)
		self.button_sizer.Add(self.remove_button, 0, wx.ALL, 5)
		self.button_sizer.Add(self.save_button, 0, wx.ALL, 5)
		self.button_sizer.Add(self.cancel_button, 0, wx.ALL, 5)

		self.sizer.Add(self.button_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 5)
		self.panel.SetSizerAndFit(self.sizer)

		self.Bind(wx.EVT_BUTTON, self.on_add, self.add_button)
		self.Bind(wx.EVT_BUTTON, self.on_edit, self.edit_button)
		self.Bind(wx.EVT_BUTTON, self.on_remove, self.remove_button)
		self.Bind(wx.EVT_BUTTON, self.on_save, self.save_button)
		self.Bind(wx.EVT_BUTTON, self.on_cancel, self.cancel_button)
		self.Bind(
			wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected, self.list_ctrl
		)

	def init_data(self):
		self.update_ui()

	def update_ui(self):
		self.list_ctrl.DeleteAllItems()
		for i, profil in enumerate(self.profil_manager.root):
			self.list_ctrl.InsertItem(i, profil.name)
			self.list_ctrl.SetItem(i, 1, profil.system_prompt)

	def on_item_selected(self, event):
		self.selected_index = event.GetIndex()

	def on_add(self, event):
		dialog = EditConversationProfileDialog(self, "Add Conversation Profile")
		if dialog.ShowModal() == wx.ID_OK:
			self.profil_manager.root.append(dialog.profil)
			self.update_ui()

	def on_edit(self, event):
		index = self.list_ctrl.GetFirstSelected()
		if index != wx.NOT_FOUND:
			profil = self.profil_manager.root[index]
			dialog = EditConversationProfileDialog(
				self, "Edit Conversation Profile", profil=profil
			)
			if dialog.ShowModal() == wx.ID_OK:
				self.profil_manager.root[index] = dialog.profil
				self.update_ui()

	def on_remove(self, event):
		index = self.list_ctrl.GetFirstSelected()
		if index != wx.NOT_FOUND:
			del self.profil_manager.root[index]
			self.update_ui()

	def on_save(self, event):
		# Implement saving logic here
		self.EndModal(wx.ID_OK)

	def on_cancel(self, event):
		self.EndModal(wx.ID_CANCEL)
