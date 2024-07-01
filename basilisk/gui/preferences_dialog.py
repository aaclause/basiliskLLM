import logging
import wx
from babel import Locale
from basilisk.config import (
	conf,
	LogLevelEnum,
	ReleaseChannelEnum,
	AutomaticUpdateModeEnum,
)
from basilisk.localization import get_supported_locales, get_app_locale
from basilisk.logger import set_log_level

log = logging.getLogger(__name__)

LOG_LEVELS = {
	# Translators: A label for the log level in the settings dialog
	LogLevelEnum.NOTSET: _("Off"),
	# Translators: A label for the log level in the settings dialog
	LogLevelEnum.DEBUG: _("Debug"),
	# Translators: A label for the log level in the settings dialog
	LogLevelEnum.INFO: _("Info"),
	# Translators: A label for the log level in the settings dialog
	LogLevelEnum.WARNING: _("Warning"),
	# Translators: A label for the log level in the settings dialog
	LogLevelEnum.ERROR: _("Error"),
	# Translators: A label for the log level in the settings dialog
	LogLevelEnum.CRITICAL: _("Critical"),
}

release_channels = {
	# Translators: A label for the release channel in the settings dialog
	ReleaseChannelEnum.STABLE: _("Stable"),
	# Translators: A label for the release channel in the settings dialog
	ReleaseChannelEnum.BETA: _("Beta"),
	# Translators: A label for the release channel in the settings dialog
	ReleaseChannelEnum.DEV: _("Development"),
}


auto_update_modes = {
	# Translators: A label for the automatic update mode in the settings dialog
	AutomaticUpdateModeEnum.OFF: _("Off"),
	# Translators: A label for the automatic update mode in the settings dialog
	AutomaticUpdateModeEnum.NOTIFY: _("Notify new version"),
	# Translators: A label for the automatic update mode in the settings dialog
	AutomaticUpdateModeEnum.DOWNLOAD: _("Download new version"),
	# Translators: A label for the automatic update mode in the settings dialog
	AutomaticUpdateModeEnum.INSTALL: _("Install new version"),
}


