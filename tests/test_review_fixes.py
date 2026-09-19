"""
Regression tests for the remaining bugs found in a line-by-line review of the whole tool. Each test names the
behaviour that used to be wrong.
"""

import os
import subprocess
import sys
import types

import pytest

from modules import helpers, resume_builder
from modules.ai import connections
from modules.clickers_and_finders import multi_sel_noWait, xpath_literal
from modules.validator import check_boolean

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# AI answer graph
# ---------------------------------------------------------------------------
class _FakeModel:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, prompt):
        return types.SimpleNamespace(content=self.reply)


def _answer(reply, options, question_type):
    graph = connections._build_answer_graph(_FakeModel(reply))
    return graph.invoke({"question": "Q?", "options": options, "question_type": question_type})["answer"]


@pytest.mark.parametrize("question_type", ["select", "radio", "single_select"])
def test_option_questions_are_snapped_to_a_real_option(question_type):
    # The company-site applier asks with question_type "select"/"radio"; those used to skip the snapping step.
    assert _answer("yes", ["Select", "Yes", "No"], question_type) == "Yes"


def test_an_empty_ai_reply_does_not_match_the_first_option():
    assert _answer("", ["Yes", "No"], "select") == ""


def test_no_is_not_snapped_to_not_sure():
    # "No" is inside "Not sure" as letters but not as a word.
    assert _answer("No", ["Not sure", "Yes"], "select") == "No"
    assert _answer("No", ["Not sure", "No"], "select") == "No"


