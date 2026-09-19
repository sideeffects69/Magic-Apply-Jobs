'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

Local "control panel" web app. It lets a non-technical person configure and run
the tool from a browser instead of editing Python files and using a terminal.

IMPORTANT - how configuration works:
  * This app reads/writes ONLY `user_config.json` in the per-user data folder (outside the project).
  * It NEVER edits the config/*.py files.
  * The config/*.py modules load user_config.json over their built-in defaults
    (see config/_overrides.py), so saving here changes the tool's behaviour
    while leaving the classic "edit the .py files" workflow intact. With no
    user_config.json present the tool behaves exactly as it always has.

SECURITY: this app handles LinkedIn credentials, so it binds to 127.0.0.1 only
(never 0.0.0.0) and runs with debug OFF. Do not change these.
'''

from flask import Flask, request, jsonify, render_template, send_file, abort
import atexit
import csv
from datetime import datetime
import os
import sys
import json
import copy
import signal
import subprocess
import threading
import importlib
from urllib.parse import urlparse

import config_schema
from config import _overrides
from config._overrides import DATA_DIR
from modules import session_data

app = Flask(__name__)
# A backup file carries a whole profile (resume files, history, optionally passwords).
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


@app.before_request
def _local_requests_only():
    '''
    The panel serves credentials, backups and an "erase everything" button, so it
    must only ever answer the person sitting at this computer - not a website
    they happen to have open in another tab.
    * A Host header that isn't localhost is a DNS-rebinding attempt.
    * A state-changing request whose Origin is another site is cross-site forgery.
    (There is no CORS handling on purpose: the page is served by this same app,
    so it never needs cross-origin access, and without CORS headers the browser
    stops other sites from reading any response.)
    '''
    if (urlparse("//" + (request.host or "")).hostname or "") not in _LOCAL_HOSTS:
        abort(403)
    origin = request.headers.get("Origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
        if (urlparse(origin).hostname or "") not in _LOCAL_HOSTS:
            abort(403)


# Project root is the folder this file lives in.
ROOT = os.path.dirname(os.path.abspath(__file__))
USER_CONFIG_PATH = _overrides.USER_CONFIG_PATH
# Everything the tool produces at runtime lives in the per-user data folder, never in
# the project folder, so sharing/zipping the project never carries anyone's data along.
os.makedirs(DATA_DIR, exist_ok=True)
LOG_PATH = os.path.join(DATA_DIR, ".bot_run.log")
PID_PATH = os.path.join(DATA_DIR, ".bot_run.pid")

PATH = os.path.join(DATA_DIR, "all excels")


# ===========================================================================
# Default config values (the pristine config/*.py defaults, ignoring any
# user_config.json). Captured once at startup so /api/config can always show
# "default overlaid with the user's current saved values".
# ===========================================================================
def _load_defaults() -> dict:
    '''
    Import each config module with overrides temporarily disabled, so we read
    the untouched Python defaults regardless of whether user_config.json exists
    right now. Returns {config_module: {key: default_value}}.
    '''
    original_loader = _overrides.load_user_config
    _overrides.load_user_config = lambda: {}
    try:
        import config.secrets as _secrets
        import config.personals as _personals
        import config.questions as _questions
        import config.search as _search
        import config.settings as _settings
        modules = {
            "secrets": _secrets,
            "personals": _personals,
            "questions": _questions,
            "search": _search,
            "settings": _settings,
        }
        # Reload in case they were already imported (with real overrides) earlier.
        for module in modules.values():
            importlib.reload(module)
        defaults = {}
        for field in config_schema.iter_fields():
            module_name = field["config_module"]
            key = field["key"]
            module = modules.get(module_name)
            defaults.setdefault(module_name, {})[key] = getattr(module, key, None)
        return defaults
    finally:
        _overrides.load_user_config = original_loader


DEFAULTS = _load_defaults()


# ===========================================================================
# Config API helpers
# ===========================================================================
def _effective_config() -> dict:
    '''
    Return {config_module: {key: value}} of the pristine defaults overlaid with
    the CURRENT contents of user_config.json (re-read from disk on every call).
    Only keys defined in config_schema are included.
    '''
    effective = copy.deepcopy(DEFAULTS)
    user = _overrides.load_user_config()
    for field in config_schema.iter_fields():
        module_name = field["config_module"]
        key = field["key"]
        section = user.get(module_name)
        if isinstance(section, dict) and key in section:
            effective[module_name][key] = section[key]
    return effective


def _coerce(field_type: str, value):
    '''
    Coerce an incoming JSON value into the type declared for the field in the
    schema. Raises ValueError on invalid numbers so the caller can reject them.
    '''
    if field_type in ("text", "password", "textarea", "select"):
        return "" if value is None else str(value)

    if field_type == "number":
        if isinstance(value, bool):
            raise ValueError("expected a number, got a boolean")
        if isinstance(value, (int, float)):
            number = value
        else:
            text = str(value).strip()
            if text == "":
                raise ValueError("expected a number, got an empty value")
            number = float(text)
        # Every "number" field in the schema (desired_salary, current_experience,
        # switch_number, click_gap, ...) backs a config variable the bot validates
        # as a strict Integer - round rather than saving a stray float like 1.8,
        # which would otherwise crash the bot at startup with a confusing error.
        return round(number)

    if field_type == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")

    if field_type == "list":
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip() != ""]
        text = str(value).strip()
        if text == "":
            return []
        return [item.strip() for item in text.split(",") if item.strip() != ""]

    # Unknown type: pass through untouched.
    return value


def _validate_settings(payload: dict) -> tuple[dict, list]:
    '''
    Checks {config_module: {key: value}} against the schema and coerces every
    value to its declared type. Returns (coerced, unknown) where `unknown` lists
    sections/keys the schema doesn't define (they are left out of `coerced`).
    Raises ValueError with a readable message on a malformed section or value.
    '''
    valid = config_schema.valid_keys()
    unknown = []
    coerced = {}
    for section, values in payload.items():
        if not isinstance(values, dict):
            raise ValueError(f"Section '{section}' must be an object")
        if section not in valid:
            unknown.append(section)
            continue
        for key, value in values.items():
            field = valid[section].get(key)
            if field is None:
                unknown.append(f"{section}.{key}")
                continue
            try:
                coerced.setdefault(section, {})[key] = _coerce(field["type"], value)
            except ValueError as err:
                raise ValueError(f"Invalid value for '{section}.{key}': {err}") from err
    return coerced, unknown


# ===========================================================================
# Bot subprocess management (run / stop / status / logs)
# ===========================================================================
_bot_proc = None
_bot_lock = threading.Lock()


FROZEN = bool(getattr(sys, "frozen", False))     # True inside the portable MagicApply.exe


def _bot_command():
    '''The command used to launch the bot. Isolated so tests can monkeypatch it.'''
    if FROZEN:
        return [sys.executable, "--run-bot"]         # the exe starts itself again, in bot mode
    return [sys.executable, os.path.join(ROOT, "runAiBot.py")]


def _is_running() -> bool:
    '''True if the tracked bot subprocess exists and has not exited.'''
    global _bot_proc
    if _bot_proc is None:
        return False
    if _bot_proc.poll() is None:
        return True
    # Process has exited; clean up tracking + PID file.
    _bot_proc = None
    _remove_pid_file()
    return False


def _remove_pid_file():
    try:
        os.remove(PID_PATH)
    except OSError:
        pass


def _terminate(proc) -> None:
    '''Terminate the subprocess and, where feasible, its child processes.'''
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # Kill the whole process tree on Windows.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            # We launched with start_new_session=True, so the child is its own
            # process-group leader; signal the whole group.
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    # Give it a moment, then force-kill if still alive.
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass


@app.route('/')
def home():
    """Serve the control panel single-page app."""
    return render_template('control_panel.html')


@app.route('/history')
def history():
    """Serve the applied-jobs history page."""
    return render_template('index.html')


# The applied-jobs history CSV the bot writes, and how its columns map to the JSON
# keys the history page consumes.
_HISTORY_CSV = 'all_applied_applications_history.csv'
_FAILED_CSV = 'all_failed_applications_history.csv'
_HISTORY_FIELDS = {
    'Job ID': 'Job_ID',
    'Title': 'Title',
    'Company': 'Company',
    'HR Name': 'HR_Name',
    'HR Link': 'HR_Link',
    'HR Email': 'HR_Email',
    'HR Phone': 'HR_Phone',
    'Job Link': 'Job_Link',
    'External Job link': 'External_Job_link',
    'Date Applied': 'Date_Applied',
}

# Application status tracking, kept in its own small JSON file (keyed by Job ID)
# rather than the bot's CSV - so the bot's writer never needs to know about it,
# and clearing/re-running the bot doesn't clobber statuses the user set by hand.
_STATUS_PATH = os.path.join(DATA_DIR, 'all excels', 'job_statuses.json')
VALID_JOB_STATUSES = ['Applied', 'Interviewing', 'Offer', 'Rejected', 'Ghosted', 'Withdrawn']


def _load_statuses() -> dict:
    try:
        with open(_STATUS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_statuses(data: dict) -> None:
    os.makedirs(os.path.dirname(_STATUS_PATH), exist_ok=True)
    with open(_STATUS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


@app.route('/applied-jobs', methods=['GET'])
def get_applied_jobs():
    """Return the applied-jobs history as JSON for the history page."""
    csv_path = os.path.join(PATH, _HISTORY_CSV)
    if not os.path.exists(csv_path):
        return jsonify({"error": "No applications history found yet."}), 404
    try:
        jobs = []
        statuses = _load_statuses()
        with open(csv_path, 'r', encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                job = {key: row.get(col) or '' for col, key in _HISTORY_FIELDS.items()}
                job['Status'] = statuses.get(job['Job_ID'], {}).get('status', 'Applied')
                jobs.append(job)
        return jsonify(jobs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/applied-jobs/export', methods=['GET'])
def export_applied_jobs():
    """Download the full applied-jobs history CSV, exactly as the bot wrote it."""
    csv_path = os.path.join(PATH, _HISTORY_CSV)
    if not os.path.exists(csv_path):
        return jsonify({"error": "No applications history found yet."}), 404
    download_name = 'applied_jobs_history_{}.csv'.format(datetime.now().strftime('%Y-%m-%d_%H%M%S'))
    return send_file(csv_path, mimetype='text/csv', as_attachment=True, download_name=download_name)


@app.route('/applied-jobs/clear', methods=['POST'])
def clear_applied_jobs():
    """Deletes the applied-jobs history CSV. The bot recreates it (with a fresh header) on its next application."""
    csv_path = os.path.join(PATH, _HISTORY_CSV)
    try:
        if os.path.exists(csv_path):
            os.remove(csv_path)
        if os.path.exists(_STATUS_PATH):
            os.remove(_STATUS_PATH)
    except OSError as err:
        return jsonify({"error": f"Could not clear history: {err}"}), 500
    return jsonify({"message": "Cleared."})


@app.route('/applied-jobs/<job_id>/status', methods=['PUT'])
def set_job_status(job_id):
    """Sets the tracked application status (Applied/Interviewing/Offer/Rejected/Ghosted/Withdrawn) for one job."""
    payload = request.get_json(silent=True)
    status = payload.get('status') if isinstance(payload, dict) else None
    if status not in VALID_JOB_STATUSES:
        return jsonify({"error": f"status must be one of {VALID_JOB_STATUSES}"}), 400
    statuses = _load_statuses()
    statuses[job_id] = {"status": status, "updated": datetime.now().isoformat()}
    try:
        _save_statuses(statuses)
    except OSError as err:
        return jsonify({"error": f"Could not save status: {err}"}), 500
    return jsonify({"message": "Updated.", "status": status})


@app.route('/applied-jobs/<job_id>', methods=['PUT'])
def mark_job_applied(job_id):
    """Stamp one job's 'Date Applied' (matched by Job ID) with the current time."""
    csv_path = os.path.join(PATH, _HISTORY_CSV)
    if not os.path.exists(csv_path):
        return jsonify({"error": f"History file not found at {csv_path}"}), 404
    try:
        with open(csv_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            rows = list(reader)
        target = next((row for row in rows if row.get('Job ID') == job_id), None)
        if target is None:
            return jsonify({"error": f"Job ID {job_id} not found"}), 404
        current = (target.get('Date Applied') or '').strip()
        if current and current != 'Pending':
            # The bot (or an earlier click) already recorded the real date - clicking a link must not overwrite it.
            return jsonify({"message": "Already marked as applied.", "unchanged": True}), 200
        target['Date Applied'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Write to a side file and swap it in, so a crash mid-write can't destroy the whole history.
        temp_path = csv_path + ".tmp"
        with open(temp_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore', restval='')
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, csv_path)
        return jsonify({"message": "Date Applied updated."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===========================================================================
# Resume builder API (optional - needs `pip install -r requirements-resume.txt`)
# ===========================================================================
from modules import resume_builder


@app.route('/api/resume-builder/status', methods=['GET'])
def api_resume_builder_status():
    '''Whether RenderCV is installed, so the UI can show an install hint instead of failing.'''
    return jsonify({"available": resume_builder.is_available(), "frozen": FROZEN})


@app.route('/api/resume-builder/yaml', methods=['GET'])
def api_get_resume_yaml():
    '''Returns the current content of the saved resume data (resume_data.yaml).'''
    try:
        with open(resume_builder.RESUME_YAML_PATH, 'r', encoding='utf-8') as f:
            return jsonify({"content": f.read()})
    except FileNotFoundError:
        return jsonify({"content": ""})
    except OSError as err:
        return jsonify({"error": str(err)}), 500


@app.route('/api/resume-builder/yaml', methods=['POST'])
def api_save_resume_yaml():
    '''Saves edited YAML content back to resume_data.yaml.'''
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        return jsonify({"error": "Expected a JSON object with a string 'content' field"}), 400
    try:
        os.makedirs(os.path.dirname(resume_builder.RESUME_YAML_PATH), exist_ok=True)
        with open(resume_builder.RESUME_YAML_PATH, 'w', encoding='utf-8') as f:
            f.write(payload["content"])
    except OSError as err:
        return jsonify({"error": f"Could not save resume data: {err}"}), 500
    return jsonify({"message": "Saved."})


@app.route('/api/resume-builder/generate', methods=['POST'])
def api_generate_resume():
    '''Renders resume_data.yaml into a PDF via RenderCV.'''
    success, message = resume_builder.generate_ats_resume()
    if not success:
        return jsonify({"success": False, "error": message}), 400
    return jsonify({"success": True, "path": message, "filename": os.path.basename(message)})


@app.route('/api/resume-builder/download/<path:filename>', methods=['GET'])
def api_download_resume(filename):
    '''Downloads a previously generated resume PDF by filename.'''
    safe_name = os.path.basename(filename)
    pdf_path = os.path.join(resume_builder.RESUME_OUTPUT_DIR, safe_name)
    if not safe_name.lower().endswith('.pdf') or not os.path.isfile(pdf_path):
        return jsonify({"error": "Resume PDF not found."}), 404
    return send_file(pdf_path, mimetype='application/pdf', as_attachment=True, download_name=safe_name)


# ===========================================================================
# Failed jobs (the bot skips/errors it recorded, with the debug screenshot it
# took at the time - previously only reachable by digging through the CSV
# and logs/screenshots folder by hand)
# ===========================================================================
SCREENSHOTS_DIR = os.path.join(DATA_DIR, "logs", "screenshots")
_FAILED_FIELDS = {
    'Job ID': 'Job_ID',
    'Job Link': 'Job_Link',
    'Assumed Reason': 'Reason',
    'Date listed': 'Date_Listed',
    'Date Tried': 'Date_Tried',
    'External Job link': 'External_Job_link',
    'Screenshot Name': 'Screenshot_Name',
}


@app.route('/failures')
def failures_page():
    """Serve the failed-jobs review page."""
    return render_template('failures.html')


@app.route('/failed-jobs', methods=['GET'])
def get_failed_jobs():
    """Return the failed-jobs history as JSON for the failures page."""
    csv_path = os.path.join(PATH, _FAILED_CSV)
    if not os.path.exists(csv_path):
        return jsonify({"error": "No failed applications recorded yet."}), 404
    try:
        jobs = []
        with open(csv_path, 'r', encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                jobs.append({key: row.get(col) or '' for col, key in _FAILED_FIELDS.items()})
        return jsonify(jobs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/failed-jobs/export', methods=['GET'])
def export_failed_jobs():
    """Download the full failed-jobs history CSV, exactly as the bot wrote it."""
    csv_path = os.path.join(PATH, _FAILED_CSV)
    if not os.path.exists(csv_path):
        return jsonify({"error": "No failed applications recorded yet."}), 404
    download_name = 'failed_jobs_history_{}.csv'.format(datetime.now().strftime('%Y-%m-%d_%H%M%S'))
    return send_file(csv_path, mimetype='text/csv', as_attachment=True, download_name=download_name)


@app.route('/failed-jobs/clear', methods=['POST'])
def clear_failed_jobs():
    """Deletes the failed-jobs history CSV. The bot recreates it (with a fresh header) on its next failure."""
    csv_path = os.path.join(PATH, _FAILED_CSV)
    try:
        if os.path.exists(csv_path):
            os.remove(csv_path)
    except OSError as err:
        return jsonify({"error": f"Could not clear failed jobs: {err}"}), 500
    return jsonify({"message": "Cleared."})


@app.route('/screenshots/<path:filename>', methods=['GET'])
def get_screenshot(filename):
    """Serves a debug screenshot the bot took when a job failed."""
    safe_name = os.path.basename(filename)
    image_path = os.path.join(SCREENSHOTS_DIR, safe_name)
    if not safe_name.lower().endswith('.png') or not os.path.isfile(image_path):
        return jsonify({"error": "Screenshot not found."}), 404
    return send_file(image_path, mimetype='image/png')


# ===========================================================================
# Control-panel API
# ===========================================================================
@app.route('/api/schema', methods=['GET'])
def api_schema():
    '''Returns the field schema the UI renders its forms from.'''
    return jsonify(config_schema.SCHEMA)


@app.route('/api/config', methods=['GET'])
def api_get_config():
    '''
    Returns the effective config: pristine defaults overlaid with the current
    user_config.json, grouped by config module (secrets, personals, questions,
    search, settings).
    '''
    return jsonify(_effective_config())


@app.route('/api/defaults', methods=['GET'])
def api_get_defaults():
    '''
    Returns the pristine, un-overridden config defaults - no personal data,
    regardless of what's currently saved in user_config.json.

    user_config.json is one file per Windows user account, so if this tool is
    shared by multiple people signed into the same Windows account (a shared
    office PC, for example - not just a different machine), they'd otherwise
    all see whoever saved last. The control panel calls this instead of
    /api/config on a browser's first visit (before it has anything of its own
    cached), so a browser that's never been used with this tool shows a clean
    slate rather than someone else's name.
    '''
    return jsonify(copy.deepcopy(DEFAULTS))


@app.route('/api/config', methods=['POST'])
def api_save_config():
    '''
    Accepts {config_module: {key: value}}, validates against the schema, coerces
    each value to its declared type, rejects unknown modules/keys, merges into
    user_config.json (read-modify-write) and returns the full saved config.
    '''
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected a JSON object of {section: {key: value}}"}), 400

    try:
        coerced, unknown = _validate_settings(payload)
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    if unknown:
        return jsonify({"error": "Unknown settings rejected", "unknown": unknown}), 400

    # Read-modify-write user_config.json.
    current = _overrides.load_user_config()
    for section, values in coerced.items():
        target = current.get(section)
        if not isinstance(target, dict):
            target = {}
        target.update(values)
        current[section] = target

    try:
        os.makedirs(os.path.dirname(USER_CONFIG_PATH), exist_ok=True)
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(current, file, indent=2, ensure_ascii=False)
    except OSError as err:
        return jsonify({"error": f"Could not save settings: {err}"}), 500

    return jsonify(current)


@app.route('/api/run', methods=['POST'])
def api_run():
    '''Starts the bot as a subprocess if it isn't already running.'''
    global _bot_proc
    with _bot_lock:
        if _is_running():
            return jsonify({"running": True, "pid": _bot_proc.pid,
                            "message": "The tool is already running."})
        log_file = None
        try:
            # Truncate the log at the start of each run.
            log_file = open(LOG_PATH, "w", encoding="utf-8")
            # PYTHONIOENCODING=utf-8: without it, the bot's own print() calls encode
            # using the Windows console's codepage (cp1252) even though stdout is
            # redirected to this UTF-8 log file - job titles/companies/descriptions
            # scraped from LinkedIn routinely contain characters cp1252 can't encode
            # (accents, emoji, non-Latin scripts), crashing print_lg() and showing a
            # misleading "log.txt is occupied" alert that has nothing to do with the file.
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            if FROZEN:
                env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # make the second copy of the exe unpack itself fresh
            popen_kwargs = {
                "cwd": DATA_DIR if FROZEN else ROOT,
                "stdout": log_file,
                "stderr": subprocess.STDOUT,
                "env": env,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            _bot_proc = subprocess.Popen(_bot_command(), **popen_kwargs)
            # The bot has its own copy of the handle; close ours explicitly instead of relying on garbage collection.
            log_file.close()
        except Exception as err:
            if log_file is not None:
                log_file.close()
            return jsonify({"running": False, "error": str(err)}), 500
        try:
            with open(PID_PATH, "w", encoding="utf-8") as pid_file:
                pid_file.write(str(_bot_proc.pid))
        except OSError:
            pass
        return jsonify({"running": True, "pid": _bot_proc.pid})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    '''Stops the running bot subprocess (and its children where possible).'''
    global _bot_proc
    with _bot_lock:
        if _bot_proc is not None:
            _terminate(_bot_proc)
            _bot_proc = None
        _remove_pid_file()
        return jsonify({"running": False})


@app.route('/api/status', methods=['GET'])
def api_status():
    '''Reports whether the bot subprocess is currently running.'''
    with _bot_lock:
        running = _is_running()
        pid = _bot_proc.pid if (running and _bot_proc is not None) else None
        return jsonify({"running": running, "pid": pid})


# ===========================================================================
# Session data: nothing is kept between sessions. People download a backup
# file to keep their data, restore it next time, and everything is erased
# when the panel closes (see modules/session_data.py).
# ===========================================================================
_session_started = False


@app.before_request
def _note_session_started():
    '''Marks that someone actually used the panel, so a failed launch never erases anything.'''
    global _session_started
    _session_started = True


# Settings that decide where the bot reads/writes files. A backup never gets to set these.
_BACKUP_BLOCKED_KEYS = {"file_name", "failed_file_name", "logs_folder_path", "generated_resume_path"}


def _is_plain_value(value) -> bool:
    scalar = (str, int, float, bool)
    return isinstance(value, scalar) or (isinstance(value, list) and all(isinstance(item, scalar) for item in value))


def _resume_path_stays_private(path: str) -> bool:
    '''True for a relative resume path that resolves inside the private data folder.'''
    if os.path.isabs(path):
        return False
    resolved = os.path.abspath(os.path.join(DATA_DIR, path))
    return os.path.commonpath([resolved, os.path.abspath(DATA_DIR)]) == os.path.abspath(DATA_DIR)


def _restore_config_validator(config: dict) -> dict:
    '''
    Cleans the settings out of a backup file before they are written back:
    known fields go through the same checks as the Save button; settings the
    form doesn't show (e.g. the AI "about me" text) are kept if they are plain
    values; anything that could point the bot at other files on this computer
    is dropped.
    '''
    try:
        cleaned, _unknown = _validate_settings(config)
    except ValueError as err:
        raise session_data.BackupError(f"The settings in this backup are invalid: {err}")
    known = config_schema.valid_keys()
    for section, values in config.items():
        if section not in known or not isinstance(values, dict):
            continue
        for key, value in values.items():
            if key in known[section] or key in _BACKUP_BLOCKED_KEYS or not _is_plain_value(value):
                continue
            cleaned.setdefault(section, {})[key] = value
    resume_path = cleaned.get("questions", {}).get("default_resume_path")
    if isinstance(resume_path, str) and resume_path and not _resume_path_stays_private(resume_path):
        del cleaned["questions"]["default_resume_path"]
    return cleaned


@app.route('/api/data-status', methods=['GET'])
def api_data_status():
    '''Whether the private data folder holds anything, and whether erase-on-exit is switched off.'''
    return jsonify({"has_data": session_data.has_data(DATA_DIR), "keep_data": session_data.keep_data_enabled()})


@app.route('/api/backup', methods=['GET'])
def api_backup():
    '''Downloads everything the person entered as a single backup file. `?secrets=0` leaves out passwords and API keys.'''
    backup = session_data.build_backup(DATA_DIR, include_secrets=request.args.get("secrets", "1") != "0")
    filename = "AutoJobApplier-backup-{}.json".format(datetime.now().strftime('%Y-%m-%d'))
    return app.response_class(
        json.dumps(backup, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="{}"'.format(filename), "Cache-Control": "no-store"},
    )


@app.route('/api/restore', methods=['POST'])
def api_restore():
    '''Loads a backup file (as JSON) back into the tool. A bad file changes nothing.'''
    try:
        restored = session_data.restore_backup(request.get_json(silent=True), DATA_DIR,
                                               config_validator=_restore_config_validator)
    except session_data.BackupError as err:
        return jsonify({"error": str(err)}), 400
    except OSError as err:
        return jsonify({"error": f"Could not restore the backup: {err}"}), 500
    return jsonify({"restored": restored})


_cleanup_lock = threading.Lock()
_cleanup_done = False


def _shutdown_cleanup() -> None:
    '''
    Runs once when the panel ends, however it ends (Finish button, Ctrl+C,
    closing the window): stops a running bot so it lets go of Chrome and its
    files, then erases all session data.
    '''
    global _cleanup_done
    with _cleanup_lock:
        if _cleanup_done or not _session_started:
            return
        _cleanup_done = True
    got_lock = _bot_lock.acquire(timeout=3)
    try:
        if _bot_proc is not None:
            _terminate(_bot_proc)
    except Exception:
        pass
    finally:
        if got_lock:
            _bot_lock.release()
    try:
        erased = session_data.wipe_if_enabled(DATA_DIR)
    except Exception as err:
        erased = False
        print(f"\n  Could not erase your data automatically: {err}\n", flush=True)
    if erased:
        print("\n  Your data has been erased from this computer.\n", flush=True)
    elif session_data.keep_data_enabled():
        print("\n  Keep-data mode is on - nothing was erased.\n", flush=True)


def _finish_and_exit() -> None:
    '''Erase everything and end the whole process (which closes the panel window).'''
    _shutdown_cleanup()
    os._exit(0)


@app.route('/api/quit', methods=['POST'])
def api_quit():
    '''"Finish & erase": replies first, then stops the bot, erases the data and exits.'''
    threading.Timer(0.5, _finish_and_exit).start()
    return jsonify({"erased": not session_data.keep_data_enabled()})


_console_handler_ref = None


def _install_exit_hooks() -> None:
    '''
    Makes sure the erase also happens when the panel is ended without the Finish
    button: normal interpreter exit, a terminate signal, or - on Windows -
    clicking the X on the console window (which never reaches atexit).
    '''
    atexit.register(_shutdown_cleanup)

    def _exit_via_atexit(signum, frame):
        sys.exit(0)

    for name in ("SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _exit_via_atexit)
            except (ValueError, OSError):
                pass

    if os.name == "nt":
        import ctypes
        global _console_handler_ref
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

        def _on_console_event(event_type):
            # 2 = window closed, 5 = user logging off, 6 = system shutting down
            if event_type in (2, 5, 6):
                _shutdown_cleanup()
                os._exit(0)
            return 0

        _console_handler_ref = handler_type(_on_console_event)  # must stay referenced
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler_ref, True)


def _csv_row_count(filename: str) -> int:
    '''
    Counts data rows (excludes the header) in a CSV under PATH. Returns 0 if it
    doesn't exist. Uses csv.reader rather than counting newlines - fields like a
    failed job's stack trace routinely contain embedded newlines, which would
    wildly overcount a plain line-count.
    '''
    csv_path = os.path.join(PATH, filename)
    if not os.path.exists(csv_path):
        return 0
    try:
        with open(csv_path, 'r', encoding='utf-8', newline='') as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except OSError:
        return 0


@app.route('/api/run-summary', methods=['GET'])
def api_run_summary():
    '''Quick counts for the Run tab: total applied and total failed, all-time.'''
    return jsonify({
        "applied": _csv_row_count(_HISTORY_CSV),
        "failed": _csv_row_count(_FAILED_CSV),
    })


@app.route('/api/logs', methods=['GET'])
def api_logs():
    '''
    Returns the run log starting from byte offset ?offset=N, plus the byte
    offset to read from next time. The UI polls this while the bot runs.
    '''
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    if offset < 0:
        offset = 0
    if not os.path.exists(LOG_PATH):
        return jsonify({"content": "", "next_offset": 0})
    try:
        with open(LOG_PATH, "rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            if offset > size:
                # Log was truncated (a new run started); start over.
                offset = 0
            log_file.seek(offset)
            data = log_file.read()
        for trim in range(4):                       # a chunk may end part-way through an emoji / accented letter
            try:
                content = data[:len(data) - trim].decode("utf-8")
                data = data[:len(data) - trim]
                break
            except UnicodeDecodeError:
                continue
        else:
            content = data.decode("utf-8", errors="replace")
        return jsonify({"content": content, "next_offset": offset + len(data)})
    except OSError as err:
        return jsonify({"content": "", "next_offset": offset, "error": str(err)})


@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    '''Empties the activity log shown in the Run tab.'''
    try:
        open(LOG_PATH, "w", encoding="utf-8").close()
    except OSError as err:
        return jsonify({"error": f"Could not clear the log: {err}"}), 500
    return jsonify({"message": "Cleared."})


PANEL_LOCK_PATH = os.path.join(DATA_DIR, ".panel.lock")


def _running_instance_port():
    '''
    Returns the port of an already-running control panel from a previous
    launch, if one is still alive - so a second launch (e.g. double-clicking
    start.bat again while one is already open) reuses it instead of starting
    a second server that collides with the first one over logs/log.txt and
    .bot_run.log.
    '''
    try:
        with open(PANEL_LOCK_PATH, "r", encoding="utf-8") as f:
            recorded_port = int(f.read().strip())
    except (OSError, ValueError):
        return None
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{recorded_port}/api/status", timeout=1) as resp:
            if resp.status == 200:
                return recorded_port
    except Exception:
        return None
    return None


def _write_lock(port: int) -> None:
    try:
        with open(PANEL_LOCK_PATH, "w", encoding="utf-8") as f:
            f.write(str(port))
    except OSError:
        pass


def _remove_lock() -> None:
    try:
        os.remove(PANEL_LOCK_PATH)
    except OSError:
        pass


def _claim_port(port: int):
    '''
    Binds `port` and returns the held socket, or None if something else
    already has it. Binding a TCP port is a single atomic kernel operation -
    unlike the old "check if something answers, then separately write a lock
    file" approach, there's no window where two near-simultaneous launches
    (e.g. start.bat double-clicked twice) can both see "nothing running yet"
    and both proceed. The caller closes this socket immediately before handing
    the same port to app.run(), so the only remaining race is the microseconds
    between that close() and Flask's own bind - not the whole startup sequence.
    '''
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", port))
        return s
    except OSError:
        s.close()
        return None


def _claim_free_port(start: int, tries: int = 25):
    '''Claims the first free port from `start` upward. Returns (port, held_socket), or (None, None).'''
    for port in range(start, start + tries):
        probe = _claim_port(port)
        if probe is not None:
            return port, probe
    return None, None


def _wait_for_running_instance(seconds: float = 5.0):
    '''Waits briefly for a panel that another launch is still starting (its port answers a moment after it is claimed).'''
    import time
    end = time.monotonic() + seconds
    while True:
        port = _running_instance_port()
        if port is not None or time.monotonic() >= end:
            return port
        time.sleep(0.5)


def main() -> None:
    '''Starts the local control panel (or reuses one that is already running).'''
    # SECURITY: localhost only, debug OFF. This app handles credentials.
    open_browser = os.environ.get("PANEL_OPEN_BROWSER", "").strip() not in ("", "0", "false", "False")

    requested = os.environ.get("PORT", "").strip()
    target_port = int(requested) if requested.isdigit() else 5000

    # A panel we started earlier may be on a different port than the one asked for (if 5000 was busy),
    # so ask the lock file first.
    existing_port = _running_instance_port()
    probe = None
    if existing_port is None:
        probe = _claim_port(target_port)
        if probe is None:
            # The port is taken. Either another launch of this app is still starting (wait for it) or a
            # completely different program owns it (macOS AirPlay uses 5000) - never send the person there.
            existing_port = _wait_for_running_instance()
    if existing_port is not None:
        # An earlier launch of this same app is alive (e.g. start.bat was double-clicked twice): reuse it
        # instead of starting a second server that would collide with the first over the log and data files.
        url = "http://127.0.0.1:%d" % existing_port
        print(
            "\n  The control panel is already running at:  %s\n"
            "  Opening that instead of starting a second one.\n" % url,
            flush=True,
        )
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        sys.exit(0)

    port = target_port
    if probe is None:
        port, probe = _claim_free_port(target_port + 1)
        if probe is None:
            print("\n  Could not find a free port to start the control panel on. Close other programs and try again.\n", flush=True)
            sys.exit(1)
        print("\n  Port %d is used by another program - using port %d instead.\n" % (target_port, port), flush=True)
    _write_lock(port)
    # Only the instance that owns the panel installs the erase - a second launch that
    # exits above must never wipe the first one's data.
    _install_exit_hooks()
    probe.close()  # Release right before Flask binds for real - minimal gap.
    url = "http://127.0.0.1:%d" % port
    if session_data.keep_data_enabled():
        data_note = "Keep-data mode is ON: your data is NOT erased when this window closes."
    else:
        data_note = ("Your data is erased when you close this window - download a backup\n"
                     "  from the panel first if you want to keep it.")
    print(
        "\n  Control panel ready at:  %s\n"
        "  Keep this window open while you use the tool; close it to stop.\n"
        "  %s\n" % (url, data_note),
        flush=True,
    )
    # The launcher scripts set PANEL_OPEN_BROWSER=1 so the browser opens itself,
    # to the right port, cross-platform. Running `python app.py` by hand won't.
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        app.run(host="127.0.0.1", port=port, debug=False)
    finally:
        _shutdown_cleanup()
        _remove_lock()


if __name__ == '__main__':
    main()
