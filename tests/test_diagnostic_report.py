"""
The report a person can attach to a bug report. The tool erases everything when it closes, so this is what survives - and it
must never carry the person's own details with it. Everything runs in temp folders.
"""

import csv
from datetime import datetime

import pytest

import app as app_module
from modules.diagnostic_report import Redactor, build_report, host_of, personal_values

# Key-shaped fakes are built at run time so that no key-looking text sits in the public repository.
FAKE_API_KEY = "sk-" + "abcdefghijklmnopqrstuvwx"

CONFIG = {
    "personals": {"first_name": "Asha", "last_name": "Rao", "email": "asha.rao@example.org", "phone_number": "+91 98765 43210",
                  "current_city": "Springfield", "street": "12 Lake View Road", "zipcode": "62701", "state": "Illinois",
                  "country": "India"},
    "secrets": {"username": "asha.login@example.org", "password": "Tr0ub4dor&3", "llm_api_key": FAKE_API_KEY,
                "google_email": "asha.g@example.org", "use_AI": True, "ai_provider": "openai"},
    "questions": {"linkedIn": "https://www.linkedin.com/in/asha-rao-42", "website": "https://asha.dev",
                  "recent_employer": "Acme Widgets Ltd", "desired_salary": 900000, "current_ctc": 600000,
                  "years_of_experience": "3", "notice_period": 30, "require_visa": "No"},
    "settings": {"external_apply_enabled": True, "use_google_login": True, "pause_before_submit": False, "click_gap": 2,
                 "a_text_setting": "Asha Rao's private note"},
    "search": {"easy_apply_only": False},
}

PRIVATE = ["Asha", "Rao", "asha.rao@example.org", "98765 43210", "Springfield", "12 Lake View Road", "62701", "Illinois", "India",
           "asha.login@example.org", "Tr0ub4dor&3", FAKE_API_KEY, "asha.g@example.org", "asha-rao-42",
           "asha.dev", "Acme Widgets Ltd", "900000", "600000"]


def _leaks(text):
    return [value for value in PRIVATE if value.lower() in text.lower()]


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------
def test_every_personal_value_is_masked_wherever_it_appears():
    text = " | ".join([
        "Hello Asha Rao", "ASHA RAO in capitals", "mail asha.rao@example.org", "phone +91 98765 43210 / 9876543210 / 98765-43210",
        "city Springfield, Illinois 62701, India", "street 12 lake view road", "login asha.login@example.org pw Tr0ub4dor&3",
        "key " + FAKE_API_KEY, "google asha.g@example.org", "profile https://www.linkedin.com/in/asha-rao-42?x=1",
        "site https://asha.dev/about", "employer Acme Widgets Ltd", "salary 900000 and 600000",
    ])
    masked = Redactor(CONFIG)(text)
    assert not _leaks(masked), f"still visible: {_leaks(masked)}\n{masked}"


def test_details_that_are_not_in_the_settings_are_caught_too():
    masked = Redactor({})(" | ".join([
        "someone.else@corp.example", "call +44 20 7946 0958 or (555) 123-4567", r"C:\Users\Someone\Documents\x.txt",
        "/home/someone/project/file.py", "https://www.linkedin.com/in/some-other-person", "sk-" + "z" * 24,
        "gh" + "p_abcdefghijklmnopqrstuvwxyz0123",
    ]))
    for private in ("someone.else", "7946 0958", "123-4567", "Someone", "/home/someone", "some-other-person", "zzzzzzzz", "ghp_abcdef"):
        assert private not in masked, f"{private!r} still visible in: {masked}"


def test_links_keep_the_site_and_page_but_lose_tokens_and_logins():
    masked = Redactor({})("open https://boards.greenhouse.io/acme/jobs/123?gh_jid=9&token=SECRET#apply, "
                          "then https://user:pass@example.com/path.")
    assert "https://boards.greenhouse.io/acme/jobs/123" in masked
    assert "SECRET" not in masked and "gh_jid" not in masked and "user:pass" not in masked
    assert "https://example.com/path." in masked


