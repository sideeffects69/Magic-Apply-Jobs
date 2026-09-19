'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

A plain-text report someone can attach to a bug report. The tool erases everything
when it closes, so without this there would be nothing to look at after a run that
went wrong. It holds the recent activity log, why jobs failed and which settings were
on - with the person's own details (name, email, phone, address, passwords, API keys,
links, folder names) masked. It never includes the applied-jobs list or screenshots.

Masking is best effort, so the person is told to read the file before sharing it.
'''

import csv
import os
import platform
import re
import sys
from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit

from modules.form_profile import Profile

MAX_LOG_LINES = 400
MAX_LOG_LINE_CHARS = 500
MAX_FAILED_ROWS = 60
MAX_CELL_CHARS = 600
_TAIL_BYTES = 256 * 1024

# Sections of the saved settings whose text values are personal. Every value found in them is masked wherever it shows up.
_PERSONAL_SECTIONS = ("personals", "questions", "secrets")
# Not personal however they were filled in (a path inside the tool's own folder, a small number).
_NOT_PERSONAL_KEYS = {"default_resume_path", "confidence_level", "years_of_experience", "notice_period",
                      "ai_provider", "llm_model", "llm_api_url", "llm_temperature"}
# Choices rather than details: masking "No" everywhere would make the log unreadable.
_GENERIC_ANSWERS = {"yes", "no", "decline", "other", "true", "false", "none"}
_MONEY_KEYS = ("desired_salary", "current_ctc")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://[^\s\"'<>)\]]+")
_LINKEDIN_PROFILE = re.compile(r"(?i)(linkedin\.com/in/)[^/\s\"'?#]+")
_WINDOWS_USER = re.compile(r"(?i)\b([a-z]):\\Users\\[^\\\s\"']+")
_UNIX_USER = re.compile(r"(/Users|/home)/[^/\s\"']+")
_PHONE = re.compile(r"(?<!\w)\+\d[\d\s().-]{7,}\d(?!\w)|(?<!\w)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\w)")
_SECRET = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{20,})\b")


def personal_values(config: dict) -> list[tuple[str, str]]:
    '''(setting name, value) for every personal value in the saved settings, longest first.'''
    found = {}
    for section in _PERSONAL_SECTIONS:
        values = config.get(section)
        for key, value in (values.items() if isinstance(values, dict) else []):
            if key in _NOT_PERSONAL_KEYS or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                text = str(int(value)) if key in _MONEY_KEYS and value >= 1000 else ""
            elif isinstance(value, str):
                text = value.strip()
            else:
                continue
            if len(text) < 2 or text.lower() in _GENERIC_ANSWERS or (text.isdigit() and len(text) < 5):
                continue
            found.setdefault(text, key)
    return sorted(((key, text) for text, key in found.items()), key=lambda item: -len(item[1]))


def _looks_like_phone(text: str) -> bool:
    return len(re.sub(r"\D", "", text)) >= 7 and re.fullmatch(r"[\d\s+().-]+", text) is not None


def _phone_pattern(text: str) -> re.Pattern:
    '''Matches one phone number however it is written: +91 98765 43210, 98765-43210, (987) 654 3210 - with or without its country code.'''
    digits = re.sub(r"\D", "", text)
    forms = [digits] + ([digits[-10:]] if len(digits) > 10 else [])
    return re.compile("|".join(r"(?<!\d)\+?" + r"[\s().-]*".join(form) + r"(?!\d)" for form in forms))


def _shorten_url(match: re.Match, keep_path: bool = True) -> str:
    '''A link without its query string, fragment or login part - those are where tokens live.'''
    url, trailing = match.group(0), ""
    while url and url[-1] in ".,;:!?":
        trailing, url = url[-1] + trailing, url[:-1]
    try:
        parts = urlsplit(url)
    except ValueError:
        return "[link]" + trailing
    if not parts.netloc:
        return "[link]" + trailing
    host = parts.netloc.rsplit("@", 1)[-1]
    path = parts.path[:80] if keep_path else ""
    return f"{parts.scheme}://{host}{path}{trailing}"


def host_of(link: str) -> str:
    '''Just the site name of a link ("boards.greenhouse.io"), or "" if it isn't one.'''
    try:
        return urlsplit(link.strip()).netloc.rsplit("@", 1)[-1] if link.strip().lower().startswith("http") else ""
    except ValueError:
        return ""


