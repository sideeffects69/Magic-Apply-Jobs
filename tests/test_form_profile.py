"""
The rules that decide what goes into an external job application form. Pure logic,
no browser. The two that matter most: never touch a field that already has a value,
and never type a made-up value into a real employer's form.
"""

import pytest

from modules.form_profile import (Decision, FieldInfo, Profile, choose_option, classify, decide,
                                  format_notice, format_salary)


@pytest.fixture
def me():
    return Profile.from_values(
        first_name="Asha", middle_name="", last_name="Rao", email="asha@example.org", phone="+91 98765 43210",
        city="Springfield", state="Illinois", zipcode="62701", country="India", street="12 MG Road",
        linkedin="https://www.linkedin.com/in/asha", website="https://asha.dev", recent_employer="Acme Ltd",
        years_of_experience="3", desired_salary=900000, current_ctc=600000, notice_period=30,
        require_visa="No", us_citizenship="Other", gender="Female", ethnicity="Asian",
        disability_status="No", veteran_status="No", cover_letter="Dear team, ...", summary="Ad-tech pro.",
    )


def field(kind="text", label="", **kw):
    return FieldInfo(kind=kind, label=label, **kw)


# ---------------------------------------------------------------------------
# The two safety rules
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind, kwargs", [
    ("text", {"value": "Already Typed"}),
    ("textarea", {"value": "My own words"}),
    ("select", {"value": "Illinois", "options": ["Select", "Illinois", "Goa"]}),
    ("radio", {"checked": True, "options": ["Yes", "No"]}),
    ("checkbox", {"checked": True}),
])
def test_a_field_that_already_has_a_value_is_never_touched(me, kind, kwargs):
    decision = decide(field(kind, "First name", **kwargs), me)
    assert decision.action == "skip"


def test_a_site_autofilled_value_is_kept_even_if_it_differs_from_the_profile(me):
    assert decide(field("text", "Email", value="autofilled@site.com", input_type="email"), me).action == "skip"


def test_placeholder_defaults_from_the_config_template_count_as_not_set():
    untouched = Profile.from_values(first_name="First", last_name="Last", phone="9876543210", street="123 Main Street",
                                    state="STATE", zipcode="12345", country="Will Let You Know When Established",
                                    email="username@example.com", recent_employer="Not Applicable")
    assert untouched.first_name == untouched.last_name == untouched.phone == untouched.street == ""
    assert untouched.state == untouched.zipcode == untouched.country == untouched.email == untouched.recent_employer == ""
    assert set(untouched.missing_essentials()) == {"first name", "last name", "email", "phone number"}
    assert decide(field("text", "Street address"), untouched).action == "unknown"


def test_a_complete_profile_is_ready(me):
    assert me.missing_essentials() == []
    assert me.full_name == "Asha Rao"


# ---------------------------------------------------------------------------
# What goes where
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("label, expected", [
    ("First name *", "Asha"), ("Last Name", "Rao"), ("Full name", "Asha Rao"), ("Name", "Asha Rao"),
    ("Phone number", "+91 98765 43210"), ("Mobile", "+91 98765 43210"),
    ("City", "Springfield"), ("Current location", "Springfield"), ("State / Province", "Illinois"),
    ("Postal code", "62701"), ("Country", "India"), ("Street address", "12 MG Road"),
    ("LinkedIn profile URL", "https://www.linkedin.com/in/asha"),
    ("Portfolio / website", "https://asha.dev"), ("Current employer", "Acme Ltd"),
    ("Total years of experience", "3"), ("How did you hear about us?", "LinkedIn"),
    ("Please sign by typing your full name", "Asha Rao"),
])
def test_text_fields_get_the_matching_profile_value(me, label, expected):
    decision = decide(field("text", label), me)
    assert (decision.action, decision.value) == ("fill", expected)


def test_email_is_recognised_from_the_input_type_even_with_a_vague_label(me):
    assert decide(field("email", "Contact", input_type="email"), me).value == "asha@example.org"


def test_autocomplete_attribute_wins_over_a_confusing_label(me):
    assert decide(field("text", "Tell us", autocomplete="given-name"), me).value == "Asha"


@pytest.mark.parametrize("label, expected", [
    ("Expected salary (annual)", "900000"),
    ("Expected CTC in lakhs", "9.00"),
    ("Expected monthly salary", "75000"),
    ("Current CTC", "600000"),
    ("Current salary in lakhs", "6.00"),
    ("Notice period", "30"),
    ("Notice period (in months)", "1"),
    ("Notice period in weeks", "4"),
])
def test_salary_and_notice_are_formatted_the_way_the_question_asks(me, label, expected):
    assert decide(field("text", label), me).value == expected


def test_zero_notice_period_reads_as_immediately(me):
    someone = Profile.from_values(notice_period=0)
    assert decide(field("text", "When can you start?"), someone).value == "Immediately"


