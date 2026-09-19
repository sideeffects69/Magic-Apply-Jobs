"""
What a brand-new person gets: the shipped defaults, with nothing saved yet. These must be usable, and the
control panel must not quietly turn a blank setting into a claim nobody made.
"""

import json
import os
import subprocess
import sys

import pytest

import config_schema

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_in_fresh_profile(tmp_path, code: str):
    """Runs `code` in a new interpreter whose data folder is empty, so every setting is the shipped default."""
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path), HOME=str(tmp_path))
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                          cwd=PROJECT_ROOT, env=env)


def test_default_settings_pass_the_bots_own_validation(tmp_path):
    result = _run_in_fresh_profile(tmp_path, "from modules.validator import validate_config; validate_config(); print('VALID')")
    assert "VALID" in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("override, note", [
    ({"secrets": {"username": "", "password": ""}}, "the panel calls the LinkedIn login optional"),
    ({"personals": {"ethnicity": ""}}, "the panel offers '(leave unanswered)'"),
    ({"questions": {"us_citizenship": ""}}, "unset citizenship"),
])
def test_blank_values_the_panel_allows_do_not_stop_the_bot_from_starting(tmp_path, override, note):
    folder = tmp_path / "AutoJobApplier"
    folder.mkdir()
    (folder / "user_config.json").write_text(json.dumps(override), encoding="utf-8")
    result = _run_in_fresh_profile(tmp_path, "from modules.validator import validate_config; validate_config(); print('VALID')")
    assert "VALID" in result.stdout, f"{note}: " + result.stdout + result.stderr


def test_every_dropdown_default_is_one_of_its_options(tmp_path):
    """
    A dropdown whose default isn't in its list shows the FIRST option in the browser while the real value is
    something else - so a plain Save would silently record an answer (e.g. a citizenship) the person never chose.
    """
    result = _run_in_fresh_profile(tmp_path, "import json, app; print(json.dumps(app.DEFAULTS))")
    defaults = json.loads(result.stdout.strip().splitlines()[-1])
    problems = []
    for field in config_schema.iter_fields():
        if field["type"] == "select":
            value = defaults[field["config_module"]][field["key"]]
            if value not in field["options"]:
                problems.append(f'{field["config_module"]}.{field["key"]} defaults to {value!r}, not in {field["options"]}')
    assert not problems, "\n".join(problems)


def test_a_new_user_gets_a_daily_cap_and_no_borrowed_search_location(tmp_path):
    result = _run_in_fresh_profile(
        tmp_path, "import config.settings as s, config.search as q; print(s.max_applications_per_day, repr(q.search_location), q.easy_apply_only)")
    assert result.stdout.split() == ["40", "''", "False"], result.stdout + result.stderr
