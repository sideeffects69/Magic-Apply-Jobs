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


def test_a_profile_with_no_numbers_set_never_has_any_typed_for_it():
    # What a brand-new user has: nothing entered. The tool must ask a person (or the AI), not type a made-up number.
    nobody = Profile.from_values(first_name="Asha", last_name="Rao", email="asha@example.org", phone="+91 98765 43210",
                                 desired_salary="", current_ctc=0, notice_period="", years_of_experience="")
    for label in ("Expected salary", "Current CTC", "Notice period (days)", "How many years of experience do you have?"):
        decision = decide(field("text", label), nobody)
        assert decision.action == "unknown", f"{label!r} was answered {decision.value!r}"
    assert decide(field("text", "Notice period"), Profile()).action == "unknown"      # even a bare Profile()


def test_a_notice_period_of_minus_one_is_not_read_as_one_day():
    # The bot hands its numbers over as text; "-1" used to lose its sign and become 1.
    assert Profile.from_values(notice_period="-1").notice_period == -1
    assert decide(field("text", "Notice period"), Profile.from_values(notice_period="-1")).action == "unknown"


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


# ---------------------------------------------------------------------------
# Bugs found in a full review of the answer rules
# ---------------------------------------------------------------------------
def test_the_bots_config_passes_numbers_as_text_and_that_must_not_crash():
    profile = Profile.from_values(desired_salary="1200000", current_ctc="800,000", notice_period="30", years_of_experience=3)
    assert (profile.desired_salary, profile.current_ctc, profile.notice_period) == (1200000, 800000, 30)
    assert profile.years_of_experience == "3"
    assert decide(field("text", "Expected CTC in lakhs"), profile).value == "12.00"
    assert decide(field("text", "Notice period in weeks"), profile).value == "4"
    assert Profile.from_values(desired_salary="", notice_period=None).desired_salary == 0


@pytest.mark.parametrize("options, desired, expected", [
    (["Select", "0-2 years", "3-5 years", "10-13 years"], "3", 2),           # never the substring match "10-13"
    (["1-2", "2-3", "5+"], "3", 1),
    (["Less than 1 year", "1-3 years", "More than 5 years"], "0", 0),
    (["Less than 1 year", "1-3 years", "More than 5 years"], "8", 2),
    (["0-1", "2-4", "10+"], "12", 2),
    (["4-6", "10-13"], "3", None),                                            # no range holds 3: unknown, not a guess
    (["30 days", "60 days", "90 days"], "60", 1),
    (["30 days", "60 days", "90 days"], "45", None),
])
def test_a_number_picks_the_option_whose_range_holds_it(options, desired, expected):
    assert choose_option(options, desired) == expected


def test_years_of_experience_dropdown_end_to_end(me):
    options = ["Select", "0-2 years", "3-5 years", "6-10 years", "10-13 years"]
    decision = decide(field("select", "Total years of experience", options=options), me)
    assert (decision.action, decision.value) == ("choose", "3-5 years")


def test_a_single_value_is_never_typed_into_an_essay_box(me):
    for label in ("Describe your experience over the last 3 years", "Tell us your notice period and why you are leaving",
                  "Explain your years of experience in ad tech"):
        assert decide(field("textarea", label), me).action == "unknown", label
    assert decide(field("textarea", "Cover letter"), me).action == "fill"
    assert decide(field("textarea", "Tell us about yourself"), me).value == "Ad-tech pro."


def test_work_authorisation_is_only_claimed_for_the_country_you_live_in(me):
    # `me` lives in India with no US status.
    yes_no = ["Yes", "No"]
    assert decide(field("radio", "Are you legally authorized to work in the United States?", options=yes_no), me).action == "unknown"
    assert decide(field("radio", "Are you authorized to work in the UK?", options=yes_no), me).action == "unknown"
    assert decide(field("radio", "Are you legally authorized to work in India?", options=yes_no), me).value == "Yes"
    assert decide(field("radio", "Are you authorized to work for our company?", options=yes_no), me).value == "Yes"
    american = Profile.from_values(country="United States", us_citizenship="U.S. Citizen/Permanent Resident")
    assert decide(field("radio", "Are you legally authorized to work in the US?", options=yes_no), american).value == "Yes"


def test_willingness_to_relocate_is_not_assumed(me):
    assert decide(field("radio", "Are you willing to relocate?", options=["Yes", "No"]), me).action == "unknown"


def test_availability_alone_is_not_a_notice_period(me):
    assert decide(field("text", "Weekend availability"), me).action == "unknown"
    assert decide(field("text", "Earliest start date"), me).value == "30"
