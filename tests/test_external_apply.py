"""
Runs the external-site applier in a real (headless) Chrome against the local mock career
portal in tests/mock_job_site.py. Skipped automatically if Chrome can't be started.
"""

import os

import pytest

from modules import external_apply
from modules.external_apply import APPLIED, NEEDS_MANUAL, ExternalApplier, ExternalSettings
from modules.form_profile import Profile
from tests.mock_job_site import MockSite


@pytest.fixture(scope="module")
def site():
    mock = MockSite().start()
    yield mock
    mock.stop()


@pytest.fixture(scope="module")
def driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    for arg in ("--headless=new", "--window-size=1280,1100", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"):
        options.add_argument(arg)
    try:
        browser = webdriver.Chrome(options=options)
    except Exception as error:
        pytest.skip(f"Chrome could not be started for the browser tests: {type(error).__name__}")
    yield browser
    browser.quit()


@pytest.fixture(autouse=True)
def fresh_browser(driver, site, monkeypatch):
    # The "Google" screens live on `localhost`; the company site is on `127.0.0.1`.
    monkeypatch.setattr(external_apply, "GOOGLE_AUTH_HOSTS", ("localhost",))
    site.reset()
    handles = driver.window_handles
    for extra in handles[1:]:
        driver.switch_to.window(extra)
        driver.close()
    driver.switch_to.window(driver.window_handles[0])
    driver.get(site.base + "/blank.html")
    driver.execute_script("sessionStorage.clear()")
    yield


@pytest.fixture
def resume(tmp_path):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-1.4 fake resume")
    return str(path)


@pytest.fixture
def me():
    return Profile.from_values(
        first_name="Asha", last_name="Rao", email="tester@example.com", phone="+91 98765 43210", city="Springfield",
        state="Illinois", country="India", years_of_experience="3", desired_salary=900000, notice_period=30,
        require_visa="No", cover_letter="Dear team, I would love to join.", gender="",
    )


def quick(**overrides):
    values = dict(max_steps=14, timeout_seconds=150, manual_wait_seconds=0, google_email="tester@example.com")
    values.update(overrides)
    return ExternalSettings(**values)


def run(driver, me, resume, settings=None, **kw):
    return ExternalApplier(driver, me, resume, settings or quick(), log=lambda *_: None, **kw).run()


# ---------------------------------------------------------------------------
def test_full_flow_from_job_page_through_google_popup_to_a_submitted_application(driver, site, me, resume):
    driver.get(site.base + "/job.html")

    result = run(driver, me, resume)

    assert result.status == APPLIED, result
    assert site.google_picks == ["tester@example.com"], "should pick the configured Google account, not the first one"
    assert len(site.submissions) == 1
    sent = site.submissions[0]

    # Filled from the profile where the field was empty ...
    assert sent["last_name"] == "Rao"
    assert sent["city"] == "Springfield"
    assert sent["auth"] == "Yes"
    assert sent["sponsor"] == "no"
    assert sent["gender"] == "Decline to self-identify"
    assert sent["salary"] == "900000"
    assert sent["cover"] == "Dear team, I would love to join."
    assert sent["privacy"] is True
    assert sent["resume_name"] == "resume.pdf"
    # ... and everything that already had a value was left exactly as it was.
    assert sent["first_name"] == "SiteParsedFirst", "the site's own resume autofill must not be overwritten"
    assert sent["email"] == "tester@example.com"
    assert sent["phone"] == "000111", "a pre-filled phone number must not be replaced by the profile's"
    assert sent["notice"] == "60 days", "a pre-selected dropdown value must not be changed"
    assert sent["extra"] == "Typed by the applicant, keep me."
    assert sent["news"] is False, "marketing opt-ins are never ticked"


def test_google_button_inside_an_iframe_is_found_and_used(driver, site, me, resume):
    driver.get(site.base + "/gsi-login.html")

    result = run(driver, me, resume)

    assert result.status == APPLIED, result
    assert site.google_picks == ["tester@example.com"]
    assert len(site.submissions) == 1


def test_a_required_question_it_cannot_answer_is_never_guessed_or_submitted(driver, site, me, resume):
    driver.get(site.base + "/unknown-question.html")

    result = run(driver, me, resume)

    assert result.status == NEEDS_MANUAL
    assert any("Kubernetes" in label for label in result.unresolved), result.unresolved
    assert "unrecognised question" in result.detail, "the message should say WHY it would not answer"
    assert site.submissions == [], "must not submit with a required field empty"


def test_an_ai_answer_is_used_for_an_unknown_required_question(driver, site, me, resume):
    driver.get(site.base + "/unknown-question.html")
    asked = []

    def ai(question, options, kind):
        asked.append(question)
        return "2 years"

    result = run(driver, me, resume, ask_ai=ai)

    assert result.status == APPLIED, result
    assert any("Kubernetes" in q for q in asked)
    assert site.submissions == [{"k8s": "2 years"}]


def test_a_captcha_is_left_to_a_person_not_bypassed(driver, site, me, resume):
    driver.get(site.base + "/captcha.html")

    result = run(driver, me, resume)

    assert result.status == NEEDS_MANUAL
    assert "captcha" in result.detail.lower()


def test_a_site_that_only_offers_email_and_password_is_reported_not_forced(driver, site, me, resume):
    driver.get(site.base + "/no-google-login.html")

    result = run(driver, me, resume)

    assert result.status == NEEDS_MANUAL
    assert "no Google sign-in" in result.detail


def test_google_sign_in_can_be_switched_off(driver, site, me, resume):
    driver.get(site.base + "/login.html")

    result = run(driver, me, resume, quick(use_google_login=False))

    assert result.status == NEEDS_MANUAL
    assert site.google_picks == []


def test_a_page_with_nothing_to_apply_to_is_reported_after_a_few_tries(driver, site, me, resume):
    driver.get(site.base + "/blank.html")

    result = run(driver, me, resume)

    assert result.status == NEEDS_MANUAL
    assert "Could not find" in result.detail


def test_a_newsletter_box_on_a_job_page_is_not_mistaken_for_the_application_form(driver, site, me, resume):
    driver.get(site.base + "/job-newsletter.html")

    result = run(driver, me, resume)

    assert result.status == APPLIED, result
    assert "newsletter-typed" not in site.events, "the person's email must never be typed into a newsletter box"
    assert "hero-clicked" not in site.events, "a generic 'Continue' on a hero banner is not a cookie banner"


def test_an_unexpected_error_inside_the_engine_costs_one_job_not_the_run(driver, site, me, resume, monkeypatch):
    def boom(self):
        raise RuntimeError("something odd on this page")

    monkeypatch.setattr(ExternalApplier, "_run", boom)

    result = run(driver, me, resume)

    assert result.status == external_apply.FAILED
    assert "RuntimeError" in result.detail


def test_success_wording_on_a_job_page_is_not_mistaken_for_an_application(driver, site, me, resume):
    driver.get(site.base + "/faq.html")

    result = run(driver, me, resume)

    assert result.status == NEEDS_MANUAL, "text like 'once your application has been submitted...' must not count as a success"


def test_submit_is_pressed_once_and_never_blindly_repeated(driver, site, me, resume):
    driver.get(site.base + "/silent-submit.html")

    result = run(driver, me, resume, quick(confirmation_wait_seconds=3))

    assert result.status == NEEDS_MANUAL
    assert "never confirmed" in result.detail
    assert site.events.count("submit-click") == 1, "a second Submit could send the employer a duplicate application"


def test_links_that_only_look_like_apply_are_not_clicked(driver, site, me, resume):
    driver.get(site.base + "/job.html")
    run(driver, me, resume, quick(max_steps=1))
    urls = []
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        urls.append(driver.current_url)
    assert any(u.endswith("/login.html") for u in urls), "the real Apply link should have been followed"
    # "Saved jobs" / "Application status" / "About us" must never be followed as if they were Apply.
    assert not any(u.endswith(("/saved.html", "/status.html", "/about.html")) for u in urls), urls


def test_template_placeholder_details_are_refused_before_touching_the_browser(driver, site, resume):
    untouched = Profile.from_values(first_name="First", last_name="Last", phone="9876543210", email="username@example.com")
    driver.get(site.base + "/apply.html")

    result = run(driver, untouched, resume)

    assert result.status == NEEDS_MANUAL
    assert "Fill in your" in result.detail
    assert driver.find_element("id", "first").get_attribute("value") == "", "nothing may be typed for placeholder details"


def test_pausing_before_submit_lets_a_person_discard(driver, site, me, resume):
    driver.get(site.base + "/apply2.html")
    asked = []

    result = run(driver, me, resume, quick(pause_before_submit=True), confirm_submit=lambda url: asked.append(url) or False)

    assert result.status == external_apply.FAILED and "Discarded" in result.detail
    assert asked and site.submissions == []


def test_a_form_embedded_in_an_iframe_is_filled_and_submitted(driver, site, me, resume):
    driver.get(site.base + "/embed.html")

    result = run(driver, me, resume)

    assert result.status == APPLIED, result
    assert len(site.submissions) == 1
    assert site.submissions[0]["last_name"] == "Rao"
    assert site.submissions[0]["resume_name"] == "resume.pdf"


def test_visually_hidden_radios_and_checkboxes_are_operated_through_their_labels(driver, site, me, resume):
    driver.get(site.base + "/styled.html")

    result = run(driver, me, resume)

    assert result.status == APPLIED, result
    assert site.submissions == [{"sponsor": "no", "privacy": True}]


def test_it_never_guesses_which_google_account_to_use(driver, site, me, resume):
    driver.get(site.base + "/login.html")

    # The configured account is not in the list (which shows two other accounts): must not click the first one.
    result = run(driver, me, resume, quick(google_email="nobody@example.com"))
    assert result.status == NEEDS_MANUAL
    assert site.google_picks == [], "signing in with the wrong Google account could apply under a stranger's identity"

    # Nothing configured and several accounts listed: also a guess.
    site.reset()
    driver.get(site.base + "/login.html")
    result = run(driver, me, resume, quick(google_email=""))
    assert result.status == NEEDS_MANUAL
    assert site.google_picks == []


def test_a_single_listed_google_account_is_used_when_none_is_configured(driver, site, me, resume):
    driver.get(site.base + "/login-one.html")

    result = run(driver, me, resume, quick(google_email=""))

    assert result.status == APPLIED, result
    assert site.google_picks == ["solo@example.com"]


def test_a_plain_google_sign_in_consent_is_approved(driver, site, me, resume):
    driver.get(site.base + "/login-consent.html")

    result = run(driver, me, resume, quick(google_email="tester@example.com"))

    assert result.status == APPLIED, result
    assert "consent-clicked" in site.events


def test_google_screens_asking_for_drive_or_gmail_access_are_never_approved(driver, site, me, resume):
    driver.get(site.base + "/login-risky.html")

    result = run(driver, me, resume, quick(google_email="tester@example.com"))

    assert result.status == NEEDS_MANUAL
    assert "allow-clicked" not in site.events, "granting an employer's site access to Drive or Gmail must be your decision"


def test_a_field_revealed_by_an_earlier_answer_is_filled_too(driver, site, me, resume):
    driver.get(site.base + "/dependent.html")

    result = run(driver, me, resume)

    assert result.status == APPLIED, result
    assert site.submissions == [{"country": "India", "state": "Illinois"}]


def test_an_optional_essay_box_is_left_alone_and_never_sent_to_the_ai(driver, site, me, resume):
    driver.get(site.base + "/optional-textarea.html")
    asked = []

    result = run(driver, me, resume, ask_ai=lambda question, options, kind: asked.append(question) or "generated text")

    assert result.status == APPLIED, result
    assert asked == []
    assert site.submissions == [{"more": ""}]


def test_a_google_screen_that_wants_a_password_is_handed_to_the_person(driver, site, me, resume):
    driver.get(site.base + "/login-password.html")

    result = run(driver, me, resume)

    assert result.status == NEEDS_MANUAL
    assert "Google" in result.detail
    assert site.submissions == []


# ---------------------------------------------------------------------------
# The bot's own glue (runAiBot.external_apply), with the real Chrome launch stubbed out
# ---------------------------------------------------------------------------
@pytest.fixture
def bot(driver, site, tmp_path, monkeypatch, resume):
    import sys
    import types
    from selenium.webdriver.support.ui import WebDriverWait

    fake_chrome = types.ModuleType("modules.open_chrome")
    fake_chrome.options, fake_chrome.driver = None, driver
    fake_chrome.actions, fake_chrome.wait = None, WebDriverWait(driver, 5)
    monkeypatch.setitem(sys.modules, "modules.open_chrome", fake_chrome)
    monkeypatch.delitem(sys.modules, "runAiBot", raising=False)
    import runAiBot

    (tmp_path / "logs" / "screenshots").mkdir(parents=True)
    for name, value in dict(
        first_name="Asha", middle_name="", last_name="Rao", email="tester@example.com", phone_number="+91 98765 43210",
        current_city="Springfield", state="Illinois", zipcode="62701", country="India", street="", linkedIn="", website="",
        us_citizenship="", gender="", ethnicity="", disability_status="", veteran_status="", recent_employer="",
        linkedin_headline="", linkedin_summary="", years_of_experience="3", desired_salary="900000", current_ctc="600000",
        notice_period="30", require_visa="No", google_email="tester@example.com", use_AI=False, aiClient=None, run_in_background=False,
        pause_before_submit=False, external_manual_wait_seconds=0, external_apply_timeout_seconds=150,
        external_apply_max_steps=14, use_google_login=True, easy_apply_only=False, close_tabs=False,
        default_resume_path=resume, failed_file_name=str(tmp_path / "failed.csv"), logs_folder_path=str(tmp_path / "logs"),
        cover_letter="Dear team, I would love to join.", external_apply_active=True, failed_count=0,
    ).items():
        monkeypatch.setattr(runAiBot, name, value)
    monkeypatch.setattr(runAiBot, "linkedIn_tab", driver.current_window_handle)
    monkeypatch.setattr(runAiBot, "print_lg", lambda *a, **k: None)
    return runAiBot


def _open_external_tab(driver, url):
    driver.switch_to.new_window("tab")
    driver.get(url)
    return driver.current_window_handle


def test_bot_applies_on_a_company_site_records_it_and_returns_to_linkedin(driver, site, bot):
    tab = _open_external_tab(driver, site.base + "/job.html")

    skip, link, tabs, applied = bot.external_apply(None, "123", "https://linkedin.example/jobs/123", "Pending", "Unknown",
                                                   "Easy Applied", "Not Available", pending_tab=tab, description="An ad ops job")

    assert (skip, applied) == (False, True)
    assert link.endswith("/thanks.html")
    assert driver.window_handles == [bot.linkedIn_tab], "the company tab is closed and LinkedIn is the only tab left"
    assert driver.current_window_handle == bot.linkedIn_tab
    assert len(site.submissions) == 1


def test_bot_reports_a_stuck_company_site_as_failed_and_leaves_the_tab_open_for_you(driver, site, bot, tmp_path):
    tab = _open_external_tab(driver, site.base + "/unknown-question.html")

    skip, link, tabs, applied = bot.external_apply(None, "456", "https://linkedin.example/jobs/456", "Pending", "Unknown",
                                                   "Easy Applied", "Not Available", pending_tab=tab, description="")

    assert (skip, applied) == (True, False)
    assert bot.failed_count == 1
    assert tab in driver.window_handles, "the tab stays open so the person can finish the application by hand"
    assert driver.current_window_handle == bot.linkedIn_tab
    failed_rows = (tmp_path / "failed.csv").read_text(encoding="utf-8")
    assert "Company site:" in failed_rows and "Kubernetes" in failed_rows
    assert site.submissions == []


def test_bot_only_saves_the_link_when_company_site_applying_is_off(driver, site, bot, monkeypatch):
    monkeypatch.setattr(bot, "external_apply_active", False)
    tab = _open_external_tab(driver, site.base + "/job.html")

    skip, link, tabs, applied = bot.external_apply(None, "789", "https://linkedin.example/jobs/789", "Pending", "Unknown",
                                                   "Easy Applied", "Not Available", pending_tab=tab)

    assert (skip, applied) == (False, False)
    assert link.endswith("/job.html")
    assert site.submissions == []


def test_bot_builds_a_profile_that_never_carries_template_placeholders(bot, monkeypatch):
    monkeypatch.setattr(bot, "first_name", "First")
    monkeypatch.setattr(bot, "email", "")
    monkeypatch.setattr(bot, "google_email", "")
    monkeypatch.setattr(bot, "username", "username@example.com")

    profile = bot.build_external_profile()

    assert profile.first_name == "" and profile.email == ""
    assert "first name" in profile.missing_essentials() and "email" in profile.missing_essentials()
