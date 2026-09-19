"""
Rules the bot uses to read and judge a LinkedIn job. Each one guards a bug that was really in the tool.
"""

import pytest

from modules.job_rules import (asks_about_visa, extract_years_required, job_search_url, mentions_masters_degree,
                               parse_card_subtitle, parse_card_title, requires_security_clearance)


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
