from __future__ import annotations

import logging
import os
import re
import threading
import time
import weakref
from typing import TYPE_CHECKING, Optional
from uuid import UUID

import wx
from more_itertools import first, locate
from wx.lib.agw.floatspin import FloatSpin

import basilisk.config as config
from basilisk import global_vars
from basilisk.conversation import (
	Conversation,
	Message,
	MessageBlock,
	MessageRoleEnum,
	RequestParams,
)
from basilisk.gui.html_view_window import show_html_view_window
from basilisk.gui.search_dialog import SearchDialog, SearchDirection
from basilisk.image_file import URL_PATTERN, ImageFile, get_image_dimensions
from basilisk.message_segment_manager import (
	MessageSegment,
	MessageSegmentManager,
	MessageSegmentType,
)
from basilisk.provider_ai_model import ProviderAIModel
from basilisk.provider_capability import ProviderCapability
from basilisk.sound_manager import play_sound, stop_sound

if TYPE_CHECKING:
	from basilisk.provider_engine.base_engine import BaseEngine
	from basilisk.recording_thread import RecordingThread


log = logging.getLogger(__name__)


class FloatSpinTextCtrlAccessible(wx.Accessible):
	def __init__(self, win: wx.Window = None, name: str = None):
		super().__init__(win)
		self._name = name

	def GetName(self, childId):
		if self._name:
			return (wx.ACC_OK, self._name)
		return super().GetName(childId)


