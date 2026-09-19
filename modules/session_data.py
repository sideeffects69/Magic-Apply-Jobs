'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

The tool keeps nothing between sessions. Everything a person enters (settings,
LinkedIn login, resume text, uploaded resumes, applied-jobs history) lives in
the per-user data folder only while the control panel is open, and is erased
when it closes. To keep their data, people download ONE backup file and load
it back next time - if they don't save it, it is gone, and the next person
starts with a completely fresh tool.

This module holds the three operations behind that:
  * wipe_data     - erase everything in the data folder
  * build_backup  - collect the user's data into one JSON-able dict
  * restore_backup - validate a backup dict and write it back into the folder
'''

import base64
import binascii
import json
import os
import shutil
import time
from datetime import datetime

from config import _overrides

APP_DIR_NAME = "AutoJobApplier"
KEEP_DATA_ENV = "AUTOJOBAPPLIER_KEEP_DATA"

BACKUP_FORMAT = "AutoJobApplier-backup"
BACKUP_VERSION = 1
MAX_RESUME_FILE_BYTES = 10 * 1024 * 1024
MAX_RESUME_FILES = 20

# Secrets that a backup can leave out, for people who'd rather retype them than
# keep them in a file.
_SECRET_KEYS = {"secrets": ("password", "llm_api_key")}

_CONFIG_FILE = "user_config.json"
_RESUME_YAML_FILE = "resume_data.yaml"
_HISTORY_REL = ("all excels", "all_applied_applications_history.csv")
_STATUS_REL = ("all excels", "job_statuses.json")
_RESUME_DIR_REL = ("all resumes", "default")


class BackupError(ValueError):
    '''Raised with a human-readable message when a backup file can't be used.'''


def _resolve(data_dir: str | None) -> str:
    return data_dir if data_dir else _overrides.DATA_DIR


def _path(data_dir: str | None, *parts: str) -> str:
    return os.path.join(_resolve(data_dir), *parts)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", newline="") as file:
            return file.read()
    except OSError:
        return ""


def _read_json(path: str) -> dict:
    try:
        data = json.loads(_read_text(path))
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file:
        file.write(text)


def keep_data_enabled() -> bool:
    '''True when the developer switch that disables the end-of-session erase is on.'''
    return os.environ.get(KEEP_DATA_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _resume_dir(data_dir: str | None) -> str:
    return _path(data_dir, *_RESUME_DIR_REL)


def has_data(data_dir: str | None = None) -> bool:
    '''True if the data folder holds anything a person entered or the tool saved for them.'''
    if os.path.exists(_path(data_dir, _CONFIG_FILE)) or os.path.exists(_path(data_dir, _RESUME_YAML_FILE)):
        return True
    if os.path.exists(_path(data_dir, *_HISTORY_REL)):
        return True
    try:
        return any(os.path.isfile(os.path.join(_resume_dir(data_dir), name)) for name in os.listdir(_resume_dir(data_dir)))
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Erase
# ---------------------------------------------------------------------------
def wipe_data(data_dir: str | None = None) -> bool:
    '''
    Deletes everything inside the data folder (the folder itself is kept).
    Returns True if it ended up empty. A locked file (e.g. a browser profile
    Chrome hasn't released yet) is retried for a few seconds, then skipped.

    Refuses to run on any folder not named like our own data folder, so a wrong
    path can never turn this into "delete somebody's Documents".
    '''
    target = os.path.abspath(_resolve(data_dir))
    if os.path.basename(target) != APP_DIR_NAME:
        raise ValueError(f"Refusing to erase '{target}': not an {APP_DIR_NAME} data folder.")
    if not os.path.isdir(target):
        return True
    for attempt in range(4):
        for name in os.listdir(target):
            entry = os.path.join(target, name)
            try:
                if os.path.isdir(entry) and not os.path.islink(entry):
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    os.remove(entry)
            except OSError:
                pass
        if not os.listdir(target):
            return True
        if attempt < 3:
            time.sleep(0.5)
    return False


def wipe_if_enabled(data_dir: str | None = None) -> bool:
    '''wipe_data(), unless the developer keep-data switch is on. Returns True if it erased.'''
    if keep_data_enabled():
        return False
    return wipe_data(data_dir)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def build_backup(data_dir: str | None = None, include_secrets: bool = True) -> dict:
    '''
    Collects everything a person entered into one JSON-serialisable dict:
    settings, resume text, applied-jobs history (which also drives the daily
    application cap), and uploaded/generated resume files.

    With `include_secrets=False` the LinkedIn password and AI API key are left out.
    '''
    config = _read_json(_path(data_dir, _CONFIG_FILE))
    if not include_secrets:
        for section, keys in _SECRET_KEYS.items():
            if isinstance(config.get(section), dict):
                for key in keys:
                    config[section].pop(key, None)

    resume_files = {}
    resume_dir = _resume_dir(data_dir)
    try:
        names = sorted(os.listdir(resume_dir))
    except OSError:
        names = []
    for name in names:
        file_path = os.path.join(resume_dir, name)
        if len(resume_files) >= MAX_RESUME_FILES:
            break
        try:
            if not os.path.isfile(file_path) or os.path.getsize(file_path) > MAX_RESUME_FILE_BYTES:
                continue
            with open(file_path, "rb") as file:
                resume_files[name] = base64.b64encode(file.read()).decode("ascii")
        except OSError:
            continue

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created": datetime.now().isoformat(timespec="seconds"),
        "includes_secrets": bool(include_secrets),
        "config": config,
        "resume_yaml": _read_text(_path(data_dir, _RESUME_YAML_FILE)),
        "applied_history_csv": _read_text(_path(data_dir, *_HISTORY_REL)),
        "job_statuses": _read_json(_path(data_dir, *_STATUS_REL)),
        "resume_files": resume_files,
    }


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
def _safe_filename(name: str) -> bool:
    '''A bare file name: no folders, no traversal, nothing hidden.'''
    return (bool(name) and name == os.path.basename(name.replace("\\", "/"))
            and name not in (".", "..") and not name.startswith(".") and ":" not in name)


