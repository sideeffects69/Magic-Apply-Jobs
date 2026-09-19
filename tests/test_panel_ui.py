"""
The control panel's pages, driven in a real headless Chrome against the real Flask app - with every path pointed
at a temp folder and the bot launcher stubbed, so a test can never touch your data or start a real run.
"""

import csv
import json
import sys
import threading
import time

import pytest
from werkzeug.serving import make_server

import app as app_module

HISTORY_COLUMNS = ["Job ID", "Title", "Company", "HR Name", "HR Link", "HR Email", "HR Phone", "Date Applied",
                   "Job Link", "External Job link"]
FAILED_COLUMNS = ["Job ID", "Job Link", "Assumed Reason", "Date listed", "Date Tried", "External Job link", "Screenshot Name"]


@pytest.fixture(scope="module")
def panel(tmp_path_factory):
    folder = tmp_path_factory.mktemp("AutoJobApplier")
    config_file = str(folder / "user_config.json")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(app_module, "PATH", str(folder))
        patch.setattr(app_module, "DATA_DIR", str(folder))
        patch.setattr(app_module, "LOG_PATH", str(folder / ".bot_run.log"))
        patch.setattr(app_module, "PID_PATH", str(folder / ".bot_run.pid"))
        patch.setattr(app_module, "_STATUS_PATH", str(folder / "job_statuses.json"))
        patch.setattr(app_module, "USER_CONFIG_PATH", config_file)
        patch.setattr(app_module._overrides, "USER_CONFIG_PATH", config_file)
        started = []
        patch.setattr(app_module, "_bot_command", lambda: started.append(1) or [sys.executable, "-c", "print('stub bot')"])
        server = make_server("127.0.0.1", 0, app_module.app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield {"url": f"http://127.0.0.1:{server.server_port}", "folder": folder, "config": config_file, "bot_starts": started}
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    for arg in ("--headless=new", "--window-size=1300,1200", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"):
        options.add_argument(arg)
    try:
        browser = webdriver.Chrome(options=options)
    except Exception as error:
        pytest.skip(f"Chrome could not be started for the browser tests: {type(error).__name__}")
    yield browser
    browser.quit()


@pytest.fixture(autouse=True)
def clean_folder(panel):
    # A previous test may have "started" the stub bot; let it finish so it lets go of its log file.
    stub = app_module._bot_proc
    if stub is not None:
        try:
            stub.wait(timeout=20)
        except Exception:
            stub.kill()
        app_module._bot_proc = None
    for item in panel["folder"].iterdir():
        if item.is_file():
            for _ in range(20):
                try:
                    item.unlink()
                    break
                except PermissionError:
                    time.sleep(0.25)
    panel["bot_starts"].clear()
    yield


def _write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _wait_for(driver, script, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = driver.execute_script(script)
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError("timed out waiting for: " + script)


# ---------------------------------------------------------------------------
# History and failures pages
# ---------------------------------------------------------------------------
def test_history_page_shows_a_friendly_empty_state_on_a_fresh_session(driver, panel):
    driver.get(panel["url"] + "/history")
    text = _wait_for(driver, "return document.getElementById('historyBody').innerText")
    assert "No applied jobs yet" in text
    assert "Could not load" not in text


def test_javascript_links_in_scraped_data_are_never_made_clickable(driver, panel):
    evil = "javascript:document.title='hacked'"
    _write_csv(panel["folder"] / app_module._HISTORY_CSV, HISTORY_COLUMNS, [
        {"Job ID": "1", "Title": "Analyst", "Company": "Acme", "HR Name": "Pat", "HR Link": evil, "HR Email": "pat@acme.example",
         "HR Phone": "", "Date Applied": "Pending", "Job Link": evil, "External Job link": evil},
        {"Job ID": "2", "Title": "Engineer", "Company": "Beta", "HR Name": "", "HR Link": "", "HR Email": "",
         "HR Phone": "", "Date Applied": "Pending", "Job Link": "https://www.linkedin.com/jobs/view/2", "External Job link": "https://beta.example/apply"},
    ])

    driver.get(panel["url"] + "/history")
    _wait_for(driver, "return document.querySelectorAll('#historyBody tr').length >= 2")

    hrefs = driver.execute_script("return Array.from(document.querySelectorAll('#historyBody a')).map(a => a.getAttribute('href'))")
    assert not any(h.lower().startswith("javascript:") for h in hrefs), hrefs
    assert "https://www.linkedin.com/jobs/view/2" in hrefs and "https://beta.example/apply" in hrefs, "safe links still work"
    assert "mailto:pat@acme.example" in hrefs
    assert "Analyst" in driver.find_element("id", "historyBody").text, "the row is still shown, just not linked"


def test_the_run_tab_history_also_refuses_javascript_links(driver, panel):
    evil = "javascript:document.title='hacked'"
    _write_csv(panel["folder"] / app_module._HISTORY_CSV, HISTORY_COLUMNS, [
        {"Job ID": "1", "Title": "Analyst", "Company": "Acme", "HR Name": "Pat", "HR Link": evil, "HR Email": "",
         "HR Phone": "", "Date Applied": "Pending", "Job Link": evil, "External Job link": evil}])

    driver.get(panel["url"] + "/")
    _wait_for(driver, "return document.querySelectorAll('#tabs button').length > 3")
    driver.execute_script("Array.from(document.querySelectorAll('#tabs button')).find(b => b.dataset.tab === 'Run').click()")
    _wait_for(driver, "return document.querySelectorAll('#jobsHolder table').length > 0")

    hrefs = driver.execute_script("return Array.from(document.querySelectorAll('#jobsHolder a')).map(a => a.getAttribute('href'))")
    assert not any((h or "").lower().startswith("javascript:") for h in hrefs), hrefs


def test_failed_company_site_jobs_show_a_link_to_finish_them_by_hand(driver, panel):
    _write_csv(panel["folder"] / app_module._FAILED_CSV, FAILED_COLUMNS, [
        {"Job ID": "7", "Job Link": "https://www.linkedin.com/jobs/view/7", "Assumed Reason": "Company site: Required questions the tool can't answer: Kubernetes",
         "Date listed": "", "Date Tried": "2026-09-19 10:00:00", "External Job link": "https://acme.example/careers/apply/7", "Screenshot Name": "Not Available"},
        {"Job ID": "8", "Job Link": "https://www.linkedin.com/jobs/view/8", "Assumed Reason": "Asking for Security clearance",
         "Date listed": "", "Date Tried": "2026-09-19 10:01:00", "External Job link": "Skipped", "Screenshot Name": "Not Available"},
    ])

    driver.get(panel["url"] + "/failures")
    _wait_for(driver, "return document.querySelectorAll('tbody tr').length >= 2")

    hrefs = driver.execute_script("return Array.from(document.querySelectorAll('tbody a')).map(a => a.getAttribute('href'))")
    assert "https://acme.example/careers/apply/7" in hrefs
    summary = driver.find_element("id", "summaryHint").text
    assert "1 need attention" in summary and "1 filtered by your rules" in summary, summary   # the clearance skip is not an "error"


# ---------------------------------------------------------------------------
# Settings form
# ---------------------------------------------------------------------------
def test_the_citizenship_dropdown_does_not_display_an_answer_nobody_gave(driver, panel):
    driver.get(panel["url"] + "/")
    _wait_for(driver, "return document.getElementById('f__questions__us_citizenship')")

    assert driver.execute_script("return document.getElementById('f__questions__us_citizenship').value") == ""
    driver.execute_script("document.getElementById('saveBtn').click()")
    time.sleep(0.5)
    assert "Nothing to save" in driver.find_element("id", "saveMsg").text, "a plain Save must not record a citizenship"


def _open_run_tab(driver, panel):
    driver.get(panel["url"] + "/")
    _wait_for(driver, "return document.querySelectorAll('#tabs button').length > 3")
    driver.execute_script("Array.from(document.querySelectorAll('#tabs button')).find(b => b.dataset.tab === 'Run').click()")
    _wait_for(driver, "return document.getElementById('startBtn')")


def _saved_first_name(panel):
    try:
        return json.loads(open(panel["config"], encoding="utf-8").read()).get("personals", {}).get("first_name")
    except (OSError, ValueError):
        return None


def test_start_offers_to_save_unsaved_settings_instead_of_silently_ignoring_them(driver, panel):
    driver.get(panel["url"] + "/")
    _wait_for(driver, "return document.getElementById('f__personals__first_name')")
    driver.execute_script("Array.from(document.querySelectorAll('#tabs button')).find(b => b.dataset.tab === 'Profile').click()")
    driver.find_element("id", "f__personals__first_name").clear()
    driver.find_element("id", "f__personals__first_name").send_keys("Zed")
    driver.execute_script("Array.from(document.querySelectorAll('#tabs button')).find(b => b.dataset.tab === 'Run').click()")
    _wait_for(driver, "return document.getElementById('startBtn')")

    driver.find_element("id", "startBtn").click()
    alert = driver.switch_to.alert
    assert "not saved yet" in alert.text and "Searching for:" in alert.text
    alert.dismiss()                                  # cancel: nothing saved, nothing started
    time.sleep(0.5)
    assert _saved_first_name(panel) is None and panel["bot_starts"] == []

    driver.find_element("id", "startBtn").click()
    driver.switch_to.alert.accept()                  # OK: saves first, then starts
    _wait_for(driver, "return true")
    end = time.monotonic() + 10
    while time.monotonic() < end and not (_saved_first_name(panel) == "Zed" and panel["bot_starts"]):
        time.sleep(0.25)
    assert _saved_first_name(panel) == "Zed"
    assert panel["bot_starts"] == [1], "the (stubbed) bot was started exactly once, after the save"


def test_start_with_everything_saved_just_confirms_and_shows_what_will_run(driver, panel):
    _open_run_tab(driver, panel)

    driver.find_element("id", "startBtn").click()
    alert = driver.switch_to.alert
    assert "not saved yet" not in alert.text
    assert "Searching for: Software Engineer" in alert.text and "company websites" in alert.text
    alert.dismiss()
    assert panel["bot_starts"] == []


# ---------------------------------------------------------------------------
# Download report (the tool erases its own log when it closes - this is how evidence of a bad run survives)
# ---------------------------------------------------------------------------
def test_the_report_button_saves_a_report_and_says_to_read_it_before_sharing(driver, panel):
    driver.get(panel["url"])
    _wait_for(driver, "return !!document.getElementById('reportBtn')")
    driver.execute_script("document.getElementById('reportBtn').click();")
    message = _wait_for(driver, "return document.getElementById('dataMsg').innerText")
    assert "Report downloaded" in message and "read the file" in message


def test_finish_and_erase_offers_a_report_first(driver, panel):
    driver.get(panel["url"])
    _wait_for(driver, "return !!document.getElementById('finishBtn')")
    driver.execute_script("document.getElementById('finishBtn').click();")
    assert _wait_for(driver, "return document.getElementById('finishDialog').open")
    assert "Something went wrong? Download a report first" in driver.find_element("id", "finishDialog").text
    driver.execute_script("document.getElementById('finishReportBtn').click();")
    assert _wait_for(driver, "return document.getElementById('finishReportBtn').textContent === 'Report downloaded'")
    driver.execute_script("document.getElementById('finishCancelBtn').click();")        # never actually erase anything here