def test_number_inputs_get_digits_only(me):
    assert decide(field("number", "Expected CTC in lakhs", input_type="number"), me).value == "9.00"
    assert decide(field("number", "Years of experience", input_type="number"), me).value == "3"


# ---------------------------------------------------------------------------
# Dropdowns and radio groups
# ---------------------------------------------------------------------------
def test_sponsorship_follows_the_profile_and_maps_onto_the_options(me):
    options = ["Select...", "Yes", "No"]
    decision = decide(field("select", "Will you now or in the future require visa sponsorship?", options=options), me)
    assert (decision.action, decision.value) == ("choose", "No")

    needs_visa = Profile.from_values(require_visa="Yes")
    assert decide(field("radio", "Do you require sponsorship?", options=["Yes", "No"]), needs_visa).value == "Yes"


def test_work_authorisation_is_yes_unless_the_profile_says_otherwise(me):
    assert decide(field("radio", "Are you legally authorized to work in India?", options=["Yes", "No"]), me).value == "Yes"
    seeking = Profile.from_values(us_citizenship="Non-citizen seeking work authorization")
    assert decide(field("radio", "Are you legally authorized to work in the US?", options=["Yes", "No"]), seeking).value == "No"


def test_demographic_questions_use_the_profile_and_default_to_decline(me):
    options = ["Select", "Male", "Female", "Decline to self identify"]
    assert decide(field("select", "Gender", options=options), me).value == "Female"
    blank = Profile.from_values()
    assert decide(field("select", "Gender", options=options), blank).value == "Decline to self identify"
    assert decide(field("select", "Veteran status", options=["I am a veteran", "I prefer not to answer"]), blank).value == "I prefer not to answer"


def test_how_did_you_hear_falls_back_to_a_generic_source_when_linkedin_is_not_listed(me):
    decision = decide(field("select", "How did you hear about this job?", options=["Select", "Employee referral", "Job board", "Other"]), me)
    assert (decision.action, decision.value) == ("choose", "Job board")
    decision = decide(field("select", "How did you hear about us?", options=["Select", "LinkedIn", "Indeed"]), me)
    assert decision.value == "LinkedIn"


def test_a_select_with_no_matching_option_is_unknown_not_a_guess(me):
    decision = decide(field("select", "State", options=["Select", "Karnataka", "Kerala"]), me)
    assert decision.action == "unknown"


@pytest.mark.parametrize("options, desired, expected", [
    (["Select an option", "Yes", "No"], "Yes", 1),
    (["Yes, I do", "No, I don't"], "No", 1),
    (["Full-time", "Part-time"], "part-time", 1),
    (["Male", "Female", "Non-binary"], "Female", 1),
    (["Prefer not to say", "Male"], "Decline", 0),
    (["Select", "India (+91)", "USA (+1)"], "India", 1),
    (["Select", "A", "B"], "Z", None),
    ([], "Yes", None),
])
def test_choose_option(options, desired, expected):
    assert choose_option(options, desired) == expected


# ---------------------------------------------------------------------------
# Consent, opt-ins and things we must not guess
# ---------------------------------------------------------------------------
def test_privacy_and_terms_checkboxes_are_ticked(me):
    decision = decide(field("checkbox", "I agree to the Privacy Policy and Terms of Use"), me)
    assert (decision.action, decision.key) == ("check", "consent")


def test_marketing_opt_ins_are_left_alone(me):
    for label in ("Send me the newsletter", "Keep me updated about future jobs", "I agree to receive marketing emails",
                  "Join our talent community"):
        assert decide(field("checkbox", label), me).action == "skip", label


def test_a_factual_question_we_cannot_answer_is_unknown_and_never_guessed(me):
    for label in ("Do you have experience with Kubernetes?", "Describe a time you led a team", "Favourite colour"):
        assert decide(field("text", label), me).action == "unknown", label


def test_unknown_carries_the_reason_so_the_log_can_say_why(me):
    decision = decide(field("text", "GitHub profile"), me)
    assert decision.action == "skip" and decision.key == "other_social"
    assert isinstance(decide(field("text", "Favourite colour"), me), Decision)


@pytest.mark.parametrize("amount, label, expected", [(900000, "salary in lakhs", "9.00"), (900000, "per month", "75000"), (900000, "salary", "900000")])
def test_format_salary(amount, label, expected):
    assert format_salary(amount, label) == expected


@pytest.mark.parametrize("days, label, expected", [(60, "notice in months", "2"), (15, "in weeks", "2"), (15, "notice", "15")])
def test_format_notice(days, label, expected):
    assert format_notice(days, label) == expected


def test_classify_returns_empty_for_unrecognised_fields():
    assert classify(field("text", "Something entirely different")) == ""
