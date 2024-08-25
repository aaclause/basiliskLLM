import argparse
import os
import sys

import psutil

from basilisk import global_vars
from basilisk.consts import APP_NAME, FILE_LOCK_PATH, TMP_DIR
from basilisk.file_watcher import send_focus_signal
from basilisk.singleton_instance import SingletonInstance


def display_already_running_msg():
	import ctypes

	ctypes.windll.user32.MessageBoxW(
		0,
		f"{APP_NAME} is already running. Use the tray icon to interact with the application or AltGr+Shift+B to focus the window.",
		APP_NAME,
		0x40 | 0x0,
	)


def parse_args():
	parser = argparse.ArgumentParser(
		prog=APP_NAME,
		description="Runs the application with customized configurations.",
	)
	parser.add_argument(
		"--language", "-l", help="Set the application language", default=None
	)
	parser.add_argument(
		"--log_level",
		"-L",
		help="Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
		default=None,
	)
	parser.add_argument(
		"--no-env-account",
		"-N",
		help="Disable loading accounts from environment variables",
		action="store_true",
	)
	parser.add_argument(
		"--minimize",
		"-m",
		help="Start the application minimized",
		action="store_true",
	)
	parser.add_argument(
		"-n",
		help="Show message window if application is already running",
		action="store_true",
		dest="show_already_running_msg",
	)
	return parser.parse_args()


if __name__ == '__main__':
	os.makedirs(TMP_DIR, exist_ok=True)
	global_vars.args = parse_args()
	singleton_instance = SingletonInstance(FILE_LOCK_PATH)
	if not singleton_instance.acquire():
		existing_pid = singleton_instance.get_existing_pid()
		if existing_pid:
			try:
				psutil.Process(existing_pid)
				if global_vars.args.show_already_running_msg:
					display_already_running_msg()
				else:
					send_focus_signal()
				sys.exit(0)
			except psutil.NoSuchProcess:
				singleton_instance.acquire()
	from basilisk.main_app import MainApp

	app = MainApp()
	app.MainLoop()
