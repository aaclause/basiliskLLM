import logging
import shutil
import sys
import threading

import truststore
import wx

import basilisk.config as config
import basilisk.global_vars as global_vars

# don't use relative import here, CxFreeze will fail to find the module
from basilisk.consts import APP_NAME, TMP_DIR
from basilisk.file_watcher import init_file_watcher
from basilisk.localization import init_translation
from basilisk.logger import (
	get_log_file_path,
	logging_uncaught_exceptions,
	setup_logging,
)
from basilisk.server_thread import ServerThread
from basilisk.sound_manager import initialize_sound_manager
from basilisk.updater import automatic_update_check, automatic_update_download

log = logging.getLogger(__name__)


class MainApp(wx.App):
	def OnInit(self) -> bool:
		sys.excepthook = logging_uncaught_exceptions

		self.conf = config.conf()
		log_level = (
			global_vars.args.log_level or self.conf.general.log_level.name
		)
		log.debug(f"args: {global_vars.args}")
		setup_logging(log_level)
		log.debug(f"config: {self.conf}")
		if getattr(sys, "frozen", False):
			log.info(
				"running frozen application: redirecting stdio to log file"
			)
			self.RedirectStdio(str(get_log_file_path()))
		language = global_vars.args.language or self.conf.general.language
		self.locale = init_translation(language)
		log.info("translation initialized")
		initialize_sound_manager()
		log.info("sound manager initialized")
		from basilisk.gui.main_frame import MainFrame

		frame_style = wx.DEFAULT_FRAME_STYLE
		if global_vars.args.minimize:
			frame_style |= wx.MINIMIZE
		self.frame = MainFrame(
			None, title=APP_NAME, conf=self.conf, style=frame_style
		)
		self.frame.Show(not global_vars.args.minimize)
		self.SetTopWindow(self.frame)
		self.init_system_cert_store()
		self.file_watcher = init_file_watcher(self.bring_window_to_focus)
		self.server = None
		if self.conf.server.enable:
			self.server = ServerThread(self.frame, self.conf.server.port)
			self.server.start()
		self.auto_update = None
		if (
			self.conf.general.automatic_update_mode
			!= config.AutomaticUpdateModeEnum.OFF
		):
			self.start_auto_update_thread()
		log.info("Application started")
		return True

	def bring_window_to_focus(self):
		wx.CallAfter(self.frame.toggle_visibility, None)

	def start_auto_update_thread(self):
		self.stop_auto_update = False
		target_func = (
			automatic_update_check
			if self.conf.general.automatic_update_mode
			== config.AutomaticUpdateModeEnum.NOTIFY
			else automatic_update_download
		)
		callback_func = (
			self.frame.show_update_notification
			if self.conf.general.automatic_update_mode
			== config.AutomaticUpdateModeEnum.NOTIFY
			else self.frame.show_update_download
		)
		self.auto_update = threading.Thread(
			target=target_func,
			args=(self.conf, callback_func, self.stop_auto_update),
			daemon=True,
		)
		self.auto_update.start()
		log.info("Automatic update thread started")

	def OnExit(self) -> int:
		if self.server:
			log.debug("Stopping server")
			self.server.stop()
			self.server.join()
			log.debug("Server stopped")
		if self.auto_update and self.auto_update.is_alive():
			self.stop_auto_update = True
			self.auto_update.join()
			log.info("Automatic update thread stopped")
		log.debug("Removing temporary files")
		shutil.rmtree(TMP_DIR, ignore_errors=True)

		log.debug("Stopping file watcher")
		self.file_watcher.stop()
		self.file_watcher.join()
		log.debug("File watcher stopped")

		log.info("Application exited")
		return 0

	def init_system_cert_store(self):
		if not self.conf.network.use_system_cert_store:
			log.info("Use certifi certificate store")
			return
		try:
			log.debug("Activating system certificate store")
			truststore.inject_into_ssl()
			log.info("System certificate store activated")
		except Exception as e:
			log.error(
				f"Failed to activate system certificate store: {e}",
				exc_info=True,
			)
			wx.MessageBox(
				# Translators: Error message
				_("Failed to activate system certificate store"),
				# Translators: Error title
				_("Error"),
				style=wx.ICON_ERROR,
			)
