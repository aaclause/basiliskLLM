import datetime
import logging
import os
import signal
import sys
import tempfile
import wx

if sys.platform == 'win32':
	import win32con
import basilisk.config as config
from basilisk import global_vars
from basilisk.consts import APP_NAME, APP_SOURCE_URL, HotkeyAction
from basilisk.image_file import ImageFile
from basilisk.logger import get_log_file_path
from basilisk.screen_capture_thread import ScreenCaptureThread, CaptureMode
from basilisk.updater import BaseUpdater
from .conversation_tab import ConversationTab
from .taskbar_icon import TaskBarIcon
from .update_dialog import UpdateDialog, DownloadUpdateDialog

log = logging.getLogger(__name__)


class MainFrame(wx.Frame):
	def __init__(self, *args, **kwargs):
		self.conf: config.BasiliskConfig = kwargs.pop("conf")
		self.tmp_files = []
		super(MainFrame, self).__init__(*args, **kwargs)
		log.debug("Initializing main frame")
		self.init_ui()
		self.ID_NEW_CONVERSATION = wx.NewIdRef()
		self.ID_CLOSE_CONVERSATION = wx.NewIdRef()
		self.ID_ADD_IMAGE_FILE = wx.NewIdRef()
		self.ID_ADD_URL_IMAGE = wx.NewIdRef()
		self.ID_MANAGE_ACCOUNTS = wx.NewIdRef()
		self.ID_PREFERENCES = wx.NewIdRef()
		self.ID_VIEW_LOG = wx.NewIdRef()
		self.ID_TOGGLE_RECORDING = wx.NewIdRef()
		self.ID_TRANSCRIBE_AUDIO = wx.NewIdRef()

		self.init_accelerators()
		if sys.platform == "win32":
			self.tray_icon = TaskBarIcon(self)
			self.register_hot_key()
			self.Bind(wx.EVT_HOTKEY, self.on_hotkey)
		self.on_new_conversation(None)

	def init_ui(self):
		def update_item_label_suffix(item: wx.MenuItem, suffix: str = "..."):
			"""
			Update the label of the given item to include ellipsis at the end if not already present.

			:param item: The item whose label is to be updated.
			:param suffix: The suffix to add to the label.
			"""
			if not item.GetItemLabel().endswith(suffix):
				item.SetItemLabel(item.GetItemLabel() + suffix)

		menu_bar = wx.MenuBar()

		conversation_menu = wx.Menu()
		new_conversation_item = conversation_menu.Append(
			wx.ID_ANY,
			# Translators: A label for a menu item to create a new conversation
			_("New conversation") + " (Ctrl+N)",
		)
		self.Bind(wx.EVT_MENU, self.on_new_conversation, new_conversation_item)
		open_conversation_item = conversation_menu.Append(
			wx.ID_ANY,
			# Translators: A label for a menu item to open a conversation
			_("Open conversation") + "... (Ctrl+O)",
		)
		open_conversation_item.Enable(False)
		save_conversation_item = conversation_menu.Append(
			wx.ID_ANY,
			# Translators: A label for a menu item to save a conversation
			_("Save conversation") + " (Ctrl+S)",
		)
		save_conversation_item.Enable(False)
		save_as_conversation_item = conversation_menu.Append(
			wx.ID_ANY,
			# Translators: A label for a menu item to save a conversation as a new file
			_("Save conversation as") + "... (Ctrl+Shift+S)",
		)
		save_as_conversation_item.Enable(False)
		close_conversation_item = conversation_menu.Append(
			wx.ID_ANY, _("Close conversation") + " (Ctrl+W)"
		)
		self.Bind(
			wx.EVT_MENU, self.on_close_conversation, close_conversation_item
		)
		conversation_menu.AppendSeparator()
		add_image_files_item = conversation_menu.Append(
			wx.ID_ANY,
			# Translators: A label for a menu item to add an image from a file
			_("Add image from f&ile") + "... (Ctrl+I)",
		)
		self.Bind(
			wx.EVT_MENU,
			lambda e: self.on_add_image(e, False),
			add_image_files_item,
		)
		add_image_url = conversation_menu.Append(
			wx.ID_ANY,
			# Translators: A label for a menu item to add an image from a URL
			_("Add image from &URL") + "... (Ctrl+U)",
		)
		self.Bind(
			wx.EVT_MENU, lambda e: self.on_add_image(e, True), add_image_url
		)
		self.transcribe_audio_microphone_item = conversation_menu.Append(
			wx.ID_ANY, _("Transcribe audio from microphone") + "... (Ctrl+R)"
		)
		self.Bind(wx.EVT_MENU, lambda e: self.on_transcribe_audio(e, True))
		self.transcribe_audio_file_item = conversation_menu.Append(
			wx.ID_ANY, _("Transcribe audio file") + "... (Ctrl+Shift+R)"
		)
		self.Bind(wx.EVT_MENU, lambda e: self.on_transcribe_audio(e, False))
		conversation_menu.AppendSeparator()
		manage_accounts_item = conversation_menu.Append(
			wx.ID_ANY,
			# Translators: A label for a menu item to manage accounts
			_("Manage &accounts") + "... (Ctrl+Shift+A)",
		)
		self.Bind(wx.EVT_MENU, self.on_manage_accounts, manage_accounts_item)
		preferences_item = conversation_menu.Append(wx.ID_PREFERENCES)
		self.Bind(wx.EVT_MENU, self.on_preferences, preferences_item)
		update_item_label_suffix(preferences_item, "... (Ctrl+Shift+P)")
		quit_item = conversation_menu.Append(wx.ID_EXIT)
		self.Bind(wx.EVT_MENU, self.on_quit, quit_item)
		self.signal_received = False
		signal.signal(signal.SIGINT, self.on_ctrl_c)
		self.timer = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self.on_timer)
		self.timer.Start(100)

		tool_menu = wx.Menu()
		install_nvda_addon = tool_menu.Append(
			wx.ID_ANY, _("Install NVDA addon")
		)
		self.Bind(wx.EVT_MENU, self.on_install_nvda_addon, install_nvda_addon)

		help_menu = wx.Menu()
		about_item = help_menu.Append(wx.ID_ABOUT)
		self.Bind(wx.EVT_MENU, self.on_about, about_item)
		update_item_label_suffix(about_item)
		check_updates_item = help_menu.Append(wx.ID_ANY, _("Check updates"))
		self.Bind(wx.EVT_MENU, self.on_manual_update_check, check_updates_item)
		github_repo_item = help_menu.Append(wx.ID_ANY, _("&GitHub repository"))
		self.Bind(wx.EVT_MENU, self.on_github_repo, github_repo_item)
		roko_basilisk_item = help_menu.Append(wx.ID_ANY, _("Roko's Basilisk"))
		self.Bind(wx.EVT_MENU, self.on_roko_basilisk, roko_basilisk_item)
		view_log_item = help_menu.Append(
			wx.ID_ANY, _("View &log") + " (Ctrl+Shift+F1)"
		)
		self.Bind(wx.EVT_MENU, self.on_view_log, view_log_item)

		menu_bar.Append(conversation_menu, _("&Conversation"))
		menu_bar.Append(tool_menu, _("Too&ls"))
		menu_bar.Append(help_menu, _("&Help"))
		self.SetMenuBar(menu_bar)

		sizer = wx.BoxSizer(wx.VERTICAL)
		self.panel = wx.Panel(self)
		minimize_taskbar = wx.Button(
			self.panel, label=_("Minimize to tray") + " (Ctrl+Alt+Shift+B)"
		)
		minimize_taskbar.Bind(wx.EVT_BUTTON, self.on_minimize)
		sizer.Add(minimize_taskbar, flag=wx.EXPAND)

		self.notebook = wx.Notebook(self.panel)
		sizer.Add(self.notebook, proportion=1, flag=wx.EXPAND)
		self.panel.SetSizer(sizer)
		self.tabs_panels = []

		self.CreateStatusBar()
		self.SetStatusText(_("Ready"))
		self.Layout()
		self.Maximize(True)

	def init_accelerators(self):
		self.Bind(wx.EVT_CLOSE, self.on_close)
		self.Bind(
			wx.EVT_MENU, self.on_new_conversation, id=self.ID_NEW_CONVERSATION
		)
		self.Bind(
			wx.EVT_MENU,
			self.on_close_conversation,
			id=self.ID_CLOSE_CONVERSATION,
		)
		self.Bind(wx.EVT_MENU, self.on_add_image, id=self.ID_ADD_IMAGE_FILE)
		self.Bind(
			wx.EVT_MENU,
			lambda evt: self.on_add_image(evt, True),
			id=self.ID_ADD_URL_IMAGE,
		)
		self.Bind(
			wx.EVT_MENU, self.on_manage_accounts, id=self.ID_MANAGE_ACCOUNTS
		)
		self.Bind(wx.EVT_MENU, self.on_preferences, id=self.ID_PREFERENCES)
		self.Bind(wx.EVT_MENU, self.on_view_log, id=self.ID_VIEW_LOG)
		self.Bind(
			wx.EVT_MENU,
			lambda evt: self.on_transcribe_audio(evt, True),
			id=self.ID_TOGGLE_RECORDING,
		)
		self.Bind(
			wx.EVT_MENU,
			lambda evt: self.on_transcribe_audio(evt, False),
			id=self.ID_TRANSCRIBE_AUDIO,
		)

		self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)

		accelerators = [
			(wx.ACCEL_CTRL, ord('N'), self.ID_NEW_CONVERSATION),
			(wx.ACCEL_CTRL, ord('W'), self.ID_CLOSE_CONVERSATION),
			(wx.ACCEL_CTRL, ord('I'), self.ID_ADD_IMAGE_FILE),
			(wx.ACCEL_CTRL, ord('U'), self.ID_ADD_URL_IMAGE),
			(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('A'), self.ID_MANAGE_ACCOUNTS),
			(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('P'), self.ID_PREFERENCES),
			(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_F1, self.ID_VIEW_LOG),
			(wx.ACCEL_CTRL, ord('R'), self.ID_TOGGLE_RECORDING),
			(
				wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
				ord('R'),
				self.ID_TRANSCRIBE_AUDIO,
			),
		]

		for i in range(1, 10):
			id_ref = wx.NewIdRef()
			accelerators.append((wx.ACCEL_CTRL, ord(str(i)), id_ref))
			self.Bind(wx.EVT_MENU, self.make_on_goto_tab(i), id=id_ref)

		self.SetAcceleratorTable(wx.AcceleratorTable(accelerators))

	def register_hot_key(self):
		self.RegisterHotKey(
			HotkeyAction.TOGGLE_VISIBILITY.value,
			win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT,
			ord('B'),
		)
		self.RegisterHotKey(
			HotkeyAction.CAPTURE_FULL.value,
			win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT,
			ord('F'),
		)
		self.RegisterHotKey(
			HotkeyAction.CAPTURE_WINDOW.value,
			win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT,
			ord('W'),
		)

	def on_hotkey(self, event):
		match HotkeyAction(event.GetId()):
			case HotkeyAction.TOGGLE_VISIBILITY:
				self.toggle_visibility(None)
			case HotkeyAction.CAPTURE_WINDOW:
				self.screen_capture(CaptureMode.WINDOW)
			case HotkeyAction.CAPTURE_FULL:
				self.screen_capture(CaptureMode.FULL)
			case _:
				log.error(f"Unknown hotkey action: {event.GetId()}")

	def toggle_visibility(self, event):
		if self.IsShown():
			self.on_minimize(None)
		elif not self.IsShown():
			self.on_restore(None)

	def capture_partial_screen(
		self, screen_coordinates: tuple[int, int, int, int], name: str = ""
	):
		log.debug(f"Capturing partial screen: {screen_coordinates}")
		now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
		fd, path = tempfile.mkstemp(
			prefix=f"basilisk_{now_str}_", suffix=".png"
		)
		os.close(fd)
		self.tmp_files.append(path)
		log.debug(f"Temporary file: {path}")
		thread = ScreenCaptureThread(
			self,
			path=path,
			capture_mode=CaptureMode.PARTIAL,
			screen_coordinates=screen_coordinates,
			name=name,
		)
		thread.start()

	def screen_capture(self, capture_mode: CaptureMode):
		log.debug("Capturing screen")
		now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
		fd, path = tempfile.mkstemp(
			prefix=f"basilisk_{now_str}_", suffix=".png"
		)
		os.close(fd)
		self.tmp_files.append(path)
		log.debug(f"Temporary file: {path}")
		thread = ScreenCaptureThread(self, path, capture_mode)
		thread.start()

	def post_screen_capture(self, imagefile: ImageFile | str):
		log.debug("Screen capture received")
		self.current_tab.add_images([imagefile])
		if not self.IsShown():
			self.Show()
			self.Restore()
			self.Layout()
		self.Raise()

	def on_minimize(self, event):
		if not self.IsShown():
			log.debug("Already minimized")
			return
		log.debug("Minimized to tray")
		self.Hide()

	def on_restore(self, event):
		if self.IsShown():
			log.debug("Already restored")
			return
		log.debug("Restored from tray")
		self.Show(True)
		self.Raise()

	def on_close(self, event):
		if config.conf.general.quit_on_close:
			self.on_quit(event)
		else:
			self.on_minimize(event)

	def on_quit(self, event):
		log.info("Closing application")
		global_vars.app_should_exit = True
		for tmp_file in self.tmp_files:
			log.debug(f"Removing temporary file: {tmp_file}")
			os.remove(tmp_file)
		# ensure all conversation tasks are stopped
		for tab in self.tabs_panels:
			if tab.task:
				task_id = tab.task.ident
				log.debug(
					f"Waiting for conversation task {task_id} to finish..."
				)
				tab.task.join()
				log.debug("... is dead")
		if sys.platform == "win32":
			self.UnregisterHotKey(HotkeyAction.TOGGLE_VISIBILITY.value)
			self.UnregisterHotKey(HotkeyAction.CAPTURE_WINDOW.value)
			self.UnregisterHotKey(HotkeyAction.CAPTURE_FULL.value)
			self.tray_icon.RemoveIcon()
			self.tray_icon.Destroy()
		self.Destroy()
		wx.GetApp().ExitMainLoop()

	def on_tab_changed(self, event):
		tab_index = event.GetSelection()
		self.SetTitle(f"Conversation {tab_index + 1} - {APP_NAME}")

	def make_on_goto_tab(self, tab_index):
		def on_goto_tab(event):
			if tab_index <= len(self.tabs_panels):
				self.notebook.SetSelection(tab_index - 1)

		return on_goto_tab

	def on_new_conversation(self, event):
		log.debug("Creating a new conversation")
		self.tabs_panels.append(ConversationTab(self.notebook))
		self.notebook.AddPage(
			self.tabs_panels[-1], f"Conversation {len(self.tabs_panels)}"
		)
		self.notebook.SetSelection(len(self.tabs_panels) - 1)
		self.SetTitle(f"Conversation {len(self.tabs_panels)} - {APP_NAME}")

	def on_close_conversation(self, event):
		current_tab = self.notebook.GetSelection()
		if current_tab != wx.NOT_FOUND:
			self.notebook.DeletePage(current_tab)
			self.tabs_panels.pop(current_tab)
			current_tab_count = self.notebook.GetPageCount()
			if current_tab_count == 0:
				self.on_new_conversation(None)
			else:
				for tab_index in range(current_tab_count):
					self.notebook.SetPageText(
						tab_index, f"Conversation {tab_index + 1}"
					)
				self.notebook.SetSelection(current_tab_count - 1)
				self.SetTitle(f"Conversation {current_tab_count} - {APP_NAME}")

	@property
	def current_tab(self):
		return self.tabs_panels[self.notebook.GetSelection()]

	def on_add_image(self, event, from_url=False):
		current_tab = self.current_tab
		if not current_tab:
			wx.MessageBox(
				_("No conversation selected"), _("Error"), wx.OK | wx.ICON_ERROR
			)
			return
		if from_url:
			current_tab.add_image_url()
		else:
			current_tab.add_image_files()

	def on_transcribe_audio(
		self, event: wx.Event, from_microphone: bool = False
	):
		current_tab = self.current_tab
		if not current_tab:
			wx.MessageBox(
				_("No conversation selected"), _("Error"), wx.OK | wx.ICON_ERROR
			)
			return
		if from_microphone:
			current_tab.toggle_recording(event)
		else:
			current_tab.on_transcribe_audio_file()

	def refresh_tabs(self):
		for tab in self.tabs_panels:
			tab.on_config_change()

	def on_manage_accounts(self, event):
		from .account_dialog import AccountDialog

		account_dialog = AccountDialog(self, _("Manage accounts"))
		if account_dialog.ShowModal() == wx.ID_OK:
			self.refresh_tabs()
		account_dialog.Destroy()

	def on_preferences(self, event):
		log.debug("Opening preferences dialog")
		from .preferences_dialog import PreferencesDialog

		preferences_dialog = PreferencesDialog(self, title=_("Settings"))
		if preferences_dialog.ShowModal() == wx.ID_OK:
			self.refresh_tabs()
		preferences_dialog.Destroy()

	def on_install_nvda_addon(self, event):
		import zipfile

		res_nvda_addon_path = os.path.join(
			global_vars.resource_path, "connectors", "nvda"
		)
		try:
			if not os.path.isdir(res_nvda_addon_path):
				raise ValueError(
					f"NVDA addon folder not found: {res_nvda_addon_path}"
				)

			tmp_nvda_addon_path = os.path.join(
				tempfile.gettempdir(), "basiliskllm.nvda-addon"
			)
			log.debug(f"Creating NVDA addon: {tmp_nvda_addon_path}")
			with zipfile.ZipFile(
				tmp_nvda_addon_path, 'w', zipfile.ZIP_DEFLATED
			) as zipf:
				for root, _, files in os.walk(res_nvda_addon_path):
					for file in files:
						file_path = os.path.join(root, file)
						arcname = os.path.relpath(
							file_path, start=res_nvda_addon_path
						)
						zipf.write(file_path, arcname)
			log.debug("NVDA addon created")
			os.startfile(tmp_nvda_addon_path)
		except Exception as e:
			log.error(f"Failed to create NVDA addon: {e}")
			wx.MessageBox(
				_("Failed to create NVDA addon"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)

	def on_github_repo(self, event):
		wx.LaunchDefaultBrowser(APP_SOURCE_URL)

	def on_roko_basilisk(self, event):
		wx.LaunchDefaultBrowser(
			"https://en.wikipedia.org/wiki/Roko%27s_basilisk"
		)

	def on_about(self, event):
		from .about_dialog import display_about_dialog

		display_about_dialog(self)

	def on_manual_update_check(self, event):
		log.debug("Checking for updates")
		UpdateDialog(parent=self, title=_("Check updates")).Show()

	def on_view_log(self, event):
		try:
			os.startfile(get_log_file_path())
		except Exception as e:
			log.error(f"Failed to open log file: {e}")
			wx.MessageBox(
				_("Failed to open log file"), _("Error"), wx.OK | wx.ICON_ERROR
			)

	def on_ctrl_c(self, signum, frame):
		self.signal_received = True

	def on_timer(self, event):
		if self.signal_received:
			log.debug("Received SIGINT")
			wx.CallAfter(self.on_quit, None)

	def show_update_notification(self, updater: BaseUpdater):
		log.info("Showing update notification")

		def show_dialog():
			update_dialog = UpdateDialog(
				parent=self, title=_("New version available"), updater=updater
			)
			update_dialog.ShowModal()
			log.debug(f"Update dialog shown: {update_dialog.IsShown()}")

		wx.CallAfter(show_dialog)

	def show_update_download(self, updater: BaseUpdater):
		log.info("Showing update download dialog")

		def show_dialog():
			download_dialog = DownloadUpdateDialog(
				parent=self, title=_("Downloading update"), updater=updater
			)
			download_dialog.ShowModal()
			log.debug(f"Download dialog shown: {download_dialog.IsShown()}")

		wx.CallAfter(show_dialog)
