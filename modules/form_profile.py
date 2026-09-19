'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

Decides what to put in a job-application form field, from a person's profile.
Pure Python (no browser), so every rule here is unit-tested.

The rules that matter:
  * A field that already has a value is NEVER touched - not by us, not by a site's
    resume autofill that ran before us.
  * Template placeholders ("First", "123 Main Street", ...) count as "not set", so
    a made-up value is never typed into a real employer's form.
  * A factual question we can't answer from the profile is reported as unknown -
    we don't guess (the caller may ask an AI, or hand the question to a human).
'''

import re
from dataclasses import dataclass, field

# Values shipped in the config templates. Someone who never edited them must not
# have "First Last, 123 Main Street" submitted to an employer.
_TEMPLATE_PLACEHOLDERS = {
    "first_name": {"first"},
    "last_name": {"last"},
    "phone": {"9876543210"},
    "street": {"123 main street"},
    "state": {"state"},
    "zipcode": {"12345"},
    "country": {"will let you know when established"},
    "email": {"username@example.com"},
    "recent_employer": {"not applicable"},
}


_NUMBER_FIELDS = ("desired_salary", "current_ctc", "notice_period")


def _to_int(value, unset: int = 0) -> int:
    '''The bot's config turns these into text ("1200000") before we see them; accept either, never raise.
    Blank or unreadable gives `unset`.'''
    if isinstance(value, bool):
        return unset
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "")
    digits = re.sub(r"[^\d.]", "", text)
    try:
        number = int(float(digits)) if digits else unset
    except ValueError:
        return unset
    return -number if digits and number and text.lstrip().startswith("-") else number


@dataclass
class Profile:
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    state: str = ""
    zipcode: str = ""
    country: str = ""
    street: str = ""
    linkedin: str = ""
    website: str = ""
    headline: str = ""
    summary: str = ""
    cover_letter: str = ""
    recent_employer: str = ""
    years_of_experience: str = ""
    desired_salary: int = 0
    current_ctc: int = 0
    notice_period: int = -1               # -1 = not set (0 means "can start immediately")
    require_visa: str = "No"
    us_citizenship: str = ""
    gender: str = ""
    ethnicity: str = ""
    disability_status: str = ""
    veteran_status: str = ""

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.middle_name, self.last_name) if part)

    @classmethod
    def from_values(cls, **values) -> "Profile":
        '''Builds a profile, blanking any value that is still a config-template placeholder.'''
        known = {name for name in cls.__dataclass_fields__}
        clean = {}
        for name, value in values.items():
            if name not in known:
                continue
            if name in _NUMBER_FIELDS:
                value = _to_int(value, unset=-1 if name == "notice_period" else 0)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(value)
            if isinstance(value, str):
                value = value.strip()
                if value.lower() in _TEMPLATE_PLACEHOLDERS.get(name, ()):
                    value = ""
            clean[name] = value
        return cls(**clean)

    def missing_essentials(self) -> list[str]:
        '''What must be set before it is safe to submit applications on this person's behalf.'''
        missing = []
        if not self.first_name:
            missing.append("first name")
        if not self.last_name:
            missing.append("last name")
        if not self.email:
            missing.append("email")
        if not self.phone:
            missing.append("phone number")
        return missing


@dataclass
class FieldInfo:
    '''What the page told us about one form control (or one radio group).'''
    kind: str                       # text | email | tel | url | number | date | textarea | select | radio | checkbox
    label: str = ""
    name: str = ""                  # id / name / autocomplete / placeholder hints
    autocomplete: str = ""
    required: bool = False
    value: str = ""                 # current text, or the selected option's text
    checked: bool = False           # checkbox state, or "some radio in the group is chosen"
    options: list = field(default_factory=list)
    input_type: str = ""


@dataclass
class Decision:
    action: str                     # fill | choose | check | skip | unknown
    value: str = ""
    key: str = ""                   # which profile item this maps to (for the log)
    reason: str = ""


def _norm(text: str) -> str:
    text = (text or "").lower().replace("*", " ").replace("(required)", " ").replace("required", " ")
    return re.sub(r"\s+", " ", text).strip()


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text) is not None


_PLACEHOLDER_OPTION = re.compile(r"^(select|choose|please|pick|--|\-\-|none$|n/a$|\s*$)")