class ConversationTab(wx.Panel):
	ROLE_LABELS: dict[MessageRoleEnum, str] = {
		# Translators: Label indicating that the message is from the user in a conversation
		MessageRoleEnum.USER: _("User:") + ' ',
		# Translators: Label indicating that the message is from the assistant in a conversation
		MessageRoleEnum.ASSISTANT: _("Assistant:") + ' ',
	}

	def __init__(self, parent: wx.Window):
		wx.Panel.__init__(self, parent)
		self.SetStatusText = parent.GetParent().GetParent().SetStatusText
		self.conversation = Conversation()
		self.image_files = []
		self.last_time = 0
		self.message_segment_manager = MessageSegmentManager()
		self.recording_thread: Optional[RecordingThread] = None
		self.task = None
		self.stream_buffer = ""
		self._messages_already_focused = False
		self._stop_completion = False
		self._search_dialog = None
		self.accounts_engines: dict[UUID, BaseEngine] = {}
		self.init_ui()
		self.init_data()
		self.update_ui()

	def init_ui(self):
		sizer = wx.BoxSizer(wx.VERTICAL)

		label = wx.StaticText(
			self,
			# Translators: This is a label for account in the main window
			label=_("&Account:"),
		)
		sizer.Add(label, proportion=0, flag=wx.EXPAND)
		self.account_combo = wx.ComboBox(
			self, style=wx.CB_READONLY, choices=self.get_display_accounts()
		)
		self.account_combo.Bind(wx.EVT_COMBOBOX, self.on_account_change)
		if len(self.account_combo.GetItems()) > 0:
			self.account_combo.SetSelection(0)
		sizer.Add(self.account_combo, proportion=0, flag=wx.EXPAND)

		label = wx.StaticText(
			self,
			# Translators: This is a label for system prompt in the main window
			label=_("S&ystem prompt:"),
		)
		sizer.Add(label, proportion=0, flag=wx.EXPAND)
		self.system_prompt_txt = wx.TextCtrl(
			self,
			size=(800, 100),
			style=wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.HSCROLL,
		)
		sizer.Add(self.system_prompt_txt, proportion=1, flag=wx.EXPAND)

		label = wx.StaticText(
			self,
			# Translators: This is a label for user prompt in the main window
			label=_("&Messages:"),
		)
		sizer.Add(label, proportion=0, flag=wx.EXPAND)
		self.messages = wx.TextCtrl(
			self,
			size=(800, 400),
			style=wx.TE_MULTILINE
			| wx.TE_READONLY
			| wx.TE_WORDWRAP
			| wx.HSCROLL,
		)
		self.messages.Bind(wx.EVT_CONTEXT_MENU, self.on_messages_context_menu)
		self.messages.Bind(wx.EVT_KEY_DOWN, self.on_messages_key_down)
		sizer.Add(self.messages, proportion=1, flag=wx.EXPAND)

		label = wx.StaticText(
			self,
			# Translators: This is a label for user prompt in the main window
			label=_("&Prompt:"),
		)
		sizer.Add(label, proportion=0, flag=wx.EXPAND)
		self.prompt = wx.TextCtrl(
			self,
			size=(800, 100),
			style=wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.HSCROLL,
		)
		self.prompt.Bind(wx.EVT_KEY_DOWN, self.on_prompt_key_down)
		self.prompt.Bind(wx.EVT_CONTEXT_MENU, self.on_prompt_context_menu)
		self.prompt.Bind(wx.EVT_TEXT_PASTE, self.on_prompt_paste)
		sizer.Add(self.prompt, proportion=1, flag=wx.EXPAND)
		self.prompt.SetFocus()

		self.images_list_label = wx.StaticText(
			self,
			# Translators: This is a label for models in the main window
			label=_("&Images:"),
		)
		sizer.Add(self.images_list_label, proportion=0, flag=wx.EXPAND)
		self.images_list = wx.ListCtrl(
			self, size=(800, 100), style=wx.LC_REPORT
		)
		self.images_list.Bind(wx.EVT_CONTEXT_MENU, self.on_images_context_menu)
		self.images_list.Bind(wx.EVT_KEY_DOWN, self.on_images_key_down)
		self.images_list.InsertColumn(0, _("Name"))
		self.images_list.InsertColumn(1, _("Size"))
		self.images_list.InsertColumn(2, _("Dimensions"))
		self.images_list.InsertColumn(3, _("Path"))
		self.images_list.SetColumnWidth(0, 200)
		self.images_list.SetColumnWidth(1, 100)
		self.images_list.SetColumnWidth(2, 100)
		self.images_list.SetColumnWidth(3, 200)
		sizer.Add(self.images_list, proportion=0, flag=wx.ALL | wx.EXPAND)

		label = wx.StaticText(self, label=_("M&odels:"))
		sizer.Add(label, proportion=0, flag=wx.EXPAND)
		self.model_list = wx.ListCtrl(self, style=wx.LC_REPORT)
		self.model_list.InsertColumn(0, _("Name"))
		self.model_list.InsertColumn(1, _("Context window"))
		self.model_list.InsertColumn(2, _("Max tokens"))
		self.model_list.SetColumnWidth(0, 200)
		self.model_list.SetColumnWidth(1, 100)
		self.model_list.SetColumnWidth(2, 100)
		sizer.Add(self.model_list, proportion=0, flag=wx.ALL | wx.EXPAND)
		self.model_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_model_change)
		self.model_list.Bind(wx.EVT_KEY_DOWN, self.on_model_key_down)

		self.max_tokens_label = wx.StaticText(
			self,
			# Translators: This is a label for max tokens in the main window
			label=_("Max to&kens:"),
		)
		sizer.Add(self.max_tokens_label, proportion=0, flag=wx.EXPAND)
		self.max_tokens_spin_ctrl = wx.SpinCtrl(
			self, value='0', min=0, max=2000000
		)
		sizer.Add(self.max_tokens_spin_ctrl, proportion=0, flag=wx.EXPAND)

		self.temperature_label = wx.StaticText(
			self,
			# Translators: This is a label for temperature in the main window
			label=_("&Temperature:"),
		)
		sizer.Add(self.temperature_label, proportion=0, flag=wx.EXPAND)
		self.temperature_spinner = FloatSpin(
			self,
			min_val=0.0,
			max_val=2.0,
			increment=0.01,
			value=0.5,
			digits=2,
			name="temperature",
		)
		float_spin_accessible = FloatSpinTextCtrlAccessible(
			win=self.temperature_spinner._textctrl,
			name=self.temperature_label.GetLabel().replace("&", ""),
		)
		self.temperature_spinner._textctrl.SetAccessible(float_spin_accessible)
		sizer.Add(self.temperature_spinner, proportion=0, flag=wx.EXPAND)

		self.top_p_label = wx.StaticText(
			self,
			# Translators: This is a label for top P in the main window
			label=_("Probabilit&y Mass (top P):"),
		)
		sizer.Add(self.top_p_label, proportion=0, flag=wx.EXPAND)
		self.top_p_spinner = FloatSpin(
			self,
			min_val=0.0,
			max_val=1.0,
			increment=0.01,
			value=1.0,
			digits=2,
			name="Top P",
		)
		float_spin_accessible = FloatSpinTextCtrlAccessible(
			win=self.top_p_spinner._textctrl,
			name=self.top_p_label.GetLabel().replace("&", ""),
		)
		self.top_p_spinner._textctrl.SetAccessible(float_spin_accessible)
		sizer.Add(self.top_p_spinner, proportion=0, flag=wx.EXPAND)

		self.stream_mode = wx.CheckBox(
			self,
			# Translators: This is a label for stream mode in the main window
			label=_("&Stream mode"),
		)
		self.stream_mode.SetValue(True)
		sizer.Add(self.stream_mode, proportion=0, flag=wx.EXPAND)

		btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

		self.submit_btn = wx.Button(
			self,
			# Translators: This is a label for submit button in the main window
			label=_("Su&bmit (Ctrl+Enter)"),
		)
		self.submit_btn.Bind(wx.EVT_BUTTON, self.on_submit)
		self.submit_btn.SetDefault()
		btn_sizer.Add(self.submit_btn, proportion=0, flag=wx.EXPAND)

		self.stop_completion_btn = wx.Button(
			self,
			# Translators: This is a label for stop completion button in the main window
			label=_("Stop completio&n"),
		)
		self.stop_completion_btn.Bind(wx.EVT_BUTTON, self.on_stop_completion)
		btn_sizer.Add(self.stop_completion_btn, proportion=0, flag=wx.EXPAND)
		self.stop_completion_btn.Hide()

		self.toggle_record_btn = wx.Button(
			self,
			# Translators: This is a label for record button in the main window
			label=_("Record") + " (Ctrl+R)",
		)
		btn_sizer.Add(self.toggle_record_btn, proportion=0, flag=wx.EXPAND)
		self.toggle_record_btn.Bind(wx.EVT_BUTTON, self.toggle_recording)

		sizer.Add(btn_sizer, proportion=0, flag=wx.EXPAND)

		self.SetSizerAndFit(sizer)

	def init_data(self):
		self.on_account_change(None)
		self.on_model_change(None)
		self.refresh_images_list()

	def update_ui(self):
		unsupported_request_params = (
			self.current_engine.unsupported_request_params
		)
		control_params = {
			RequestParams.MAX_TOKENS: (
				self.max_tokens_label,
				self.max_tokens_spin_ctrl,
			),
			RequestParams.TEMPERATURE: (
				self.temperature_label,
				self.temperature_spinner,
			),
			RequestParams.TOP_P: (self.top_p_label, self.top_p_spinner),
			RequestParams.STREAM: (self.stream_mode,),
		}

		for param, controls in control_params.items():
			should_enabled = (
				config.conf.general.advanced_mode
				and param not in unsupported_request_params
			)
			for control in controls:
				control.Enable(should_enabled)
				control.Show(should_enabled)
		self.Layout()

	def on_account_change(self, event: wx.CommandEvent):
		account_index = self.account_combo.GetSelection()
		if account_index == wx.NOT_FOUND:
			if not config.conf.accounts:
				if (
					wx.MessageBox(
						_(
							"Please add an account first. Do you want to add an account now?"
						),
						_("No account configured"),
						wx.YES_NO | wx.ICON_QUESTION,
					)
					== wx.YES
				):
					self.GetParent().GetParent().GetParent().on_manage_accounts(
						None
					)
					self.on_config_change()
			return
		account = config.conf.accounts[account_index]
		self.accounts_engines.setdefault(
			account.id, account.provider.engine_cls(account)
		)
		self.model_list.DeleteAllItems()
		for i, model in enumerate(self.get_display_models()):
			self.model_list.InsertItem(i, model[0])
			self.model_list.SetItem(i, 1, model[1])
			self.model_list.SetItem(i, 2, model[2])
		self.model_list.SetItemState(
			0,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
			wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
		)
		self.toggle_record_btn.Enable(
			ProviderCapability.STT in account.provider.engine_cls.capabilities
		)
		self.update_ui()

	def on_images_context_menu(self, event: wx.ContextMenuEvent):
		selected = self.images_list.GetFirstSelected()
		menu = wx.Menu()

		if selected != wx.NOT_FOUND:
			item = wx.MenuItem(
				menu, wx.ID_ANY, _("Remove selected image") + " (Shift+Del)"
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_images_remove, item)

			item = wx.MenuItem(
				menu, wx.ID_ANY, _("Copy image URL") + " (Ctrl+C)"
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_copy_image_url, item)
		item = wx.MenuItem(
			menu, wx.ID_ANY, _("Paste (image or text)") + " (Ctrl+V)"
		)
		menu.Append(item)
		self.Bind(wx.EVT_MENU, self.on_image_paste, item)
		item = wx.MenuItem(menu, wx.ID_ANY, _("Add image files..."))
		menu.Append(item)
		self.Bind(wx.EVT_MENU, self.add_image_files, item)

		item = wx.MenuItem(menu, wx.ID_ANY, _("Add image URL..."))
		menu.Append(item)
		self.Bind(wx.EVT_MENU, self.add_image_url_dlg, item)

		self.images_list.PopupMenu(menu)
		menu.Destroy()

	def on_images_key_down(self, event: wx.KeyEvent):
		key_code = event.GetKeyCode()
		modifiers = event.GetModifiers()
		if modifiers == wx.MOD_CONTROL and key_code == ord("C"):
			self.on_copy_image_url(None)
		if modifiers == wx.MOD_CONTROL and key_code == ord("V"):
			self.on_image_paste(None)
		if modifiers == wx.MOD_NONE and key_code == wx.WXK_DELETE:
			self.on_images_remove(None)
		event.Skip()

	def on_image_paste(self, event: wx.CommandEvent):
		with wx.TheClipboard as clipboard:
			if clipboard.IsSupported(wx.DataFormat(wx.DF_FILENAME)):
				log.debug("Pasting files from clipboard")
				file_data = wx.FileDataObject()
				clipboard.GetData(file_data)
				paths = file_data.GetFilenames()
				self.add_images(paths)
			elif clipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
				log.debug("Pasting text from clipboard")
				text_data = wx.TextDataObject()
				clipboard.GetData(text_data)
				text = text_data.GetText()
				if re.fullmatch(URL_PATTERN, text):
					log.info("Pasting URL from clipboard, adding image")
					self.add_image_from_url(text)
				else:
					log.info("Pasting text from clipboard")
					self.prompt.WriteText(text)
					self.prompt.SetFocus()
			elif clipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP)):
				log.debug("Pasting bitmap from clipboard")
			else:
				log.info("Unsupported clipboard data")

	def add_image_files(self, event: wx.CommandEvent = None):
		file_dialog = wx.FileDialog(
			self,
			message=_("Select one or more image files"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE,
			wildcard=_("Image files")
			+ " (*.png;*.jpeg;*.jpg;*.gif)|*.png;*.jpeg;*.jpg;*.gif",
		)
		if file_dialog.ShowModal() == wx.ID_OK:
			paths = file_dialog.GetPaths()
			self.add_images(paths)
		file_dialog.Destroy()

	def add_image_url_dlg(self, event: wx.CommandEvent = None):
		url_dialog = wx.TextEntryDialog(
			self,
			# Translators: This is a label for image URL in conversation tab
			message=_("Enter the URL of the image:"),
			caption=_("Add image URL"),
		)
		if url_dialog.ShowModal() != wx.ID_OK:
			return
		url = url_dialog.GetValue()
		if not url:
			return
		if not re.fullmatch(URL_PATTERN, url):
			wx.MessageBox(
				_("Invalid URL, bad format."), _("Error"), wx.OK | wx.ICON_ERROR
			)
			return
		self.add_image_from_url(url)
		url_dialog.Destroy()

	def add_image_from_url(self, url: str):
		try:
			import urllib.request

			r = urllib.request.urlopen(url)
		except urllib.error.HTTPError as err:
			wx.MessageBox(
				# Translators: This message is displayed when the image URL returns an HTTP error.
				_("HTTP error %s.") % err,
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		if not r.headers.get_content_type().startswith("image/"):
			if (
				wx.MessageBox(
					# Translators: This message is displayed when the image URL seems to not point to an image.
					_(
						"The URL seems to not point to an image (content type: %s). Do you want to continue?"
					)
					% r.headers.get_content_type(),
					_("Warning"),
					wx.YES_NO | wx.ICON_WARNING | wx.NO_DEFAULT,
				)
				== wx.NO
			):
				return
		description = ''
		content_type = r.headers.get_content_type()
		if content_type:
			description = content_type
		size = r.headers.get("Content-Length")
		if size and size.isdigit():
			size = int(size)
		try:
			dimensions = get_image_dimensions(r)
		except BaseException as err:
			log.error(err)
			dimensions = None
			wx.MessageBox(
				_("Error getting image dimensions: %s") % err,
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
		self.add_images(
			[
				ImageFile(
					location=url,
					description=description,
					size=size,
					dimensions=dimensions,
				)
			]
		)

	def on_images_remove(self, event: wx.CommandEvent):
		selection = self.images_list.GetFirstSelected()
		if selection == wx.NOT_FOUND:
			return
		self.image_files.pop(selection)
		self.refresh_images_list()
		if selection >= self.images_list.GetItemCount():
			selection -= 1
		if selection >= 0:
			self.images_list.SetItemState(
				selection, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED
			)
		else:
			self.prompt.SetFocus()

	def on_copy_image_url(self, event: wx.CommandEvent):
		selected = self.images_list.GetFirstSelected()
		if selected == wx.NOT_FOUND:
			return
		url = self.image_files[selected].location
		with wx.TheClipboard as clipboard:
			clipboard.SetData(wx.TextDataObject(url))

	def on_model_change(self, event: wx.CommandEvent):
		model_index = self.model_list.GetFirstSelected()
		if model_index == wx.NOT_FOUND:
			return
		model = self.current_engine.models[model_index]
		self.temperature_spinner.SetMax(model.max_temperature)
		self.temperature_spinner.SetValue(model.default_temperature)
		max_tokens = model.max_output_tokens
		if max_tokens < 1:
			max_tokens = model.context_window
		self.max_tokens_spin_ctrl.SetMax(max_tokens)
		self.max_tokens_spin_ctrl.SetValue(0)

	def refresh_accounts(self):
		account_index = self.account_combo.GetSelection()
		account_id = None
		if account_index != wx.NOT_FOUND:
			account_id = config.conf.accounts[account_index].id
		self.account_combo.Clear()
		self.account_combo.AppendItems(self.get_display_accounts(True))
		account_index = first(
			locate(config.conf.accounts, lambda a: a.id == account_id),
			wx.NOT_FOUND,
		)
		if account_index != wx.NOT_FOUND:
			self.account_combo.SetSelection(account_index)
		elif self.account_combo.GetCount() > 0:
			self.account_combo.SetSelection(0)
			self.account_combo.SetFocus()

	def refresh_images_list(self):
		self.images_list.DeleteAllItems()
		if not self.image_files:
			self.images_list_label.Hide()
			self.images_list.Hide()
			self.Layout()
			return
		self.images_list_label.Show()
		self.images_list.Show()
		self.Layout()
		for i, image in enumerate(self.image_files):
			self.images_list.InsertItem(i, image.name)
			self.images_list.SetItem(i, 1, image.size)
			self.images_list.SetItem(
				i, 2, f"{image.dimensions[0]}x{image.dimensions[1]}"
			)
			self.images_list.SetItem(i, 3, image.display_location)
		self.images_list.SetItemState(
			i, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED
		)
		self.images_list.EnsureVisible(i)

	def add_images(self, path: list[str | ImageFile]):
		log.debug(f"Adding images: {path}")
		for path in path:
			if isinstance(path, ImageFile):
				self.image_files.append(path)
			else:
				self.image_files.append(ImageFile(path))
		self.refresh_images_list()

	def on_config_change(self):
		self.refresh_accounts()
		self.on_account_change(None)
		self.on_model_change(None)
		self.update_ui()

	def add_standard_context_menu_items(
		self, menu: wx.Menu, include_paste: bool = True
	):
		menu.Append(wx.ID_UNDO)
		menu.Append(wx.ID_REDO)
		menu.Append(wx.ID_CUT)
		menu.Append(wx.ID_COPY)
		if include_paste:
			menu.Append(wx.ID_PASTE)
		menu.Append(wx.ID_SELECTALL)

	def _do_search_in_messages(
		self, direction: SearchDirection = SearchDirection.FORWARD
	):
		if not self._search_dialog:
			self._search_dialog = SearchDialog(self, self.messages)
		self._search_dialog._dir_radio_forward.SetValue(
			direction == SearchDirection.FORWARD
		)
		self._search_dialog._dir_radio_backward.SetValue(
			direction == SearchDirection.BACKWARD
		)

		self._search_dialog._search_combo.SetFocus()
		self._search_dialog._search_combo.SelectAll()
		self._search_dialog.ShowModal()

	def on_search_in_messages(self, event: wx.CommandEvent = None):
		self._do_search_in_messages()

	def on_search_in_messages_previous(self, event: wx.CommandEvent = None):
		if not self._search_dialog:
			return self._do_search_in_messages(SearchDirection.BACKWARD)
		self._search_dialog.search_previous()

	def on_search_in_messages_next(self, event: wx.CommandEvent = None):
		if not self._search_dialog:
			return self._do_search_in_messages()
		self._search_dialog.search_next()

	def navigate_message(self, previous: bool):
		self.message_segment_manager.absolute_position = (
			self.messages.GetInsertionPoint()
		)
		try:
			if previous:
				self.message_segment_manager.previous(
					MessageSegmentType.CONTENT
				)
			else:
				self.message_segment_manager.next(MessageSegmentType.CONTENT)
		except IndexError:
			wx.Bell()
			return
		try:
			pos = self.message_segment_manager.start
		except IndexError:
			wx.Bell()
		else:
			self.messages.SetInsertionPoint(pos)
			if config.conf.conversation.nav_msg_select:
				self.select_current_message()

	def go_to_previous_message(self, event: wx.CommandEvent = None):
		self.navigate_message(True)

	def go_to_next_message(self, event: wx.CommandEvent = None):
		self.navigate_message(False)

	def move_to_start_of_message(self, event: wx.CommandEvent = None):
		cursor_pos = self.messages.GetInsertionPoint()
		self.message_segment_manager.absolute_position = cursor_pos
		self.message_segment_manager.focus_content_block()
		self.messages.SetInsertionPoint(self.message_segment_manager.start)

	def move_to_end_of_message(self, event: wx.CommandEvent = None):
		cursor_pos = self.messages.GetInsertionPoint()
		self.message_segment_manager.absolute_position = cursor_pos
		self.message_segment_manager.focus_content_block()
		self.messages.SetInsertionPoint(self.message_segment_manager.end - 1)

	def select_current_message(self):
		cursor_pos = self.messages.GetInsertionPoint()
		self.message_segment_manager.absolute_position = cursor_pos
		self.message_segment_manager.focus_content_block()
		start = self.message_segment_manager.start
		end = self.message_segment_manager.end
		self.messages.SetSelection(start, end)

	def on_select_message(self, event: wx.CommandEvent = None):
		self.select_current_message()

	def on_show_as_html(self, event: wx.CommandEvent = None):
		cursor_pos = self.messages.GetInsertionPoint()
		self.message_segment_manager.absolute_position = cursor_pos
		start = self.message_segment_manager.start
		end = self.message_segment_manager.end
		content = self.messages.GetRange(start, end)
		show_html_view_window(self, content, "markdown")

	def on_copy_message(self, event: wx.CommandEvent = None):
		cursor_pos = self.messages.GetInsertionPoint()
		self.select_current_message()
		self.messages.Copy()
		self.messages.SetInsertionPoint(cursor_pos)

	def on_remove_message_block(self, event: wx.CommandEvent = None):
		cursor_pos = self.messages.GetInsertionPoint()
		self.message_segment_manager.absolute_position = cursor_pos
		message_block = (
			self.message_segment_manager.current_segment.message_block()
		)
		if message_block:
			self.conversation.messages.remove(message_block)
			self.refresh_messages()
			self.messages.SetInsertionPoint(cursor_pos)
		else:
			wx.Bell()

	def on_messages_key_down(self, event: wx.KeyEvent = None):
		if not self.conversation.messages:
			event.Skip()
			return
		modifiers = event.GetModifiers()
		key_code = event.GetKeyCode()

		key_actions = {
			(wx.MOD_NONE, ord('J')): self.go_to_previous_message,
			(wx.MOD_NONE, ord('K')): self.go_to_next_message,
			(wx.MOD_NONE, ord('S')): self.on_select_message,
			(wx.MOD_NONE, ord('H')): self.on_show_as_html,
			(wx.MOD_NONE, ord('C')): self.on_copy_message,
			(wx.MOD_NONE, ord('B')): self.move_to_start_of_message,
			(wx.MOD_NONE, ord('N')): self.move_to_end_of_message,
			(wx.MOD_SHIFT, wx.WXK_DELETE): self.on_remove_message_block,
			(wx.MOD_NONE, wx.WXK_F3): self.on_search_in_messages_next,
			(wx.MOD_NONE, ord('F')): self.on_search_in_messages,
			(wx.MOD_CONTROL, ord('F')): self.on_search_in_messages,
			(wx.MOD_SHIFT, wx.WXK_F3): self.on_search_in_messages_previous,
		}

		action = key_actions.get((modifiers, key_code))

		if action:
			action()
		else:
			event.Skip()

	def on_messages_context_menu(self, event: wx.ContextMenuEvent):
		menu = wx.Menu()

		if self.conversation.messages:
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Find...") + " (&f)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_search_in_messages, item)
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Find Next") + " (F3)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_search_in_messages_next, item)
			item = wx.MenuItem(
				menu, wx.ID_ANY, _("Find Previous") + " (Shift+F3)"
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_search_in_messages_previous, item)

			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Show as HTML (from Markdown)") + " (&h)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_show_as_html, item)

			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Copy current message") + " (&c)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_copy_message, item)
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Select current message") + " (&s)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_select_message, item)
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Go to previous message") + " (&j)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.go_to_previous_message, item)
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Go to next message") + " (&k)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.go_to_next_message, item)
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Move to start of message") + " (&b)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.move_to_start_of_message, item)
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("Move to end of message") + " (&n)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.move_to_end_of_message, item)
			item = wx.MenuItem(
				menu,
				wx.ID_ANY,
				# Translators: This is a label for the Messages area context menu in the main window
				_("&Remove message block") + " (Shift+Del)",
			)
			menu.Append(item)
			self.Bind(wx.EVT_MENU, self.on_remove_message_block, item)
		self.add_standard_context_menu_items(menu)
		self.messages.PopupMenu(menu)
		menu.Destroy()

	def on_prompt_context_menu(self, event: wx.ContextMenuEvent):
		menu = wx.Menu()
		item = wx.MenuItem(
			menu, wx.ID_ANY, _("Insert previous prompt") + " (Ctrl+Up)"
		)
		menu.Append(item)
		self.Bind(wx.EVT_MENU, self.insert_previous_prompt, item)

		item = wx.MenuItem(menu, wx.ID_ANY, _("Submit") + " (Ctrl+Enter)")
		menu.Append(item)
		self.Bind(wx.EVT_MENU, self.on_submit, item)
		item = wx.MenuItem(
			menu, wx.ID_ANY, _("Paste (image or text)") + " (Ctrl+V)"
		)
		menu.Append(item)
		self.Bind(wx.EVT_MENU, self.on_prompt_paste, item)

		self.add_standard_context_menu_items(menu, include_paste=False)
		self.prompt.PopupMenu(menu)
		menu.Destroy()

	def on_prompt_key_down(self, event: wx.KeyEvent):
		key_code = event.GetKeyCode()
		modifiers = event.GetModifiers()
		if (
			modifiers == wx.ACCEL_CTRL
			and key_code == wx.WXK_UP
			and not self.prompt.GetValue()
		):
			self.insert_previous_prompt()
		elif modifiers == wx.ACCEL_CTRL and key_code == wx.WXK_RETURN:
			self.on_submit(event)
		event.Skip()

	def on_prompt_paste(self, event):
		self.on_image_paste(event)

	def on_model_key_down(self, event: wx.KeyEvent):
		if event.GetKeyCode() == wx.WXK_RETURN:
			self.on_submit(event)
		event.Skip()

	def on_key_down(self, event: wx.KeyEvent):
		if (
			event.GetModifiers() == wx.ACCEL_CTRL
			and event.GetKeyCode() == wx.WXK_RETURN
		):
			self.on_submit(event)
		event.Skip()

	def insert_previous_prompt(self, event: wx.CommandEvent = None):
		if self.conversation.messages:
			last_user_message = self.conversation.messages[-1].request.content
			self.prompt.SetValue(last_user_message)

	def get_display_accounts(self, force_refresh: bool = False) -> list[str]:
		accounts = []
		for account in config.conf.accounts:
			if force_refresh:
				if "active_organization" in account.__dict__:
					del account.__dict__["active_organization"]
			name = account.name
			organization = (
				account.active_organization.name
				if account.active_organization
				else _("Personal")
			)
			provider_name = account.provider.name
			accounts.append(f"{name} ({organization}) - {provider_name}")
		return accounts

	def extract_text_from_message(
		self, content: list[ImageFile | str] | str
	) -> str:
		text = ""
		for item in content:
			if isinstance(item, str):
				text += item
		return text

	def append_text_and_create_segment(
		self, text, segment_type, new_block_ref, absolute_length
	):
		self.messages.AppendText(text)
		relative_length = self.messages.GetLastPosition() - absolute_length
		absolute_length = self.messages.GetLastPosition()
		self.message_segment_manager.append(
			MessageSegment(
				length=relative_length,
				kind=segment_type,
				message_block=new_block_ref,
			)
		)
		return absolute_length

	def display_new_block(self, new_block: MessageBlock):
		absolute_length = self.messages.GetLastPosition()
		new_block_ref = weakref.ref(new_block)

		if not self.messages.IsEmpty():
			absolute_length = self.append_text_and_create_segment(
				os.linesep,
				MessageSegmentType.SUFFIX,
				new_block_ref,
				absolute_length,
			)

		role_label = (
			config.conf.conversation.role_label_user
			or self.ROLE_LABELS[new_block.request.role]
		)
		absolute_length = self.append_text_and_create_segment(
			role_label,
			MessageSegmentType.PREFIX,
			new_block_ref,
			absolute_length,
		)

		content = self.extract_text_from_message(new_block.request.content)
		absolute_length = self.append_text_and_create_segment(
			content, MessageSegmentType.CONTENT, new_block_ref, absolute_length
		)

		absolute_length = self.append_text_and_create_segment(
			os.linesep,
			MessageSegmentType.SUFFIX,
			new_block_ref,
			absolute_length,
		)

		pos = self.messages.GetInsertionPoint()

		if new_block.response:
			role_label = (
				config.conf.conversation.role_label_assistant
				or self.ROLE_LABELS[new_block.response.role]
			)
			absolute_length = self.append_text_and_create_segment(
				role_label,
				MessageSegmentType.PREFIX,
				new_block_ref,
				absolute_length,
			)

			content = self.extract_text_from_message(new_block.response.content)
			absolute_length = self.append_text_and_create_segment(
				content,
				MessageSegmentType.CONTENT,
				new_block_ref,
				absolute_length,
			)

		self.messages.SetInsertionPoint(pos)

	def refresh_messages(self):
		self.messages.Clear()
		self.message_segment_manager.clear()
		self.image_files.clear()
		self.refresh_images_list()
		for block in self.conversation.messages:
			self.display_new_block(block)

	@property
	def current_engine(self) -> BaseEngine:
		account_index = self.account_combo.GetSelection()
		account = config.conf.accounts[account_index]
		return self.accounts_engines[account.id]

	@property
	def current_model(self) -> ProviderAIModel:
		model_index = self.model_list.GetFirstSelected()
		if model_index == wx.NOT_FOUND:
			return
		return self.current_engine.models[model_index]

	def get_display_models(self) -> list[tuple[str, str, str]]:
		return [m.display_model for m in self.current_engine.models]

	def get_content_for_completion(
		self, images_files: list[ImageFile] = None, prompt: str = None
	) -> list[dict[str, str]]:
		if not images_files:
			images_files = self.image_files
		content = []
		if prompt:
			content.append(prompt)
		if images_files:
			content.extend(images_files)
		return content

	def transcribe_audio_file(self, audio_file: str = None):
		if not self.recording_thread:
			module = __import__(
				"basilisk.recording_thread", fromlist=["RecordingThread"]
			)
			recording_thread_cls = getattr(module, "RecordingThread")
		else:
			recording_thread_cls = self.recording_thread.__class__
		self.recording_thread = recording_thread_cls(
			provider_engine=self.current_engine,
			recordings_settings=config.conf.recordings,
			conversation_tab=self,
			audio_file_path=audio_file,
		)
		self.recording_thread.start()

	def on_transcribe_audio_file(self):
		cur_provider = self.current_engine
		if ProviderCapability.STT not in cur_provider.capabilities:
			wx.MessageBox(
				_("The selected provider does not support speech-to-text"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		dlg = wx.FileDialog(
			self,
			# Translators: This is a label for audio file in the main window
			message=_("Select an audio file to transcribe"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
			wildcard=_("Audio files")
			+ " (*.mp3;*.mp4;*.mpeg;*.mpga;*.m4a;*.wav;*.webm)|*.mp3;*.mp4;*.mpeg;*.mpga;*.m4a;*.wav;*.webm",
		)
		if dlg.ShowModal() == wx.ID_OK:
			audio_file = dlg.GetPath()
			dlg.Destroy()
			self.transcribe_audio_file(audio_file)
		else:
			dlg.Destroy()

	def on_recording_started(self):
		play_sound("recording_started")
		self.SetStatusText(_("Recording..."))

	def on_recording_stopped(self):
		play_sound("recording_stopped")
		self.SetStatusText(_("Recording stopped"))

	def on_transcription_started(self):
		play_sound("progress", loop=True)
		self.SetStatusText(_("Transcribing..."))

	def on_transcription_received(self, transcription):
		stop_sound()
		self.SetStatusText(_("Ready"))
		self.prompt.AppendText(transcription.text)
		self.prompt.SetInsertionPointEnd()
		self.prompt.SetFocus()

	def on_transcription_error(self, error):
		stop_sound()
		self.SetStatusText(_("Ready"))
		wx.MessageBox(
			_("An error occurred during transcription: ") + str(error),
			_("Error"),
			wx.OK | wx.ICON_ERROR,
		)

	def toggle_recording(self, event: wx.CommandEvent):
		if self.recording_thread and self.recording_thread.is_alive():
			self.stop_recording()
		else:
			self.start_recording()

	def start_recording(self):
		cur_provider = self.current_engine
		if ProviderCapability.STT not in cur_provider.capabilities:
			wx.MessageBox(
				_("The selected provider does not support speech-to-text"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		self.toggle_record_btn.SetLabel(_("Stop recording") + " (Ctrl+R)")
		self.submit_btn.Disable()
		self.transcribe_audio_file()

	def stop_recording(self):
		self.recording_thread.stop()
		self.toggle_record_btn.SetLabel(_("Record") + " (Ctrl+R)")
		self.submit_btn.Enable()

	def on_submit(self, event: wx.CommandEvent):
		if not self.prompt.GetValue() and not self.image_files:
			self.prompt.SetFocus()
			return
		model = self.current_model
		if not model:
			wx.MessageBox(
				_("Please select a model"), _("Error"), wx.OK | wx.ICON_ERROR
			)
			return
		if self.image_files and not model.vision:
			vision_models = ", ".join(
				[m.name or m.id for m in self.current_engine.models if m.vision]
			)
			wx.MessageBox(
				_(
					"The selected model does not support images. Please select a vision model instead ({})."
				).format(vision_models),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		self.submit_btn.Disable()
		self.stop_completion_btn.Show()
		system_message = None
		if self.system_prompt_txt.GetValue():
			system_message = Message(
				role=MessageRoleEnum.SYSTEM,
				content=self.system_prompt_txt.GetValue(),
			)
		new_block = MessageBlock(
			request=Message(
				role=MessageRoleEnum.USER,
				content=self.get_content_for_completion(
					images_files=self.image_files, prompt=self.prompt.GetValue()
				),
			),
			model=model,
		)
		unsupported_request_params = (
			self.current_engine.unsupported_request_params
		)
		if RequestParams.MAX_TOKENS not in unsupported_request_params:
			new_block.max_tokens = self.max_tokens_spin_ctrl.GetValue()
		if RequestParams.TEMPERATURE not in unsupported_request_params:
			new_block.temperature = self.temperature_spinner.GetValue()
		if RequestParams.TOP_P not in unsupported_request_params:
			new_block.top_p = self.top_p_spinner.GetValue()
		new_block.stream = (
			RequestParams.STREAM not in unsupported_request_params
			and self.stream_mode.GetValue()
		)
		completion_kw = {
			"engine": self.current_engine,
			"system_message": system_message,
			"conversation": self.conversation,
			"new_block": new_block,
			"stream": new_block.stream,
		}
		if self.task:
			wx.MessageBox(
				_("A task is already running. Please wait for it to complete."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		thread = self.task = threading.Thread(
			target=self._handle_completion, kwargs=completion_kw
		)
		thread.start()
		thread_id = thread.ident
		log.debug(f"Task {thread_id} started")

	def on_stop_completion(self, event: wx.CommandEvent):
		self._stop_completion = True

	def _handle_completion(self, engine: BaseEngine, **kwargs):
		try:
			play_sound("progress", loop=True)
			response = engine.completion(**kwargs)
		except Exception as e:
			log.error("Error during completion", exc_info=True)

			wx.CallAfter(
				wx.MessageBox,
				_("An error occurred during completion: ") + str(e),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			wx.CallAfter(self._end_task, False)
			return
		new_block = kwargs["new_block"]
		if kwargs.get("stream", False):
			new_block.response = Message(role=MessageRoleEnum.ASSISTANT)
			wx.CallAfter(self._pre_handle_completion_with_stream, new_block)
			for chunk in self.current_engine.completion_response_with_stream(
				response
			):
				if self._stop_completion or global_vars.app_should_exit:
					log.debug("Stopping completion")
					break
				new_block.response.content += chunk
				wx.CallAfter(self._handle_completion_with_stream, chunk)
			wx.CallAfter(self._post_completion_with_stream, new_block)
		else:
			new_block = engine.completion_response_without_stream(
				response=response, **kwargs
			)
			wx.CallAfter(self._post_completion_without_stream, new_block)

	def _pre_handle_completion_with_stream(self, new_block: MessageBlock):
		self.conversation.messages.append(new_block)
		self.display_new_block(new_block)
		self.messages.SetInsertionPointEnd()
		self.prompt.Clear()
		self.image_files.clear()
		self.refresh_images_list()

	def _handle_completion_with_stream(self, chunk: str):
		self.stream_buffer += chunk
		if '\n' in chunk or len(self.stream_buffer) > 120:
			self._flush_stream_buffer()
			if not self._messages_already_focused:
				self.messages.SetFocus()
				self._messages_already_focused = True
		new_time = time.time()
		if new_time - self.last_time > 4:
			play_sound("chat_response_pending")
			self.last_time = new_time

	def _flush_stream_buffer(self):
		pos = self.messages.GetInsertionPoint()
		self.messages.AppendText(self.stream_buffer)
		self.stream_buffer = ""
		self.messages.SetInsertionPoint(pos)

	def _update_last_segment_length(self):
		last_position = self.messages.GetLastPosition()
		self.message_segment_manager.absolute_position = last_position
		last_segment = self.message_segment_manager.segments[-1]
		last_segment.length += last_position - self.message_segment_manager.end

	def _post_completion_with_stream(self, new_block: MessageBlock):
		self._flush_stream_buffer()
		self._update_last_segment_length()
		self._end_task()
		self._messages_already_focused = False

	def _post_completion_without_stream(self, new_block: MessageBlock):
		self._end_task()
		self.conversation.messages.append(new_block)
		self.display_new_block(new_block)
		self.prompt.Clear()
		self.image_files.clear()
		self.refresh_images_list()

	def _end_task(self, success: bool = True):
		if not self._messages_already_focused:
			self.messages.SetFocus()
			self._messages_already_focused = True
		task = self.task
		task.join()
		thread_id = task.ident
		log.debug(f"Task {thread_id} ended")
		self.task = None
		stop_sound()
		if success:
			play_sound("chat_response_received")
		self.stop_completion_btn.Hide()
		self.submit_btn.Enable()
		self._stop_completion = False
