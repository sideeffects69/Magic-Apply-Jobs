'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

Loads user settings saved by the local control panel (see app.py) - your
name, phone, LinkedIn credentials, resume text, search preferences, etc. -
and applies them over the Python defaults defined in the config/*.py files.

These settings live in `user_config.json`, saved in the OS's per-user app
data folder (`DATA_DIR`, below) - deliberately OUTSIDE this project folder.
This project gets copied, renamed, zipped and shared; personal data must
never travel along with the code by accident. Everything the tool produces
while running - application history, failed-job records, generated resumes,
logs, screenshots and the browser guest profile (login cookies) - lives in
that same folder for the same reason. Clearing that OS folder removes it
completely, like clearing an app's cache.

If `user_config.json` does not exist, everything here is a no-op and the tool
behaves exactly as it always has: configuration comes entirely from the
config/*.py defaults. This keeps the classic "edit the .py files" workflow
fully working for existing users.
'''

import os
import sys
import json
import shutil

# This file lives in <project_root>/config/, so the project root is one level up.
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CONFIG_DIR)


def _app_data_dir() -> str:
    '''
    Per-user, per-OS app data folder that holds everything personal - outside
    the project folder so sharing/copying/zipping this project never carries
    anyone's data along with it.
    '''
    app_name = "AutoJobApplier"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, app_name)


DATA_DIR = _app_data_dir()
USER_CONFIG_PATH = os.path.join(DATA_DIR, "user_config.json")
_LEGACY_USER_CONFIG_PATH = os.path.join(_ROOT_DIR, "user_config.json")


def _migrate_legacy_config() -> None:
    '''
    One-time migration for existing users: older versions saved settings as
    `user_config.json` right in the project folder - exactly the file that
    leaks personal data if this project folder is shared. If we find that old
    in-project file and nothing has been saved to the new location yet, move
    it over once, then remove the old copy so it can't be shared by accident.
    '''
    if os.path.exists(USER_CONFIG_PATH) or not os.path.exists(_LEGACY_USER_CONFIG_PATH):
        return
    try:
        os.makedirs(os.path.dirname(USER_CONFIG_PATH), exist_ok=True)
        with open(_LEGACY_USER_CONFIG_PATH, "r", encoding="utf-8") as src:
            content = src.read()
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as dst:
            dst.write(content)
        os.remove(_LEGACY_USER_CONFIG_PATH)
    except OSError:
        pass  # Best-effort; on any failure the app just starts with defaults.


_migrate_legacy_config()


# Runtime data that older versions kept inside the project folder.
_LEGACY_DATA_ITEMS = ("all excels", "all resumes", "logs", ".bot_run.log")
# Windows guest browser profile (LinkedIn login cookies) used to sit in a
# machine-wide folder every Windows account on the PC could read.
_LEGACY_WIN_CHROME_PROFILE = r"C:\temp\auto-job-apply-profile"
CHROME_GUEST_PROFILE_DIR = os.path.join(DATA_DIR, "chrome-profile")


def _merge_move(src: str, dst: str) -> None:
    '''Moves `src` to `dst`; directories are merged and an existing file is never overwritten.'''
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            _merge_move(os.path.join(src, name), os.path.join(dst, name))
        try:
            os.rmdir(src)
        except OSError:
            pass
    elif not os.path.exists(dst):
        shutil.move(src, dst)


def _migrate_legacy_data() -> None:
    '''
    One-time migration: older versions wrote history, resumes, logs and the
    browser guest profile next to the code, so a shared copy of the project
    carried the previous user's data with it. Move anything found there into
    `DATA_DIR`. Best-effort - a locked file is simply left where it is.
    '''
    for name in _LEGACY_DATA_ITEMS:
        src = os.path.join(_ROOT_DIR, name)
        if not os.path.exists(src):
            continue
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            _merge_move(src, os.path.join(DATA_DIR, name))
        except OSError:
            pass

    # A browser profile must move as one unit - a file-by-file move that hits a
    # locked file would leave it split and corrupt. Rename it whole or not at all.
    if (sys.platform.startswith("win") and os.path.isdir(_LEGACY_WIN_CHROME_PROFILE)
            and not os.path.exists(CHROME_GUEST_PROFILE_DIR)):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            os.rename(_LEGACY_WIN_CHROME_PROFILE, CHROME_GUEST_PROFILE_DIR)
        except OSError:
            pass


_migrate_legacy_data()


def load_user_config() -> dict:
    '''
    Returns the full override dictionary from `user_config.json`, or an empty
    dict if the file is missing, unreadable, or not valid JSON. Never raises.
    '''
    try:
        with open(USER_CONFIG_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def apply(module_name: str, module_globals: dict) -> None:
    '''
    Overrides a config module's existing globals with values from the matching
    section of `user_config.json`.

    - `module_name` is the module's `__name__` (e.g. "config.settings"); the last
      dotted part is the section name looked up in the JSON ("settings").
    - Only keys that ALREADY exist as globals in the module are applied, so the
      JSON can never introduce new names into the config namespace.
    '''
    section_name = module_name.split(".")[-1]
    section = load_user_config().get(section_name, {})
    if not isinstance(section, dict):
        return
    for key, value in section.items():
        if key in module_globals:
            module_globals[key] = value