class PreferencesDialog(wx.Dialog):
	def __init__(self, parent, title, size=(400, 400)):
		wx.Dialog.__init__(self, parent, title=title, size=size)
		self.parent = parent
		self.init_ui()
		self.Centre()
		self.Show()

	def init_ui(self):
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		panel.SetSizer(sizer)

		label = wx.StaticText(
			panel,
			# Translators: A label for the log level selection in the preferences dialog
			label=_("Log level"),
			style=wx.ALIGN_LEFT,
		)
		sizer.Add(label, 0, wx.ALL, 5)
		log_level_value = LOG_LEVELS[conf.general.log_level]
		self.log_level = wx.ComboBox(
			panel,
			choices=list(LOG_LEVELS.values()),
			value=log_level_value,
			style=wx.CB_READONLY,
		)
		sizer.Add(self.log_level, 0, wx.ALL, 5)
		app_locale = get_app_locale(conf.general.language)
		self.init_languages(app_locale)
		value = self.languages.get(
			conf.general.language, self.languages["auto"]
		)
		label = wx.StaticText(
			panel,
			# Translators: A label for the language selection in the preferences dialog
			label=_("Language (Requires restart)"),
			style=wx.ALIGN_LEFT,
		)
		sizer.Add(label, 0, wx.ALL, 5)
		self.language = wx.ComboBox(
			panel,
			choices=list(self.languages.values()),
			value=value,
			style=wx.CB_READONLY,
		)
		sizer.Add(self.language, 0, wx.ALL, 5)

		self.quit_on_close = wx.CheckBox(
			panel, label=_("Quit on &close, don't minimize")
		)
		self.quit_on_close.SetValue(conf.general.quit_on_close)
		sizer.Add(self.quit_on_close, 0, wx.ALL, 5)

		update_group = wx.StaticBox(panel, label=_("Update"))
		update_group_sizer = wx.StaticBoxSizer(update_group, wx.VERTICAL)

		label = wx.StaticText(
			panel, label=_("Release channel"), style=wx.ALIGN_LEFT
		)
		update_group_sizer.Add(label, 0, wx.ALL, 5)

		release_channel_value = release_channels[conf.general.release_channel]
		self.release_channel = wx.ComboBox(
			panel,
			choices=list(release_channels.values()),
			value=release_channel_value,
			style=wx.CB_READONLY,
		)
		update_group_sizer.Add(self.release_channel, 0, wx.ALL, 5)

		label = wx.StaticText(
			panel, label=_("Automatic update mode"), style=wx.ALIGN_LEFT
		)
		update_group_sizer.Add(label, 0, wx.ALL, 5)
		auto_update_mode_value = auto_update_modes[
			conf.general.automatic_update_mode
		]
		self.auto_update_mode = wx.ComboBox(
			panel,
			choices=list(auto_update_modes.values()),
			value=auto_update_mode_value,
			style=wx.CB_READONLY,
		)
		update_group_sizer.Add(self.auto_update_mode, 0, wx.ALL, 5)

		sizer.Add(update_group_sizer, 0, wx.ALL, 5)

		self.advanced_mode = wx.CheckBox(
			panel,
			# Translators: A label for a checkbox in the preferences dialog
			label=_("Advanced mode"),
			style=wx.ALIGN_LEFT,
		)
		self.advanced_mode.SetValue(conf.general.advanced_mode)
		sizer.Add(self.advanced_mode, 0, wx.ALL, 5)

		images_group = wx.StaticBox(panel, label=_("Images"))
		images_group_sizer = wx.StaticBoxSizer(images_group, wx.VERTICAL)

		self.image_resize = wx.CheckBox(
			images_group,
			# Translators: A label for a checkbox in the preferences dialog
			label=_("Resize images before uploading"),
		)
		self.image_resize.SetValue(conf.images.resize)
		self.image_resize.Bind(wx.EVT_CHECKBOX, self.on_resize)
		images_group_sizer.Add(self.image_resize, 0, wx.ALL, 5)

		label = wx.StaticText(
			images_group,
			# Translators: A label in the preferences dialog
			label=_(
				"Maximum &height (0 to resize proportionally to the width):"
			),
		)
		images_group_sizer.Add(label, 0, wx.ALL, 5)
		self.image_max_height = wx.SpinCtrl(
			images_group, value=str(conf.images.max_height), min=0, max=10000
		)
		images_group_sizer.Add(self.image_max_height, 0, wx.ALL, 5)

		label = wx.StaticText(
			images_group,
			# Translators: A label in the preferences dialog
			label=_(
				"Maximum &width (0 to resize proportionally to the height):"
			),
		)
		images_group_sizer.Add(label, 0, wx.ALL, 5)
		self.image_max_width = wx.SpinCtrl(
			images_group, value=str(conf.images.max_width), min=0, max=10000
		)
		images_group_sizer.Add(self.image_max_width, 0, wx.ALL, 5)

		label = wx.StaticText(
			images_group,
			# Translators: A label in the preferences dialog
			label=_(
				"&Quality for JPEG images (0 [worst] to 95 [best], values above 95 should be avoided):"
			),
		)
		images_group_sizer.Add(label, 0, wx.ALL, 5)
		self.image_quality = wx.SpinCtrl(
			images_group, value=str(conf.images.quality), min=1, max=100
		)
		images_group_sizer.Add(self.image_quality, 0, wx.ALL, 5)

		self.on_resize(None)
		sizer.Add(images_group_sizer, 0, wx.ALL, 5)

		server_group = wx.StaticBox(panel, label=_("Server"))
		server_group_sizer = wx.StaticBoxSizer(server_group, wx.VERTICAL)

		self.server_enable = wx.CheckBox(
			server_group,
			# Translators: A label for a checkbox in the preferences dialog
			label=_("Enable server mode (requires restart)"),
		)
		self.server_enable.SetValue(conf.server.enable)
		server_group_sizer.Add(self.server_enable, 0, wx.ALL, 5)

		label = wx.StaticText(
			server_group,
			# Translators: A label in the preferences dialog
			label=_("Port:"),
		)
		server_group_sizer.Add(label, 0, wx.ALL, 5)
		self.server_port = wx.SpinCtrl(
			server_group, value=str(conf.server.port), min=1, max=65535
		)
		server_group_sizer.Add(self.server_port, 0, wx.ALL, 5)

		sizer.Add(server_group_sizer, 0, wx.ALL, 5)

		bSizer = wx.BoxSizer(wx.HORIZONTAL)

		btn = wx.Button(panel, wx.ID_OK, _("Save"))
		btn.Bind(wx.EVT_BUTTON, self.on_ok)
		bSizer.Add(btn, 0, wx.ALL, 5)

		btn = wx.Button(panel, wx.ID_CANCEL, _("Cancel"))
		btn.Bind(wx.EVT_BUTTON, self.on_cancel)
		bSizer.Add(btn, 0, wx.ALL, 5)

		sizer.Add(bSizer, 0, wx.ALL, 5)

		panel.Layout()
		self.Layout()

	def on_resize(self, event):
		val = self.image_resize.GetValue()
		self.image_max_height.Enable(val)
		self.image_max_width.Enable(val)
		self.image_quality.Enable(val)

	def on_ok(self, event):
		log.debug("Saving configuration")
		conf.general.log_level = list(LOG_LEVELS.keys())[
			self.log_level.GetSelection()
		]
		conf.general.language = list(self.languages.keys())[
			self.language.GetSelection()
		]
		conf.general.quit_on_close = self.quit_on_close.GetValue()
		conf.general.release_channel = list(release_channels.keys())[
			self.release_channel.GetSelection()
		]
		conf.general.automatic_update_mode = list(auto_update_modes.keys())[
			self.auto_update_mode.GetSelection()
		]
		conf.general.advanced_mode = self.advanced_mode.GetValue()

		conf.images.resize = self.image_resize.GetValue()
		conf.images.max_height = int(self.image_max_height.GetValue())
		conf.images.max_width = int(self.image_max_width.GetValue())
		conf.images.quality = int(self.image_quality.GetValue())

		conf.server.enable = self.server_enable.GetValue()
		conf.server.port = int(self.server_port.GetValue())

		conf.save()
		set_log_level(conf.general.log_level.name)

		self.EndModal(wx.ID_OK)

	def on_cancel(self, event):
		self.EndModal(wx.ID_CANCEL)

	def init_languages(self, cur_locale: Locale) -> dict[str, str]:
		"""Get all supported languages and set the current language as default"""
		self.languages = {
			# Translators: A label for the language in the settings dialog
			"auto": _("System default (auto)")
		}
		supported_locales = get_supported_locales()
		self.languages.update(
			{
				str(
					locale
				): f"{locale.get_display_name(cur_locale).capitalize()} ({locale})"
				for locale in supported_locales
			}
		)