class Redactor:
    '''Masks one person's details in text. Built once from their saved settings and the folders the tool uses.'''

    def __init__(self, config: dict | None = None, known_paths=()):
        self._literal = []          # (pattern, replacement) - most specific first
        paths = sorted(((label, path) for label, path in known_paths if path and len(path) >= 4), key=lambda item: -len(item[1]))
        for label, path in paths:
            variants = {path, path.replace("\\", "/"), path.replace("/", "\\")}
            pattern = "|".join(re.escape(variant) for variant in sorted(variants, key=len, reverse=True))
            self._literal.append((re.compile(pattern, re.IGNORECASE), f"[{label}]"))
        for key, text in personal_values(config or {}):
            if _looks_like_phone(text):
                self._literal.append((_phone_pattern(text), f"[{key}]"))
            else:
                self._literal.append((re.compile(r"(?<!\w)" + re.escape(text) + r"(?!\w)", re.IGNORECASE), f"[{key}]"))

    def __call__(self, text: str) -> str:
        for pattern, replacement in self._literal:
            text = pattern.sub(lambda _match, replacement=replacement: replacement, text)
        text = _SECRET.sub("[secret]", text)
        text = _URL.sub(_shorten_url, text)         # before emails: a link's "user:password@host" must not be read as an email
        text = _LINKEDIN_PROFILE.sub(lambda match: match.group(1) + "[profile]", text)
        text = _EMAIL.sub("[email]", text)
        text = _WINDOWS_USER.sub(lambda match: match.group(1) + ":\\Users\\[user]", text)
        text = _UNIX_USER.sub(lambda match: match.group(1) + "/[user]", text)
        return _PHONE.sub("[phone]", text)


# ---------------------------------------------------------------------------
# Reading the tool's files (each one may be missing or damaged - that must never break the report)
# ---------------------------------------------------------------------------
def _read_tail(path: str, max_lines: int) -> list[str] | None:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_BYTES))
            data = handle.read()
    except OSError:
        return None
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > _TAIL_BYTES and lines:
        lines = lines[1:]                       # the first line of a partial read is cut in the middle
    return [line for line in lines if line.strip()][-max_lines:]


def _read_csv(path: str) -> list[dict] | None:
    '''Rows of a CSV the bot wrote, or None if it is missing or unreadable.'''
    try:
        csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
            return [row for row in csv.DictReader(handle) if any(isinstance(value, str) and value.strip() for value in row.values())]
    except (OSError, csv.Error, ValueError):
        return None