def test_the_folders_the_tool_uses_are_masked_in_either_slash_style():
    redact = Redactor({}, known_paths=[("tool folder", r"C:\Users\Someone\OneDrive - Some Org\Documents\Tool")])
    masked = redact(r'File "C:\Users\Someone\OneDrive - Some Org\Documents\Tool\app.py" and C:/Users/Someone/OneDrive - Some Org/Documents/Tool/x')
    assert "Some Org" not in masked and "Someone" not in masked
    assert masked.count("[tool folder]") == 2


def test_what_helps_a_bug_report_survives_the_masking():
    line = ("Job 4012345678 on 2026-09-12: UnexpectedAlertPresentException. Answered Yes, 3 years. "
            "Required questions the tool can't answer: Do you have experience with Kubernetes? * (unrecognised question)")
    assert Redactor(CONFIG)(line) == line


def test_only_real_details_are_treated_as_personal():
    values = dict((text, key) for key, text in personal_values(CONFIG))
    assert "Asha" in values and "asha.rao@example.org" in values and "900000" in values
    for harmless in ("No", "3", "30", "openai", "True"):
        assert harmless not in values, f"{harmless!r} would be masked everywhere and make the log unreadable"


# ---------------------------------------------------------------------------
# The report itself
# ---------------------------------------------------------------------------
def _write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def files(tmp_path):
    history = tmp_path / "history.csv"
    _write_csv(history, ["Job ID", "Title", "Company", "External Job link"], [
        {"Job ID": "1", "Title": "ZZ-TITLE-MUST-NOT-APPEAR", "Company": "ZZ-COMPANY-MUST-NOT-APPEAR", "External Job link": "Easy Applied"},
        {"Job ID": "2", "Title": "ZZ-TITLE-MUST-NOT-APPEAR", "Company": "ZZ-COMPANY-MUST-NOT-APPEAR", "External Job link": "https://acme.example/apply?t=1"},
    ])
    failed = tmp_path / "failed.csv"
    _write_csv(failed, ["Job ID", "Job Link", "Date Tried", "Assumed Reason", "Stack Trace", "External Job link", "Screenshot Name"], [
        {"Job ID": "111", "Date Tried": "2026-09-19 10:00", "Assumed Reason": "Required questions the tool can't answer: Notice period? (no notice in your profile)",
         "Stack Trace": "None", "External Job link": "https://boards.greenhouse.io/acme/jobs/1?gh_jid=1"},
        {"Job ID": "222", "Date Tried": "2026-09-19 10:05", "Assumed Reason": "Unexpected error: KeyError",
         "Stack Trace": r'File "C:\Users\Someone\tool\runAiBot.py", line 9 - asha.rao@example.org', "External Job link": "Easy Applied"},
    ])
    log = tmp_path / "run.log"
    log.write_text("Starting for Asha Rao\nClicked \"Apply now\"\nGot the external application link \"https://acme.example/jobs/9?token=abc\"\n",
                   encoding="utf-8")
    return {"history_csv": str(history), "failed_csv": str(failed), "log_paths": [str(tmp_path / "missing.log"), str(log)]}


def _build(files, **extra):
    return build_report(config=CONFIG, now=datetime(2026, 9, 19, 16, 0), **{**files, **extra})


def test_the_report_says_what_happened_without_the_persons_details(files):
    text = _build(files)
    assert "Created: 2026-09-19 16:00" in text
    assert "Applied jobs recorded: 2 (LinkedIn Easy Apply: 1, other/company sites: 1)" in text
    assert "Failed or skipped jobs recorded: 2" in text
    assert "Required questions the tool can't answer" in text and "Company site: boards.greenhouse.io" in text
    assert 'Clicked "Apply now"' in text and "https://acme.example/jobs/9" in text and "token=abc" not in text
    assert not _leaks(text), f"still visible: {_leaks(text)}\n{text}"
    assert "Someone" not in text