def test_free_text_answers_are_left_alone():
    assert _answer("I have five years of experience.", None, "text") == "I have five years of experience."


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def test_the_portable_exe_explains_it_has_no_resume_builder_instead_of_relaunching_itself(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    ok, message = resume_builder.generate_ats_resume()
    assert ok is False and "portable exe" in message


def test_a_missing_log_folder_is_recreated_instead_of_losing_the_message(tmp_path, monkeypatch):
    log = tmp_path / "fresh session" / "logs" / "log.txt"           # the data folder is erased every session
    monkeypatch.setattr(helpers, "__logs_file_path", str(log))
    helpers.print_lg("first message of a fresh session")
    assert "first message of a fresh session" in log.read_text(encoding="utf-8")


def test_boolean_settings_must_really_be_booleans():
    assert check_boolean(True, "x") is True and check_boolean(False, "x") is True
    for wrong in ("True", "yes", 1, 0, None):
        with pytest.raises(ValueError):
            check_boolean(wrong, "x")


def test_the_start_scripts_reinstall_packages_when_the_requirements_change(tmp_path):
    # The exact check start.bat runs: exit 1 (reinstall) only when requirements.txt is newer than the marker.
    check = "import os, sys; sys.exit(1 if os.path.getmtime('requirements.txt') > os.path.getmtime('marker') else 0)"
    (tmp_path / "requirements.txt").write_text("flask")
    (tmp_path / "marker").write_text("done")
    os.utime(tmp_path / "marker", (2_000_000_000, 2_000_000_000))
    os.utime(tmp_path / "requirements.txt", (1_000_000_000, 1_000_000_000))
    assert subprocess.run([sys.executable, "-c", check], cwd=tmp_path).returncode == 0
    os.utime(tmp_path / "requirements.txt", (3_000_000_000, 3_000_000_000))
    assert subprocess.run([sys.executable, "-c", check], cwd=tmp_path).returncode == 1
    for script in ("start.sh", "start.command"):
        assert "-nt" in open(os.path.join(PROJECT_ROOT, script), encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Selenium helpers (real headless Chrome, a local page)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    for arg in ("--headless=new", "--window-size=1200,900", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"):
        options.add_argument(arg)
    try:
        browser = webdriver.Chrome(options=options)
    except Exception as error:
        pytest.skip(f"Chrome could not be started for the browser tests: {type(error).__name__}")
    yield browser
    browser.quit()


def _page(driver, html):
    from urllib.parse import quote
    driver.get("data:text/html;charset=utf-8," + quote(html))


@pytest.mark.parametrize("text", [
    "Plain", "It's fine", 'She said "hi"', """Both "double" and 'single' quotes""", "Domino's Pizza",
])
def test_xpath_literal_finds_text_whatever_quotes_it_contains(driver, text):
    from html import escape
    from selenium.webdriver.common.by import By
    _page(driver, f"<span id='target'>{escape(text)}</span><span>other</span>")
    found = driver.find_element(By.XPATH, ".//span[normalize-space(.)=" + xpath_literal(text) + "]")
    assert found.get_attribute("id") == "target"


def test_one_company_that_cannot_be_added_does_not_abort_the_filters_after_it(driver):
    from selenium.webdriver.common.action_chains import ActionChains
    _page(driver, "<span id='b' onclick=\"window.clickedB = true\">Full-time</span>")
    multi_sel_noWait(driver, ["Some Company Ltd", "Full-time"], ActionChains(driver))
    assert driver.execute_script("return window.clickedB === true"), "the filter after the failing company was skipped"


# ---------------------------------------------------------------------------
# The bot's own CSV readers and profile (runAiBot imported with the real Chrome launch stubbed out)
# ---------------------------------------------------------------------------
@pytest.fixture
def bot(driver, tmp_path, monkeypatch):
    from selenium.webdriver.support.ui import WebDriverWait
    fake_chrome = types.ModuleType("modules.open_chrome")
    fake_chrome.options, fake_chrome.driver = None, driver
    fake_chrome.actions, fake_chrome.wait = None, WebDriverWait(driver, 5)
    monkeypatch.setitem(sys.modules, "modules.open_chrome", fake_chrome)
    monkeypatch.delitem(sys.modules, "runAiBot", raising=False)
    import runAiBot
    monkeypatch.setattr(runAiBot, "print_lg", lambda *a, **k: None)
    return runAiBot


def test_a_blank_line_in_the_history_csv_does_not_crash_the_start_of_a_run(bot, tmp_path, monkeypatch):
    history = tmp_path / "history.csv"
    history.write_bytes(b"Job ID,Title\r\n111,Analyst\r\n\r\n222,Engineer\r\n\r\n")   # blank lines, as Excel leaves them
    monkeypatch.setattr(bot, "file_name", str(history))
    assert bot.get_applied_job_ids() == {"Job ID", "111", "222"}


def test_a_short_row_does_not_crash_the_daily_application_count(bot, tmp_path, monkeypatch):
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    history = tmp_path / "history.csv"
    history.write_bytes(f"Job ID,Title,Date Applied\r\n1,A,{today} 09:00:00\r\n2,B\r\n3,C,2001-01-01 00:00:00\r\n".encode())
    monkeypatch.setattr(bot, "file_name", str(history))
    assert bot.count_applications_today() == 1


def test_the_bot_passes_salary_and_notice_to_the_company_site_applier_as_numbers(bot, monkeypatch):
    # The bot's config module turns these into text at import time ("1200000"); the applier does arithmetic on them.
    monkeypatch.setattr(bot, "first_name", "Asha")
    monkeypatch.setattr(bot, "last_name", "Rao")
    monkeypatch.setattr(bot, "desired_salary", "900000")
    monkeypatch.setattr(bot, "current_ctc", "600000")
    monkeypatch.setattr(bot, "notice_period", "30")
    monkeypatch.setattr(bot, "email", "asha@example.org")
    monkeypatch.setattr(bot, "phone_number", "+91 98765 43210")
    assert isinstance(bot.desired_salary, str), "precondition: the bot really does hold these as text"

    profile = bot.build_external_profile()

    assert isinstance(profile.desired_salary, int) and isinstance(profile.notice_period, int) and isinstance(profile.current_ctc, int)
    from modules.form_profile import FieldInfo, decide
    assert decide(FieldInfo("text", "Expected salary"), profile).action == "fill"      # used to raise TypeError


def test_advisable_is_not_a_visa_question(bot):
    assert bot.answer_common_questions("it is advisable to bring a portfolio", "Yes") == "Yes"
    assert bot.answer_common_questions("will you require visa sponsorship?", "Yes") == bot.require_visa
