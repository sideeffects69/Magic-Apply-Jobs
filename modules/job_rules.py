'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

Small, browser-free rules the bot uses to read and judge a LinkedIn job. They live here
(not in runAiBot.py) so they can be unit-tested without starting Chrome.
'''

import re
from urllib.parse import quote_plus

# "5 years", "3-5 years", "10+ years", "(2) years" ...
re_experience = re.compile(r'[(]?\s*(\d+)\s*[)]?\s*[-to]*\s*\d*[+]*\s*year[s]?', re.IGNORECASE)

_CLEARANCE = re.compile(
    r"\bpolygraph\b|\bts/sci\b|\btop[- ]secret\b"
    r"|\b(?:security|secret|dod|government|active|current)\s+clearance\b"
    r"|\bclearance\s+(?:level|eligib\w+)\b",
    re.IGNORECASE)

# A degree, not the verb ("master new tools"), a job title ("scrum master") or a product ("master data").
_MASTERS = re.compile(
    r"\bmaster['’]s\b|\bmasters?\s+(?:degree|of|in|level)\b|\b(?:mba|msc|m\.sc|mtech|m\.tech)\b",
    re.IGNORECASE)

_VISA = re.compile(r"\bsponsor|\bvisas?\b")


def job_search_url(term: str) -> str:
    '''LinkedIn search URL for `term`. The term is URL-encoded, so "R&D Engineer", "C#" and "C++" search for what they say.'''
    return "https://www.linkedin.com/jobs/search/?keywords=" + quote_plus(term.strip())


def parse_card_title(raw: str) -> str:
    '''The job title from a result card's text (its first line).'''
    return raw.split("\n")[0].strip()


def parse_card_subtitle(text: str) -> tuple[str, str, str]:
    '''
    Splits "Company · Location (Hybrid)" into (company, location, work_style).
    Works when the " · " or the "(Hybrid)" part is missing, instead of cutting a letter off the end.
    '''
    company, separator, rest = text.strip().partition(" · ")
    if not separator:
        company, rest = text.strip(), ""
    work_style = "Unknown"
    tag = re.search(r"\(([^()]*)\)\s*$", rest)
    if tag:
        work_style = tag.group(1).strip() or "Unknown"
        rest = rest[:tag.start()]
    return company.strip(), rest.strip(), work_style


def requires_security_clearance(description: str) -> bool:
    '''True if the job asks for a security clearance / polygraph. "Customs clearance" and "Secretary" do not count.'''
    return _CLEARANCE.search(description) is not None


def mentions_masters_degree(description: str) -> bool:
    '''True if the description talks about a Master's degree.'''
    return _MASTERS.search(description) is not None


def asks_about_visa(label: str) -> bool:
    '''True for visa / sponsorship questions (whole words only - "advisable" is not a visa question).'''
    return _VISA.search(label.lower()) is not None


def amount_texts(amount: int) -> tuple[str, str, str]:
    '''
    (plain, in lakhs, per month) as text for a salary / CTC. All blank when the person left it unset (0),
    so a made-up number is never typed into an application.
    '''
    if amount <= 0:
        return "", "", ""
    return str(amount), str(round(amount / 100000, 2)), str(round(amount / 12, 2))


def notice_texts(days: int) -> tuple[str, str, str]:
    '''(days, months, weeks) as text for a notice period. All blank when unset (-1); 0 means "can start immediately".'''
    if days < 0:
        return "", "", ""
    return str(days), str(days // 30), str(days // 7)


def asks_for_amount_or_notice(label: str) -> bool:
    '''True for the salary / CTC / notice-period questions - the ones that must never be answered with an unrelated number.'''
    label = label.lower()
    return any(word in label for word in ("notice", "salary", "compensation", "ctc", "pay"))


def unknown_text_answer(label: str, years_of_experience: str) -> str:
    '''
    What to type into a text box nothing else could answer: the person's years of experience (a number is usually
    what such boxes want) - but never for a salary / notice question, where that number would be a wrong answer.
    '''
    return "" if asks_for_amount_or_notice(label) else years_of_experience


def extract_years_required(text: str) -> int:
    '''
    The largest "N years" figure up to 12 in the text (bigger numbers are usually a company's age),
    or 0 when there is none.
    '''
    figures = [int(match) for match in re.findall(re_experience, text) if int(match) <= 12]
    return max(figures) if figures else 0
