import re
from enum import Enum
from typing import List

import wx

from basilisk.utils import get_corrected_position


class SearchDirection(Enum):
	BACKWARD = 0
	FORWARD = 1


class SearchMode(Enum):
	PLAIN_TEXT = 0
	EXTENDED = 1
	REGEX = 2


class SearchDialog(wx.Dialog):
	def __init__(
		self,
		parent: wx.Window,
		text: wx.TextCtrl,
		title: str = _("Search"),
		search_list: List[str] = [],
	) -> None:
		super().__init__(
			parent,
			title=title,
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
		)
		self._text = text
		self._search_list = search_list
		self._search_direction = SearchDirection.FORWARD
		self._search_mode = SearchMode.PLAIN_TEXT
		self._case_sensitive = False
		self._search_dot_all = False
		self._create_ui()
		self._bind_events()
		self._apply_initial_values()
		self._search_text.SetFocus()

	def _create_ui(self) -> None:
		main_sizer = wx.BoxSizer(wx.VERTICAL)

		search_text_sizer = wx.BoxSizer(wx.HORIZONTAL)
		search_label = wx.StaticText(self, label=_("Search for:"))
		self._search_text = wx.TextCtrl(self)
		search_text_sizer.Add(search_label, flag=wx.ALL | wx.CENTER, border=5)
		search_text_sizer.Add(
			self._search_text, proportion=1, flag=wx.ALL | wx.EXPAND, border=5
		)
		main_sizer.Add(search_text_sizer, flag=wx.EXPAND)

		direction_box = wx.StaticBox(self, label="Direction")
		direction_sizer = wx.StaticBoxSizer(direction_box, wx.HORIZONTAL)

		self._dir_radio_backward = wx.RadioButton(
			self, label="Backward", style=wx.RB_GROUP
		)
		self._dir_radio_forward = wx.RadioButton(self, label="Forward")

		direction_sizer.Add(self._dir_radio_backward, flag=wx.ALL, border=5)
		direction_sizer.Add(self._dir_radio_forward, flag=wx.ALL, border=5)

		main_sizer.Add(direction_sizer, flag=wx.ALL | wx.EXPAND, border=10)

		mode_box = wx.StaticBox(self, label="Mode")
		mode_sizer = wx.StaticBoxSizer(mode_box, wx.HORIZONTAL)

		self._mode_radio_plain = wx.RadioButton(
			self, label="Plain Text", style=wx.RB_GROUP
		)
		self._mode_radio_extended = wx.RadioButton(
			self, label="Extended (\n, \t, \r...)"
		)
		self._mode_radio_regex = wx.RadioButton(self, label="Regex")

		mode_sizer.Add(self._mode_radio_plain, flag=wx.ALL, border=5)
		mode_sizer.Add(self._mode_radio_extended, flag=wx.ALL, border=5)
		mode_sizer.Add(self._mode_radio_regex, flag=wx.ALL, border=5)

		main_sizer.Add(mode_sizer, flag=wx.ALL | wx.EXPAND, border=10)

		self._search_dot_all_checkbox = wx.CheckBox(
			self, label=_("Dot matches all (.)")
		)
		main_sizer.Add(
			self._search_dot_all_checkbox, flag=wx.ALL | wx.CENTER, border=5
		)
		self._search_dot_all_checkbox.Hide()

		self._case_sensitive_checkbox = wx.CheckBox(
			self, label=_("Case Sensitive")
		)
		main_sizer.Add(
			self._case_sensitive_checkbox, flag=wx.ALL | wx.CENTER, border=5
		)

		button_sizer = wx.StdDialogButtonSizer()
		self._find_button = wx.Button(self, wx.ID_FIND, _("Find"))
		self._find_button.SetDefault()
		button_sizer.AddButton(self._find_button)
		self._close_button = wx.Button(self, wx.ID_CANCEL)
		button_sizer.AddButton(self._close_button)
		button_sizer.Realize()
		main_sizer.Add(button_sizer, flag=wx.ALL | wx.ALIGN_CENTER, border=5)

		self.SetSizerAndFit(main_sizer)

	def _bind_events(self) -> None:
		self._find_button.Bind(wx.EVT_BUTTON, self._on_find)
		self._mode_radio_plain.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
		self._mode_radio_extended.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
		self._mode_radio_regex.Bind(wx.EVT_RADIOBUTTON, self._on_mode_change)
		self.Bind(wx.EVT_CLOSE, self._on_close)

	def _apply_initial_values(self) -> None:
		self._dir_radio_forward.SetValue(
			self._search_direction == SearchDirection.FORWARD
		)
		self._dir_radio_backward.SetValue(
			self._search_direction == SearchDirection.BACKWARD
		)
		self._mode_radio_plain.SetValue(
			self._search_mode == SearchMode.PLAIN_TEXT
		)
		self._mode_radio_extended.SetValue(
			self._search_mode == SearchMode.EXTENDED
		)
		self._mode_radio_regex.SetValue(self._search_mode == SearchMode.REGEX)
		self._case_sensitive_checkbox.SetValue(self._case_sensitive)
		self._search_dot_all_checkbox.SetValue(self._search_dot_all)
		self._update_dot_all_visibility()

	def _update_dot_all_visibility(self) -> None:
		if self._mode_radio_regex.GetValue():
			self._search_dot_all_checkbox.Show()
		else:
			self._search_dot_all_checkbox.Hide()
		self.Layout()

	def _compile_search_pattern(self, search_text: str) -> re.Pattern:
		flags = 0 if self._case_sensitive else re.IGNORECASE
		flags |= re.UNICODE
		if self._search_dot_all and self._search_mode == SearchMode.REGEX:
			flags |= re.DOTALL
		if self._search_mode == SearchMode.EXTENDED:
			search_text = (
				search_text.replace(r'\n', '\n')
				.replace(r'\t', '\t')
				.replace(r'\r', '\r')
				.replace(r'\x00', '\x00')
				.replace(r'\x1F', '\x1f')
				.replace(r'\x7F', '\x7f')
			)
		return re.compile(search_text, flags)

	def _find_matches(self, search_text: str) -> List[re.Match]:
		text_content = self._text.GetValue()
		if not self._case_sensitive:
			text_content = text_content.lower()
			search_text = search_text.lower()

		if self._search_mode in {SearchMode.PLAIN_TEXT, SearchMode.EXTENDED}:
			search_pattern = (
				re.escape(search_text)
				if self._search_mode == SearchMode.PLAIN_TEXT
				else search_text
			)
		else:
			search_pattern = search_text

		pattern = self._compile_search_pattern(search_pattern)
		return list(pattern.finditer(text_content))

	def _select_text(self, start: int, end: int):
		self._text.SetSelection(start, end)
		self._text.SetFocus()

	def _on_find(self, event: wx.Event) -> None:
		if self.IsModal():
			self.EndModal(wx.ID_OK)
		search_text = self._search_text.GetValue().strip()
		if not search_text:
			wx.MessageBox(
				_("Please enter text to search for."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		self._case_sensitive = self._case_sensitive_checkbox.GetValue()
		self._search_dot_all = self._search_dot_all_checkbox.GetValue()
		self._search_direction = (
			SearchDirection.BACKWARD
			if self._dir_radio_backward.GetValue()
			else SearchDirection.FORWARD
		)
		self._search_mode = (
			SearchMode.PLAIN_TEXT
			if self._mode_radio_plain.GetValue()
			else SearchMode.EXTENDED
			if self._mode_radio_extended.GetValue()
			else SearchMode.REGEX
		)

		matches = self._find_matches(search_text)
		if not matches:
			wx.MessageBox(
				_('"{search_text}" not found.').format(search_text=search_text),
				_("Search Result"),
				wx.OK | wx.ICON_INFORMATION,
			)
			return

		cursor_pos = get_corrected_position(
			self._text.GetInsertionPoint(), self._text.GetValue(), reverse=True
		)
		match_positions = [(match.start(), match.end()) for match in matches]

		if self._search_direction == SearchDirection.FORWARD:
			for start, end in match_positions:
				if start > cursor_pos:
					start = get_corrected_position(start, self._text.GetValue())
					end = get_corrected_position(end, self._text.GetValue())
					self._select_text(start, end)
					return
		else:
			for start, end in reversed(match_positions):
				if end < cursor_pos:
					start = get_corrected_position(start, self._text.GetValue())
					end = get_corrected_position(end, self._text.GetValue())
					self._select_text(start, end)
					return

		wx.MessageBox(
			_('"{search_text}" not found.').format(search_text=search_text),
			_("Search Result"),
			wx.OK | wx.ICON_INFORMATION,
		)

	def _on_close(self, event: wx.Event) -> None:
		self.EndModal(wx.ID_CANCEL)

	def _on_mode_change(self, event: wx.Event) -> None:
		self._update_dot_all_visibility()

	@property
	def search_direction(self) -> SearchDirection:
		return self._search_direction

	@search_direction.setter
	def search_direction(self, value: SearchDirection) -> None:
		if value not in {SearchDirection.BACKWARD, SearchDirection.FORWARD}:
			raise ValueError("search_direction must be a SearchDirection")
		self._search_direction = value

	def search_previous(self) -> None:
		self._dir_radio_backward.SetValue(True)
		self._on_find(None)

	def search_next(self) -> None:
		self._dir_radio_forward.SetValue(True)
		self._on_find(None)
