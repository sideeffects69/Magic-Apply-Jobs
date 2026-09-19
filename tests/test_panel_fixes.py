"""
Regression tests for bugs found in a full review of app.py (the control panel's backend). Everything runs in
temp folders - never the real data folder.
"""

import csv
import io
import os
import queue
import socket
import subprocess
import sys
import threading
import time

import pytest

import app as app_module

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HISTORY_COLUMNS = ["Job ID", "Title", "Company", "About Job", "Date Applied", "External Job link"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "PATH", str(tmp_path))
    monkeypatch.setattr(app_module, "_STATUS_PATH", str(tmp_path / "job_statuses.json"))
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _write_history(tmp_path, rows, newline=""):
    path = tmp_path / app_module._HISTORY_CSV
    with open(path, "w", encoding="utf-8", newline=newline) as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(job_id, applied, description="Line one\r\nLine two"):
    return {"Job ID": job_id, "Title": "Analyst", "Company": "Acme", "About Job": description,
            "Date Applied": applied, "External Job link": "https://acme.example/apply"}


# ---------------------------------------------------------------------------
# History: clicking a link must not rewrite the real applied date
# ---------------------------------------------------------------------------
def test_marking_a_job_applied_never_overwrites_a_real_applied_date(client, tmp_path):
    real = "2026-09-01 10:30:00.123456"
    path = _write_history(tmp_path, [_row("1", real), _row("2", "Pending")])
    before = path.read_bytes()

    response = client.put("/applied-jobs/1")

    assert response.status_code == 200 and response.get_json()["unchanged"] is True
    assert path.read_bytes() == before, "the file must be untouched when the job already has a real date"


def test_marking_a_pending_job_applied_stamps_it_and_keeps_every_other_row_intact(client, tmp_path):
    path = _write_history(tmp_path, [_row("1", "2026-09-01 10:30:00"), _row("2", "Pending", "Multi\r\nline\r\ndescription")])

    assert client.put("/applied-jobs/2").status_code == 200

    with open(path, encoding="utf-8", newline="") as handle:
        rows = {row["Job ID"]: row for row in csv.DictReader(handle)}
    assert rows["1"]["Date Applied"] == "2026-09-01 10:30:00"
    assert rows["2"]["Date Applied"] not in ("", "Pending")
    assert rows["2"]["About Job"] == "Multi\r\nline\r\ndescription", "line breaks inside a cell must survive the rewrite"
    assert not (tmp_path / (app_module._HISTORY_CSV + ".tmp")).exists(), "no half-written side file left behind"


def test_marking_an_unknown_job_is_a_404_and_touches_nothing(client, tmp_path):
    path = _write_history(tmp_path, [_row("1", "Pending")])
    before = path.read_bytes()
    assert client.put("/applied-jobs/999").status_code == 404
    assert path.read_bytes() == before


def test_a_short_csv_row_does_not_break_the_history_list(client, tmp_path):
    path = _write_history(tmp_path, [_row("1", "2026-09-01")])
    with open(path, "a", encoding="utf-8", newline="") as handle:
        handle.write("2,Short row\r\n")                    # fewer columns than the header

    jobs = client.get("/applied-jobs").get_json()

    assert [job["Job_ID"] for job in jobs] == ["1", "2"]
    assert all(isinstance(value, str) for job in jobs for value in job.values()), "no null values for the page to choke on"


# ---------------------------------------------------------------------------
# The bot's log: streaming and erasing
# ---------------------------------------------------------------------------
def test_log_streaming_never_garbles_a_character_split_across_two_reads(client, tmp_path, monkeypatch):
    log = tmp_path / "bot.log"
    monkeypatch.setattr(app_module, "LOG_PATH", str(log))
    emoji = "\U0001F600".encode("utf-8")                     # 4 bytes
    log.write_bytes(b"ab" + emoji[:2])                        # the bot is half-way through writing the emoji

    first = client.get("/api/logs?offset=0").get_json()
    assert first["content"] == "ab" and first["next_offset"] == 2      # the half character waits for the next read

    log.write_bytes(b"ab" + emoji + b"cd")
    second = client.get("/api/logs?offset=%d" % first["next_offset"]).get_json()
    assert second["content"] == "\U0001F600cd" and "�" not in second["content"]


def test_the_bots_run_log_can_be_deleted_once_the_run_is_over(client, tmp_path, monkeypatch):
    log = tmp_path / ".bot_run.log"
    monkeypatch.setattr(app_module, "LOG_PATH", str(log))
    monkeypatch.setattr(app_module, "PID_PATH", str(tmp_path / ".bot_run.pid"))
    monkeypatch.setattr(app_module, "_bot_command", lambda: [sys.executable, "-c", "print('hello from the bot')"])
    monkeypatch.setattr(app_module, "_bot_proc", None)

    assert client.post("/api/run").status_code == 200
    app_module._bot_proc.wait(timeout=30)

    assert "hello from the bot" in log.read_text(encoding="utf-8")
    # The end-of-session erase has to be able to delete this file (on Windows an open handle would block it).
    os.remove(log)
    assert not log.exists()


# ---------------------------------------------------------------------------
# Launching: port 5000 is often taken by an unrelated program
# ---------------------------------------------------------------------------
def _read_lines(stream, sink):
    for line in stream:
        sink.put(line)


def test_when_the_port_is_taken_by_another_program_the_panel_uses_the_next_one(tmp_path):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy_port = blocker.getsockname()[1]
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path), HOME=str(tmp_path),
               PORT=str(busy_port), PYTHONUNBUFFERED="1")
    env.pop("PANEL_OPEN_BROWSER", None)
    process = subprocess.Popen([sys.executable, "app.py"], cwd=PROJECT_ROOT, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = queue.Queue()
    threading.Thread(target=_read_lines, args=(process.stdout, lines), daemon=True).start()
    output = []
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not any("Control panel ready" in line for line in output):
            try:
                output.append(lines.get(timeout=1))
            except queue.Empty:
                if process.poll() is not None:
                    break
        text = "".join(output)
        assert "already running" not in text, "it must not claim the other program is the control panel:\n" + text
        assert f"http://127.0.0.1:{busy_port + 1}" in text, text
        assert f"Port {busy_port} is used by another program" in text, text
    finally:
        process.kill()
        process.wait(timeout=10)
        blocker.close()