def test_the_applied_jobs_list_is_never_included(files):
    assert "ZZ-TITLE-MUST-NOT-APPEAR" not in _build(files) and "ZZ-COMPANY-MUST-NOT-APPEAR" not in _build(files)


def test_a_settings_value_that_is_text_is_never_listed(files):
    text = _build(files)
    assert "external_apply_enabled = True" in text and "click_gap = 2" in text
    assert "a_text_setting" not in text


def test_a_report_with_nothing_recorded_yet_still_works(tmp_path):
    text = build_report(config={}, history_csv=str(tmp_path / "a.csv"), failed_csv=str(tmp_path / "b.csv"), log_paths=[str(tmp_path / "c.log")])
    assert "(none recorded yet)" in text and "(no activity recorded yet)" in text
    assert "NOT SET" in text                       # an empty profile is reported as missing its essentials


def test_damaged_files_never_break_the_report(tmp_path):
    bad_csv, bad_log = tmp_path / "bad.csv", tmp_path / "bad.log"
    bad_csv.write_bytes(b"\xff\xfe\x00 not,a\x00,real\r\ncsv \x81\x82")
    bad_log.write_bytes(b"\xff\xfe broken \x81 line\nsecond line\n")
    text = build_report(config=CONFIG, history_csv=str(bad_csv), failed_csv=str(bad_csv), log_paths=[str(bad_log)])
    assert "second line" in text


def test_only_the_end_of_a_huge_log_is_included(tmp_path):
    log = tmp_path / "big.log"
    log.write_text("".join(f"line {number:05d} " + "x" * 200 + "\n" for number in range(5000)), encoding="utf-8")
    text = build_report(config={}, history_csv="", failed_csv="", log_paths=[str(log)])
    assert "line 04999" in text and "line 00000" not in text
    assert sum(1 for line in text.splitlines() if line.startswith("line ")) <= 400


def test_the_report_names_missing_details_and_unset_numbers_without_giving_their_values(files):
    complete = _build(files)
    assert "Details the tool needs before it can apply: all set" in complete
    assert "Left 'not set' (a form that asks is left for a person or the AI): none" in complete
    empty = build_report(config={"personals": {}, "questions": {"desired_salary": 0, "notice_period": -1, "years_of_experience": ""}},
                         history_csv="", failed_csv="", log_paths=[])
    assert "first name, last name, email, phone number - NOT SET" in empty
    assert "years of experience, desired salary, current salary, notice period" in empty


def test_host_of_gives_only_the_site_name():
    assert host_of("https://boards.greenhouse.io/acme/jobs/1?gh_jid=1") == "boards.greenhouse.io"
    assert host_of("Easy Applied") == "" and host_of("") == ""


# ---------------------------------------------------------------------------
# The download in the control panel
# ---------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path, monkeypatch):
    log = tmp_path / ".bot_run.log"
    log.write_text(f"Starting for Asha Rao\nData folder is {app_module.DATA_DIR}\n", encoding="utf-8")
    monkeypatch.setattr(app_module, "PATH", str(tmp_path))
    monkeypatch.setattr(app_module, "LOG_PATH", str(log))
    monkeypatch.setattr(app_module, "_effective_config", lambda: CONFIG)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_the_panel_downloads_the_report_as_a_text_file(client):
    response = client.get("/api/report")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert 'filename="MagicApply-report-' in response.headers["Content-Disposition"]
    text = response.get_data(as_text=True)
    assert "Starting for [first_name] [last_name]" in text
    assert "[data folder]" in text and app_module.DATA_DIR not in text          # the person's Windows user name is in that path


def test_the_report_cannot_be_read_from_another_website_or_computer(client):
    assert client.get("/api/report", headers={"Host": "evil.example"}).status_code == 403