def is_placeholder_option(text: str) -> bool:
    return bool(_PLACEHOLDER_OPTION.match(_norm(text))) or _norm(text) in ("select...", "select an option", "please select")


_DECLINE = r"decline|prefer not|do not wish|don't wish|not wish|choose not|not to (say|disclose|answer|identify)|rather not|do not want|don't want"


def _number_fits(option: str, value: float):
    '''
    Does `value` fall in the range an option describes ("3-5 years", "10+", "less than 1", "Over 5")?
    True / False, or None when the option holds no number at all.
    '''
    text = _norm(option)
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if re.search(r"less than|under|below|fewer than|<", text):
        return value < numbers[0]
    span = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|\u2013|to)\s*(\d+(?:\.\d+)?)", text)
    if span:
        return float(span.group(1)) <= value <= float(span.group(2))
    if re.search(r"more than|over|above|greater than|>", text):
        return value > numbers[0]
    if re.search(r"\d\s*\+|or more|and above|and over|at least|plus", text):
        return value >= numbers[0]
    return value == numbers[0]


def choose_option(options: list, desired: str):
    '''
    Picks the index of the option that best matches `desired`, or None.
    Understands "Decline", "Yes" and "No" as intents rather than literal text, and picks a numeric answer
    by range ("3" belongs in "3-5 years", not in "10-13").
    '''
    if not options or not desired:
        return None
    normalized = [_norm(o) for o in options]
    want = _norm(desired)

    if re.fullmatch(r"\d+(?:\.\d+)?", want) and any(re.search(r"\d", o) for o in normalized):
        for index, option in enumerate(options):
            if not is_placeholder_option(option) and _number_fits(option, float(want)):
                return index
        return None

    def first(predicate):
        for index, text in enumerate(normalized):
            if text and not is_placeholder_option(options[index]) and predicate(text):
                return index
        return None

    if want == "decline":
        return first(lambda t: _has(t, _DECLINE))
    if want in ("yes", "no"):
        exact = first(lambda t: t == want)
        if exact is not None:
            return exact
        return first(lambda t: t.startswith(want + " ") or t.startswith(want + ",") or t.startswith(want + "."))
    for matcher in (lambda t: t == want,
                    lambda t: t.startswith(want),
                    lambda t: want in t,
                    lambda t: t in want and len(t) > 2):
        hit = first(matcher)
        if hit is not None:
            return hit
    return None


def format_salary(amount: int, label: str) -> str:
    if _has(label, r"\blakh|\blpa\b"):
        return f"{amount / 100000:.2f}"
    if _has(label, r"\bmonth"):
        return str(round(amount / 12))
    return str(amount)