def restore_backup(payload, data_dir: str | None = None, config_validator=None) -> list[str]:
    '''
    Validates `payload` (a parsed backup file) and, only if everything checks
    out, writes it into the data folder - a bad file never leaves a half-restored
    state. `config_validator(config_dict)` may clean/coerce the settings and
    raise BackupError. Returns a list of what was restored, for the UI to show.
    '''
    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        raise BackupError("This isn't a Magic Apply - Jobs backup file.")
    version = payload.get("version")
    if not isinstance(version, int) or version < 1 or version > BACKUP_VERSION:
        raise BackupError("This backup was made by a newer version of the tool and can't be read here.")

    config = payload.get("config") or {}
    if not isinstance(config, dict):
        raise BackupError("The settings in this backup are damaged.")
    if config and config_validator:
        config = config_validator(config)

    resume_yaml = payload.get("resume_yaml") or ""
    history_csv = payload.get("applied_history_csv") or ""
    statuses = payload.get("job_statuses") or {}
    if not isinstance(resume_yaml, str) or not isinstance(history_csv, str) or not isinstance(statuses, dict):
        raise BackupError("Part of this backup is damaged.")

    raw_files = payload.get("resume_files") or {}
    if not isinstance(raw_files, dict) or len(raw_files) > MAX_RESUME_FILES:
        raise BackupError("The resume files in this backup are damaged.")
    decoded_files = {}
    for name, encoded in raw_files.items():
        if not isinstance(name, str) or not _safe_filename(name) or not isinstance(encoded, str):
            raise BackupError("This backup contains a resume file with an unsafe name.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise BackupError(f"The resume file '{name}' in this backup is damaged.") from error
        if len(content) > MAX_RESUME_FILE_BYTES:
            raise BackupError(f"The resume file '{name}' in this backup is too large.")
        decoded_files[name] = content

    restored = []
    if config:
        _write_text(_path(data_dir, _CONFIG_FILE), json.dumps(config, indent=2, ensure_ascii=False))
        restored.append("settings")
    if resume_yaml.strip():
        _write_text(_path(data_dir, _RESUME_YAML_FILE), resume_yaml)
        restored.append("resume text")
    if history_csv.strip():
        _write_text(_path(data_dir, *_HISTORY_REL), history_csv)
        restored.append("applied-jobs history")
    if statuses:
        _write_text(_path(data_dir, *_STATUS_REL), json.dumps(statuses, indent=2, ensure_ascii=False))
    if decoded_files:
        resume_dir = _resume_dir(data_dir)
        os.makedirs(resume_dir, exist_ok=True)
        for name, content in decoded_files.items():
            with open(os.path.join(resume_dir, name), "wb") as file:
                file.write(content)
        restored.append(f"{len(decoded_files)} resume file{'s' if len(decoded_files) != 1 else ''}")
    return restored
