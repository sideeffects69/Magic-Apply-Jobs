"""
Rules the bot uses to read and judge a LinkedIn job. Each one guards a bug that was really in the tool.
"""

import pytest

from modules.job_rules import (amount_texts, asks_about_visa, asks_for_amount_or_notice, extract_years_required,
                               job_search_url, mentions_masters_degree, notice_texts, parse_card_subtitle,
                               parse_card_title, requires_security_clearance, unknown_text_answer)


@pytest.mark.parametrize("term, expected", [
    ("Software Engineer", "keywords=Software+Engineer"),
    ("R&D Engineer", "keywords=R%26D+Engineer"),
    ("Sales & Marketing", "keywords=Sales+%26+Marketing"),
    ("C#", "keywords=C%23"),
    ("C++ Developer", "keywords=C%2B%2B+Developer"),
    ("  Accountant  ", "keywords=Accountant"),
])
def test_search_terms_are_url_encoded_so_they_search_for_what_they_say(term, expected):
    assert job_search_url(term).endswith(expected)


def test_title_without_a_newline_keeps_its_last_letter():
    assert parse_card_title("Software Engineer") == "Software Engineer"          # used to lose the final "r"
    assert parse_card_title("Software Engineer\nSoftware Engineer with verification") == "Software Engineer"


@pytest.mark.parametrize("text, expected", [
    ("Acme · Springfield, Illinois, United States (Hybrid)", ("Acme", "Springfield, Illinois, United States", "Hybrid")),
    ("Acme · Springfield, Illinois, United States", ("Acme", "Springfield, Illinois, United States", "Unknown")),     # no work-style tag
    ("Acme · Remote (Remote)", ("Acme", "Remote", "Remote")),
    ("Acme", ("Acme", "", "Unknown")),                                                        # no " · " at all
    ("Acme Ltd · Springfield, IL (On-site)", ("Acme Ltd", "Springfield, IL", "On-site")),
])
def test_card_subtitle_is_split_without_cutting_letters_off(text, expected):
    assert parse_card_subtitle(text) == expected


@pytest.mark.parametrize("description, expected", [
    ("Requires an active Secret clearance", True),
    ("Must obtain a security clearance", True),
    ("TS/SCI with polygraph", True),
    ("Top Secret facility", True),
    ("Handle customs clearance and freight forwarding", False),
    ("Clearance sale planning for the retail floor", False),
    ("Executive Secretary to the CEO", False),
    ("Secretarial support and minutes", False),
    ("We keep the secret sauce simple", False),
])
def test_only_real_security_clearance_requirements_count(description, expected):
    assert requires_security_clearance(description) is expected


@pytest.mark.parametrize("description, expected", [
    ("Master's degree preferred", True),
    ("Masters in Computer Science", True),
    ("MBA from a top school", True),
    ("Bachelor's or Master of Science", True),
    ("Certified Scrum Master", False),
    ("Ability to master new tools quickly", False),
    ("Webmaster duties", False),
    ("Master data management", False),
])
def test_masters_degree_is_a_degree_not_a_word_that_contains_master(description, expected):
    assert mentions_masters_degree(description) is expected


@pytest.mark.parametrize("label, expected", [
    ("Will you require visa sponsorship?", True),
    ("Do you need sponsorship now or in the future", True),
    ("Are you eligible for a work visa?", True),
    ("It is advisable to bring a portfolio", False),
    ("Describe a time you envisage change", False),
])
def test_visa_questions_are_whole_words(label, expected):
    assert asks_about_visa(label) is expected


@pytest.mark.parametrize("text, expected", [
    ("3+ years of experience", 3),
    ("5-7 years", 5),                                   # the lower bound is the minimum requirement
    ("We have been in business for 25 years", 0),          # a company's age, not a requirement
    ("15+ years of history and 4 years experience needed", 4),
    ("No experience stated", 0),
])
def test_required_years_never_crashes_and_ignores_company_age(text, expected):
    assert extract_years_required(text) == expected


# ---------------------------------------------------------------------------
# Salary / notice answers: "not set" must stay blank, never turn into a number
# ---------------------------------------------------------------------------
def test_an_unset_salary_and_notice_period_produce_blank_answers():
    assert amount_texts(0) == ("", "", "")
    assert notice_texts(-1) == ("", "", "")


def test_amounts_that_are_set_convert_as_before():
    assert amount_texts(1200000) == ("1200000", "12.0", "100000.0")
    assert notice_texts(66) == ("66", "2", "9")


def test_a_notice_period_of_zero_means_immediately_not_unset():
    assert notice_texts(0) == ("0", "0", "0")


@pytest.mark.parametrize("label, expected", [
    ("What is your expected salary?", True), ("Notice period (in days)", True), ("Current CTC in lakhs", True),
    ("Expected compensation", True), ("How many years of Python experience do you have?", False),
    ("Are you comfortable working night shifts?", False),
])
def test_salary_and_notice_questions_are_recognised(label, expected):
    assert asks_for_amount_or_notice(label) is expected


def test_an_unknown_text_question_gets_the_years_number_but_never_a_salary_or_notice_question():
    assert unknown_text_answer("how many years with react?", "3") == "3"
    assert unknown_text_answer("what is your expected salary?", "3") == ""      # used to type the years into a salary box
    assert unknown_text_answer("notice period", "3") == ""
