"""
The portable MagicApply.exe re-launches itself to run the bot, and checks its own contents
with --selftest. These guard the parts of that which can be tested without building the exe.
"""

import os
import subprocess
import sys

import app as app_module

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_bot_is_started_as_the_exe_itself_when_frozen(monkeypatch):
    monkeypatch.setattr(app_module, "FROZEN", True)
    assert app_module._bot_command() == [sys.executable, "--run-bot"]


def test_bot_is_started_from_its_script_when_running_from_source(monkeypatch):
    monkeypatch.setattr(app_module, "FROZEN", False)
    command = app_module._bot_command()
    assert command[0] == sys.executable
    assert os.path.basename(command[1]) == "runAiBot.py" and os.path.isfile(command[1])


def test_selftest_confirms_everything_the_exe_needs_is_importable():
    result = subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "magic_apply.py"), "--selftest"],
                            capture_output=True, text=True, timeout=120, cwd=PROJECT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout
    assert result.stdout.count("OK") >= 6
