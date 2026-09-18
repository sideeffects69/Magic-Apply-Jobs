"""
The tool keeps nothing between sessions: data is erased when the panel closes,
and the only way to keep it is a backup file the person downloads and later
restores. Every test here works on a temp folder - never the real data folder.
"""

import base64
import json
import os

import pytest

import app as app_module
from modules import session_data


@pytest.fixture
def data_dir(tmp_path):
    folder = tmp_path / session_data.APP_DIR_NAME
    folder.mkdir()
    return folder


@pytest.fixture
def client(data_dir, monkeypatch):
    config_file = str(data_dir / "user_config.json")
    monkeypatch.setattr(app_module, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(app_module, "USER_CONFIG_PATH", config_file)
    monkeypatch.setattr(app_module._overrides, "USER_CONFIG_PATH", config_file)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _fill(data_dir):
    (data_dir / "user_config.json").write_text(json.dumps({
        "secrets": {"username": "me@example.com", "password": "hunter2", "llm_api_key": "sk-secret"},
        "personals": {"first_name": "Test"},
        "questions": {"user_information_all": "I am a test person."},
    }), encoding="utf-8")
    (data_dir / "resume_data.yaml").write_text("cv:\n  name: Test\n", encoding="utf-8")
    (data_dir / "all excels").mkdir()
    (data_dir / "all excels" / "all_applied_applications_history.csv").write_bytes(b"Job ID,Title\r\n1,\"Line one\nLine two\"\r\n")
    (data_dir / "all resumes" / "default").mkdir(parents=True)
    (data_dir / "all resumes" / "default" / "resume.pdf").write_bytes(b"%PDF-1.4 \x00\x01\x02 binary")


# ---------------------------------------------------------------------------
# Erase
# ---------------------------------------------------------------------------
def test_wipe_empties_the_folder_but_keeps_the_folder(data_dir):
    _fill(data_dir)
    (data_dir / "chrome-profile" / "Default").mkdir(parents=True)
    (data_dir / "chrome-profile" / "Default" / "Cookies").write_text("session")

    assert session_data.wipe_data(str(data_dir)) is True

    assert data_dir.is_dir()
    assert list(data_dir.iterdir()) == []


def test_wipe_refuses_a_folder_that_is_not_ours(tmp_path):
    other = tmp_path / "Documents"
    other.mkdir()
    (other / "precious.txt").write_text("keep me")

    with pytest.raises(ValueError):
        session_data.wipe_data(str(other))

    assert (other / "precious.txt").exists()


def test_wipe_if_enabled_respects_the_keep_data_switch(data_dir, monkeypatch):
    _fill(data_dir)
    monkeypatch.setenv(session_data.KEEP_DATA_ENV, "1")
    assert session_data.wipe_if_enabled(str(data_dir)) is False
    assert (data_dir / "user_config.json").exists()

    monkeypatch.setenv(session_data.KEEP_DATA_ENV, "")
    assert session_data.wipe_if_enabled(str(data_dir)) is True
    assert not (data_dir / "user_config.json").exists()


def test_has_data(data_dir):
    assert session_data.has_data(str(data_dir)) is False
    _fill(data_dir)
    assert session_data.has_data(str(data_dir)) is True


# ---------------------------------------------------------------------------
# Backup and restore
# ---------------------------------------------------------------------------
def test_backup_then_restore_brings_everything_back_byte_for_byte(data_dir, tmp_path):
    _fill(data_dir)
    backup = json.loads(json.dumps(session_data.build_backup(str(data_dir))))  # via a real JSON file

    fresh = tmp_path / "fresh" / session_data.APP_DIR_NAME
    fresh.mkdir(parents=True)
    restored = session_data.restore_backup(backup, str(fresh))

    assert set(restored) == {"settings", "resume text", "applied-jobs history", "1 resume file"}
    assert json.loads((fresh / "user_config.json").read_text(encoding="utf-8")) == json.loads(
        (data_dir / "user_config.json").read_text(encoding="utf-8"))
    assert (fresh / "resume_data.yaml").read_text(encoding="utf-8") == "cv:\n  name: Test\n"
    history = "all excels/all_applied_applications_history.csv"
    assert (fresh / history).read_bytes() == (data_dir / history).read_bytes()
    pdf = "all resumes/default/resume.pdf"
    assert (fresh / pdf).read_bytes() == (data_dir / pdf).read_bytes()


def test_backup_can_leave_out_passwords_and_api_keys(data_dir):
    _fill(data_dir)
    backup = session_data.build_backup(str(data_dir), include_secrets=False)

    assert "password" not in backup["config"]["secrets"]
    assert "llm_api_key" not in backup["config"]["secrets"]
    assert backup["config"]["secrets"]["username"] == "me@example.com"
    assert backup["includes_secrets"] is False
    assert "hunter2" not in json.dumps(backup)


@pytest.mark.parametrize("mutate, expected", [
    (lambda b: b.update(format="something-else"), "isn't a Magic Apply - Jobs backup"),
    (lambda b: b.update(version=999), "newer version"),
    (lambda b: b.update(resume_files={"../evil.pdf": "AAAA"}), "unsafe name"),
    (lambda b: b.update(resume_files={"sub/evil.pdf": "AAAA"}), "unsafe name"),
    (lambda b: b.update(resume_files={"..\\evil.pdf": "AAAA"}), "unsafe name"),
    (lambda b: b.update(resume_files={"C:evil.pdf": "AAAA"}), "unsafe name"),
    (lambda b: b.update(resume_files={"ok.pdf": "not base64 !!"}), "damaged"),
])
def test_restore_rejects_bad_backups_and_writes_nothing(data_dir, tmp_path, mutate, expected):
    _fill(data_dir)
    backup = session_data.build_backup(str(data_dir))
    mutate(backup)
    target = tmp_path / "target" / session_data.APP_DIR_NAME
    target.mkdir(parents=True)

    with pytest.raises(session_data.BackupError, match=expected):
        session_data.restore_backup(backup, str(target))

    assert list(target.iterdir()) == []


def test_restore_rejects_something_that_is_not_a_backup(tmp_path):
    for junk in (None, [], "text", {"hello": "world"}):
        with pytest.raises(session_data.BackupError):
            session_data.restore_backup(junk, str(tmp_path))


# ---------------------------------------------------------------------------
# The panel's API
# ---------------------------------------------------------------------------
def test_backup_endpoint_downloads_a_json_file(client, data_dir):
    _fill(data_dir)
    response = client.get("/api/backup")

    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["config"]["secrets"]["password"] == "hunter2"

    without = client.get("/api/backup?secrets=0").get_json()
    assert "password" not in without["config"]["secrets"]


def test_restore_endpoint_refills_the_config_the_form_reads(client, data_dir, tmp_path):
    _fill(data_dir)
    backup = client.get("/api/backup").get_json()
    session_data.wipe_data(str(data_dir))
    assert client.get("/api/data-status").get_json()["has_data"] is False

    response = client.post("/api/restore", json=backup)

    assert response.status_code == 200
    assert "settings" in response.get_json()["restored"]
    assert client.get("/api/data-status").get_json()["has_data"] is True
    assert client.get("/api/config").get_json()["personals"]["first_name"] == "Test"


def test_restore_keeps_hidden_settings_but_drops_anything_that_points_at_other_files(client, data_dir):
    backup = {
        "format": session_data.BACKUP_FORMAT, "version": 1,
        "config": {
            "questions": {
                "user_information_all": "about me text the form does not show",
                "default_resume_path": "C:/Users/someone/.ssh/id_rsa",
            },
            "settings": {"file_name": "C:/anywhere/steal.csv", "max_applications_per_day": 30},
            "not_a_section": {"x": 1},
        },
    }

    assert client.post("/api/restore", json=backup).status_code == 200
    saved = json.loads((data_dir / "user_config.json").read_text(encoding="utf-8"))

    assert saved["questions"]["user_information_all"] == "about me text the form does not show"
    assert "default_resume_path" not in saved["questions"]          # absolute path dropped
    assert "file_name" not in saved["settings"]                      # can't redirect where files are written
    assert saved["settings"]["max_applications_per_day"] == 30
    assert "not_a_section" not in saved


@pytest.mark.parametrize("path, kept", [
    ("all resumes/default/me.pdf", True),
    ("..\\..\\outside.pdf", False),
    ("../../outside.pdf", False),
    ("C:\\Windows\\win.ini", False),
])
def test_restore_only_keeps_resume_paths_inside_the_private_folder(client, data_dir, path, kept):
    backup = {"format": session_data.BACKUP_FORMAT, "version": 1,
              "config": {"questions": {"default_resume_path": path}}}
    client.post("/api/restore", json=backup)
    saved = json.loads((data_dir / "user_config.json").read_text(encoding="utf-8"))
    assert ("default_resume_path" in saved.get("questions", {})) is kept


def test_restore_endpoint_rejects_garbage_with_a_readable_error(client):
    response = client.post("/api/restore", json={"hello": "world"})
    assert response.status_code == 400
    assert "backup" in response.get_json()["error"].lower()

    response = client.post("/api/restore", data="not json", content_type="application/json")
    assert response.status_code == 400


def test_quit_endpoint_replies_then_schedules_the_erase(client, monkeypatch):
    scheduled = []

    class FakeTimer:
        def __init__(self, interval, function):
            self.function = function

        def start(self):
            scheduled.append(self.function)

    marker = lambda: None
    monkeypatch.setattr(app_module, "_finish_and_exit", marker)
    monkeypatch.setattr(app_module.threading, "Timer", FakeTimer)

    response = client.post("/api/quit")

    assert response.status_code == 200
    assert scheduled == [marker]


def test_shutdown_cleanup_erases_only_after_the_panel_was_used(data_dir, monkeypatch):
    _fill(data_dir)
    monkeypatch.setattr(app_module, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(app_module, "_bot_proc", None)

    monkeypatch.setattr(app_module, "_cleanup_done", False)
    monkeypatch.setattr(app_module, "_session_started", False)
    app_module._shutdown_cleanup()
    assert (data_dir / "user_config.json").exists(), "a launch nobody used must not erase anything"

    monkeypatch.setattr(app_module, "_cleanup_done", False)
    monkeypatch.setattr(app_module, "_session_started", True)
    app_module._shutdown_cleanup()
    assert list(data_dir.iterdir()) == []

    # Running it again is harmless.
    app_module._shutdown_cleanup()


# ---------------------------------------------------------------------------
# Other websites must not be able to reach the panel
# ---------------------------------------------------------------------------
def test_requests_from_other_sites_are_refused(client):
    assert client.post("/api/quit", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/restore", json={}, headers={"Origin": "http://evil.example:5000"}).status_code == 403
    assert client.get("/api/backup", headers={"Host": "evil.example"}).status_code == 403


def test_requests_from_the_panel_itself_are_allowed(client):
    same_origin = {"Origin": "http://127.0.0.1:5000"}
    assert client.post("/api/restore", json={"x": 1}, headers=same_origin).status_code == 400  # reached the handler
    assert client.get("/api/data-status", headers={"Host": "127.0.0.1:5000"}).status_code == 200
    assert client.get("/api/data-status", headers={"Host": "localhost:5000"}).status_code == 200