def _cut(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _positive(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def _profile_lines(config: dict) -> list[str]:
    '''Which profile details are set, without saying what they are.'''
    personals = config.get("personals") or {}
    questions = config.get("questions") or {}
    secrets = config.get("secrets") or {}
    essentials = Profile.from_values(first_name=personals.get("first_name", ""), last_name=personals.get("last_name", ""),
                                     email=personals.get("email", ""), phone=personals.get("phone_number", ""))
    missing = essentials.missing_essentials()
    unset = []
    if not str(questions.get("years_of_experience", "") or "").strip():
        unset.append("years of experience")
    if not _positive(questions.get("desired_salary")):
        unset.append("desired salary")
    if not _positive(questions.get("current_ctc")):
        unset.append("current salary")
    try:
        if float(questions.get("notice_period", -1)) < 0:
            unset.append("notice period")
    except (TypeError, ValueError):
        unset.append("notice period")
    lines = ["Details the tool needs before it can apply: " + (", ".join(missing) + " - NOT SET" if missing else "all set")]
    lines.append("Left 'not set' (a form that asks is left for a person or the AI): " + (", ".join(unset) if unset else "none"))
    lines.append("AI answers: " + ("on (" + str(secrets.get("ai_provider", "?")) + ")" if secrets.get("use_AI") is True else "off"))
    lines.append("Google account named for sign-in: " + ("yes" if str(secrets.get("google_email", "") or "").strip() else "no (the first account Google shows is used)"))
    return lines


def _settings_lines(config: dict) -> list[str]:
    lines = []
    settings = config.get("settings") or {}
    for key in sorted(settings):
        if isinstance(settings[key], (bool, int, float)):        # only on/off switches and numbers - never text
            lines.append(f"{key} = {settings[key]}")
    search = config.get("search") or {}
    if isinstance(search.get("easy_apply_only"), bool):
        lines.append(f"easy_apply_only = {search['easy_apply_only']}")
    return lines


def _run_summary(history: list[dict] | None, failed: list[dict] | None) -> list[str]:
    lines = []
    if history is None:
        lines.append("Applied jobs recorded: none yet")
    else:
        easy = sum(1 for row in history if (row.get("External Job link") or "").strip() == "Easy Applied")
        lines.append(f"Applied jobs recorded: {len(history)} (LinkedIn Easy Apply: {easy}, other/company sites: {len(history) - easy})")
    lines.append("Failed or skipped jobs recorded: " + ("none yet" if failed is None else str(len(failed))))
    return lines


def _failed_lines(failed: list[dict] | None, redact: Redactor) -> list[str]:
    if not failed:
        return ["(none recorded yet)"]
    lines = []
    reasons = Counter()
    for row in failed:
        reason = (row.get("Assumed Reason") or "").strip()
        reasons[_cut(redact(reason.split(":")[0]), 90) or "(no reason recorded)"] += 1
    lines.append("Most common reasons: " + "; ".join(f"{text} x{count}" for text, count in reasons.most_common(5)))
    lines.append("")
    for number, row in enumerate(reversed(failed[-MAX_FAILED_ROWS:]), 1):
        when = _cut(row.get("Date Tried") or "", 30)
        lines.append(f"{number}. {when} - LinkedIn job {_cut(redact(row.get('Job ID') or '?'), 30)}")
        lines.append("   Why: " + _cut(redact(row.get("Assumed Reason") or ""), MAX_CELL_CHARS))
        site = host_of(row.get("External Job link") or "")
        if site:
            lines.append("   Company site: " + redact(site))
        trace = _cut(redact(row.get("Stack Trace") or ""), MAX_CELL_CHARS)
        if trace and trace.lower() != "none":
            lines.append("   Details: " + trace)
    return lines


def build_report(*, config: dict, history_csv: str, failed_csv: str, log_paths, known_paths=(),
                 bot_running: bool = False, frozen: bool = False, now: datetime | None = None) -> str:
    '''
    The whole report as text. Never raises because of a missing or damaged file.

    `config` is the effective settings ({section: {key: value}}), used to know what to mask.
    `log_paths` are tried in order; the first one that has content is used.
    '''
    redact = Redactor(config, known_paths)
    now = now or datetime.now()
    history, failed = _read_csv(history_csv), _read_csv(failed_csv)

    log_lines = []
    for path in log_paths:
        log_lines = _read_tail(path, MAX_LOG_LINES) or []
        if log_lines:
            break

    out = [
        "Magic Apply - Jobs - report",
        f"Created: {now.strftime('%Y-%m-%d %H:%M')}",
        f"Tool: {'portable exe' if frozen else 'run from source'} | {platform.platform()} | Python {platform.python_version()}",
        f"Bot running when this was made: {'yes' if bot_running else 'no'}",
        "",
        "Your name, email, phone, address, passwords, API keys, links to you and folder names are masked below, but the",
        "masking is automatic and can miss things. READ THIS FILE before you share it. It does not include your",
        "applied-jobs list or any screenshots.",
        "",
        "== Summary ==",
        *_run_summary(history, failed),
        *_profile_lines(config),
        "",
        "== Settings that change how it behaves ==",
        *(_settings_lines(config) or ["(none)"]),
        "",
        f"== Failed or skipped jobs (newest first, up to {MAX_FAILED_ROWS}) ==",
        *_failed_lines(failed, redact),
        "",
        f"== Activity log (last {MAX_LOG_LINES} lines) ==",
        *([_cut_line(redact(line)) for line in log_lines] or ["(no activity recorded yet)"]),
        "",
    ]
    return "\n".join(out)


def _cut_line(line: str) -> str:
    return line if len(line) <= MAX_LOG_LINE_CHARS else line[:MAX_LOG_LINE_CHARS - 1] + "…"


def report_filename(now: datetime | None = None) -> str:
    return "MagicApply-report-{}.txt".format((now or datetime.now()).strftime("%Y-%m-%d"))