def format_notice(days: int, label: str) -> str:
    if _has(label, r"\bmonth"):
        return str(days // 30)
    if _has(label, r"\bweek"):
        return str(days // 7)
    return str(days)


_COUNTRIES = {
    "united states": "us", "u.s.": "us", "u.s.a.": "us", "usa": "us", "america": "us",
    "united kingdom": "uk", "uk": "uk", "great britain": "uk",
    "canada": "ca", "india": "in", "australia": "au", "germany": "de", "singapore": "sg",
    "united arab emirates": "ae", "uae": "ae", "ireland": "ie", "france": "fr", "netherlands": "nl",
}


def _countries_in(text: str) -> set:
    found = set()
    normalized = _norm(text)
    for word, code in _COUNTRIES.items():
        if re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", normalized):
            found.add(code)
    if re.search(r"\b(?:in|the|for)\s+us\b", normalized):
        found.add("us")
    return found


def _countries_authorised_in(profile: "Profile") -> set:
    home = _countries_in(profile.country)
    citizenship = _norm(profile.us_citizenship)
    if citizenship.startswith("u.s. citizen") or citizenship.startswith("non-citizen allowed"):
        home.add("us")
    if citizenship.startswith("canadian"):
        home.add("ca")
    return home


_MARKETING = r"newsletter|marketing|promotion|talent (community|network|pool)|stay in touch|job alert|receive (e-?mail|sms|text|updates|notifications)|subscribe|keep me (posted|updated)|contact me (about|regarding) (other|future)"
_CONSENT = r"agree|accept|consent|acknowledge|certify|i confirm|i understand|privacy|terms|declaration|truthful|true and (correct|accurate)"


def classify(field_info: FieldInfo) -> str:
    '''Names what a field is asking for ("first_name", "email", "desired_salary", ...), or "" if unknown.'''
    ac = _norm(field_info.autocomplete)
    by_autocomplete = {
        "given-name": "first_name", "family-name": "last_name", "name": "full_name", "additional-name": "middle_name",
        "email": "email", "tel": "phone", "tel-national": "phone", "address-level2": "city",
        "address-level1": "state", "postal-code": "zip", "country": "country", "country-name": "country",
        "street-address": "street", "address-line1": "street", "organization": "employer", "url": "website",
    }
    for token in ac.split():
        if token in by_autocomplete:
            return by_autocomplete[token]

    label = _norm(field_info.label)
    hint = _norm(f"{field_info.label} {field_info.name}")
    if field_info.input_type == "email" or _has(label, r"e-?mail"):
        return "email"
    if field_info.input_type == "tel":
        return "phone"

    rules = [
        (r"linked ?in", "linkedin"),
        (r"github|git hub|gitlab|stack ?overflow|twitter|instagram|facebook", "other_social"),
        (r"portfolio|personal (web)?site|web ?site|blog|\burl\b|\blink\b", "website"),
        (r"\bfirst name|given name|forename|preferred name", "first_name"),
        (r"\blast name|family name|surname", "last_name"),
        (r"\bmiddle (name|initial)", "middle_name"),
        (r"signature|type your (full )?name|sign here", "full_name"),
        (r"\b(full|legal|complete) name|^name$|^your name$|^name of applicant$|^applicant name$", "full_name"),
        (r"phone|mobile|telephone|contact number|cell", "phone"),
        (r"\bzip|postal|pin ?code", "zip"),
        (r"\bcountry\b", "country"),
        (r"\b(state|province|region)\b", "state"),
        (r"\bcity\b|\btown\b|current location|^location$|where are you (based|located)|city.*(state|country)|location \(city", "city"),
        (r"street|address line|^address$|mailing address|home address|current address|residential address", "street"),
        (r"(current|present|most recent|previous|last) (company|employer|organi[sz]ation)|^employer$|^company$", "employer"),
        (r"(current|present) (salary|ctc|compensation|pay)|current annual", "current_ctc"),
        (r"salary|ctc|compensation|remuneration|expected pay|pay expectation", "desired_salary"),
        (r"notice period|how soon can you (join|start)|available to (join|start)|earliest (start|joining)|when can you (join|start)|joining (time|date)|start date|date of joining|availability to (join|start)", "notice"),
        (r"(years?|yrs?)( of)?( (relevant|total|professional|work|industry|overall))* experience|experience.*\byears?\b|how many years", "years"),
        (r"cover letter|motivation letter|letter of (interest|motivation)", "cover_letter"),
        (r"\bheadline\b", "headline"),
        (r"summary|about (you|yourself)|tell us about|describe yourself|professional background", "summary"),
        (r"gender|\bsex\b|pronoun", "gender"),
        (r"ethnic|\brace\b|racial", "ethnicity"),
        (r"disabilit", "disability"),
        (r"veteran|military", "veteran"),
        (r"sponsor|visa|work permit", "visa"),
        (r"authori[sz]ed to work|authori[sz]ation|legally (eligible|entitled|permitted)|right to work|eligible to work|work in the", "work_auth"),
        (r"citizen|nationality", "citizenship"),
        (r"relocat", "relocate"),
        (r"(18|eighteen) (years|or older)|at least 18|over 18|legal age|age of (majority|18)", "adult"),
        (r"hear about|how did you (find|hear|learn|come)|where did you (find|hear|see)|referral source|source of (application|hire)", "hear_about"),
    ]
    for pattern, key in rules:
        if _has(label, pattern):
            return key
    for pattern, key in rules:
        if key in ("email", "phone", "zip", "first_name", "last_name") and _has(hint, pattern):
            return key
    return ""


def decide(field_info: FieldInfo, profile: Profile, today: str = "") -> Decision:
    '''
    The single decision point: what should go in this field?
    Never returns a "fill/choose/check" for a field that already has a value.
    '''
    kind = field_info.kind
    if kind == "checkbox":
        if field_info.checked:
            return Decision("skip", reason="already checked")
    elif kind == "radio":
        if field_info.checked:
            return Decision("skip", reason="already chosen")
    elif kind == "select":
        if field_info.value and not is_placeholder_option(field_info.value):
            return Decision("skip", reason="already selected")
    elif (field_info.value or "").strip():
        return Decision("skip", reason="already filled")

    label = _norm(field_info.label)

    if kind == "checkbox":
        if _has(label, _MARKETING):
            return Decision("skip", reason="marketing opt-in left off")
        if _has(label, _CONSENT):
            return Decision("check", key="consent")
        return Decision("unknown", reason="checkbox we don't recognise")

    key = classify(field_info)
    if not key:
        return Decision("unknown", reason="unrecognised question")

    yes_no = None
    if key == "visa":
        yes_no = "Yes" if profile.require_visa.strip().lower() == "yes" else "No"
    elif key == "work_auth":
        if _has(_norm(profile.us_citizenship), r"seeking work authori"):
            yes_no = "No"                                # said so explicitly: that is the answer
        else:
            asked_about = _countries_in(field_info.label)
            if asked_about and not (asked_about & _countries_authorised_in(profile)):
                return Decision("unknown", key=key, reason="asks about work authorization in a country that isn't yours - the tool won't claim it")
            yes_no = "Yes"
    elif key == "relocate":
        return Decision("unknown", key=key, reason="willingness to relocate isn't in your profile")
    elif key == "adult":
        yes_no = "Yes"

    text_values = {
        "first_name": profile.first_name, "last_name": profile.last_name, "middle_name": profile.middle_name,
        "full_name": profile.full_name, "email": profile.email, "phone": profile.phone,
        "city": profile.city, "state": profile.state, "zip": profile.zipcode, "country": profile.country,
        "street": profile.street, "linkedin": profile.linkedin, "website": profile.website,
        "employer": profile.recent_employer, "headline": profile.headline, "summary": profile.summary,
        "cover_letter": profile.cover_letter, "years": profile.years_of_experience,
        "hear_about": "LinkedIn",
    }
    if key == "desired_salary" and profile.desired_salary:
        text_values["desired_salary"] = format_salary(profile.desired_salary, label)
    if key == "current_ctc" and profile.current_ctc:
        text_values["current_ctc"] = format_salary(profile.current_ctc, label)
    if key == "notice" and profile.notice_period >= 0:
        text_values["notice"] = ("Immediately" if profile.notice_period == 0 and not _has(label, r"month|week|day")
                                 else format_notice(profile.notice_period, label))

    eeo = {"gender": profile.gender, "ethnicity": profile.ethnicity,
           "disability": profile.disability_status, "veteran": profile.veteran_status}

    if kind in ("select", "radio"):
        desired = ""
        if yes_no:
            desired = yes_no
        elif key in eeo:
            desired = eeo[key] or "Decline"
        elif key == "citizenship":
            desired = profile.us_citizenship
        elif key == "country":
            desired = profile.country
        elif key == "state":
            desired = profile.state
        elif key == "hear_about":
            desired = "LinkedIn"
        elif key in text_values:
            desired = str(text_values[key])
        if not desired:
            return Decision("unknown", key=key, reason=f"no {key} in your profile")
        index = choose_option(field_info.options, desired)
        if index is None and key == "hear_about":
            for fallback in ("Job board", "Job site", "Internet", "Online", "Social media", "Other"):
                index = choose_option(field_info.options, fallback)
                if index is not None:
                    break
        if index is None:
            return Decision("unknown", key=key, reason=f'no option matches "{desired}"')
        return Decision("choose", value=field_info.options[index], key=key)

    # text-like controls
    if kind == "textarea" and key not in ("summary", "cover_letter", "headline", "hear_about", "street"):
        return Decision("unknown", key=key, reason="a free-text box wants more than a single profile value")
    if key in eeo:
        return Decision("unknown", key=key, reason="demographic question asked as free text")
    if yes_no:
        return Decision("fill", value=yes_no, key=key)
    if field_info.input_type == "number" and key in ("years", "desired_salary", "current_ctc", "notice"):
        digits = re.findall(r"\d+(?:\.\d+)?", str(text_values.get(key, "")))
        value = digits[0] if digits else ""
    else:
        value = str(text_values.get(key, "") or "")
    if key == "other_social":
        return Decision("skip", key=key, reason="not in your profile")
    if not value:
        return Decision("unknown", key=key, reason=f"no {key} in your profile")
    return Decision("fill", value=value, key=key)
