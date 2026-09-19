'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

Applies to a job on ANY company website, starting from the tab LinkedIn opened.

What it does, in order, on whatever page it lands on:
  1. Finds the Apply button and follows it (new tab, same tab or pop-up).
  2. If the site wants you to sign in, finds the "Sign in / Sign up with Google"
     button (in the page or inside Google's own iframe) and uses it. The Google
     account chooser is completed for you; a password, 2-step verification or
     CAPTCHA is left to the person at the keyboard - it waits, it never tries to
     get past them.
  3. Uploads the resume, so the site's own resume-autofill runs first.
  4. Fills only the fields that are STILL empty (modules/form_profile.py decides
     what goes where). Anything already filled - by the site or by the person - is
     left exactly as it is.
  5. Clicks Next / Continue / Submit, page after page, until the site confirms.

It will not click Submit while a required field is empty, and it does not make up
answers: a question it can't answer from the profile is handed to the AI (if one is
configured) or to the person, otherwise the job is reported as "needs manual".
'''

import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from selenium.common.exceptions import (ElementNotInteractableException, NoSuchWindowException,
                                        StaleElementReferenceException,
                                        UnexpectedAlertPresentException, WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from modules.form_profile import Decision, FieldInfo, Profile, choose_option, decide, is_placeholder_option

APPLIED = "applied"
NEEDS_MANUAL = "needs_manual"
FAILED = "failed"

GOOGLE_AUTH_HOSTS = ("accounts.google.com",)


@dataclass
class ExternalResult:
    status: str
    detail: str = ""
    url: str = ""
    steps: int = 0
    filled: int = 0
    unresolved: list = field(default_factory=list)


@dataclass
class ExternalSettings:
    max_steps: int = 25
    timeout_seconds: int = 300
    manual_wait_seconds: int = 120      # how long to wait for a person (captcha, Google password/2FA, unanswerable question)
    use_google_login: bool = True
    google_email: str = ""
    pause_before_submit: bool = False
    confirmation_wait_seconds: int = 20  # how long to wait for the site to confirm after Submit before giving up (never re-clicks Submit blindly)


# ---------------------------------------------------------------------------
# Page scripts. They run inside the page and return plain data (plus the
# elements themselves, which Selenium hands back as WebElements).
# ---------------------------------------------------------------------------
_JS_COMMON = r'''
const isVisible = (el) => {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2 || r.right < 0 || r.bottom < 0) return false;
  const s = getComputedStyle(el);
  if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) === 0) return false;
  if (el.closest('[aria-hidden="true"], [hidden]')) return false;
  return true;
};
const text = (n) => ((n && (n.innerText || n.textContent)) || '').replace(/\s+/g, ' ').trim();
'''

_JS_COLLECT_FIELDS = _JS_COMMON + r'''
const labelText = (el) => {
  const parts = [];
  const by = el.getAttribute('aria-labelledby');
  if (by) by.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) parts.push(text(n)); });
  if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) parts.push(text(l)); }
  const wrap = el.closest('label'); if (wrap) parts.push(text(wrap));
  const aria = el.getAttribute('aria-label'); if (aria) parts.push(aria);
  if (!parts.join('').trim()) {
    let node = el.parentElement;
    for (let hop = 0; node && hop < 3 && !parts.join('').trim(); hop++, node = node.parentElement) {
      const cand = node.querySelector('label, legend, [class*=label], [class*=Label], h3, h4');
      if (cand && cand !== el && !cand.contains(el)) parts.push(text(cand));
    }
  }
  if (!parts.join('').trim()) parts.push(el.getAttribute('placeholder') || el.getAttribute('title') || '');
  return parts.join(' ').replace(/\s+/g, ' ').trim();
};
const groupQuestion = (el, optionTexts) => {
  const fs = el.closest('fieldset'); if (fs) { const lg = fs.querySelector('legend'); if (lg && text(lg)) return text(lg); }
  const rg = el.closest('[role=radiogroup], [role=group]');
  if (rg) {
    const lb = rg.getAttribute('aria-labelledby');
    if (lb) { const n = document.getElementById(lb.split(/\s+/)[0]); if (n && text(n)) return text(n); }
    if (rg.getAttribute('aria-label')) return rg.getAttribute('aria-label');
  }
  let node = el.parentElement;
  for (let hop = 0; node && hop < 5; hop++, node = node.parentElement) {
    const lines = (node.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    const q = lines.find(l => !optionTexts.includes(l) && l.length > 2);
    if (q && node.querySelectorAll('input[type=radio]').length === optionTexts.length) return q;
  }
  return '';
};
const controlVisible = (el) => {
  if (isVisible(el)) return true;
  if (el.type === 'radio' || el.type === 'checkbox') {
    const l = (el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]')) || el.closest('label');
    return !!l && isVisible(l);
  }
  return false;
};
const SEL = 'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=image]):not([type=reset]):not([type=file]):not([type=password]):not([type=search]), select, textarea';
const out = [];
const doneRadio = new Set();
document.querySelectorAll(SEL).forEach(el => {
  if (el.disabled || el.readOnly) return;
  if (!controlVisible(el)) return;
  if (el.closest('nav, header, footer') && !el.closest('form')) return;
  const hints = ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.placeholder || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
  if (/(^|[^a-z])search([^a-z]|$)/.test(hints)) return;
  const tag = el.tagName.toLowerCase();
  const type = (el.type || '').toLowerCase();
  const base = {
    label: '', name: (el.id || '') + ' ' + (el.name || '') + ' ' + (el.placeholder || ''),
    autocomplete: el.getAttribute('autocomplete') || '', required: false, value: '', checked: false,
    options: [], input_type: type, combobox: el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete') === 'list',
  };
  if (type === 'radio') {
    const key = el.name || ('__r' + out.length);
    if (doneRadio.has(key)) return;
    doneRadio.add(key);
    const group = Array.from(document.querySelectorAll('input[type=radio]')).filter(r => (r.name || '') === (el.name || '') && controlVisible(r));
    const labels = group.map(r => {
      const l = (r.id && document.querySelector('label[for="' + CSS.escape(r.id) + '"]')) || r.closest('label');
      return l ? text(l) : (r.value || '');
    });
    base.kind = 'radio'; base.label = groupQuestion(group[0], labels) || labelText(group[0]);
    base.options = labels; base.checked = group.some(r => r.checked);
    base.required = group.some(r => r.required || r.getAttribute('aria-required') === 'true') || /\*/.test(base.label);
    base.els = group;
    out.push(base); return;
  }
  base.label = labelText(el);
  base.required = el.required || el.getAttribute('aria-required') === 'true' || /\*/.test(base.label);
  if (type === 'checkbox') { base.kind = 'checkbox'; base.checked = el.checked; }
  else if (tag === 'select') {
    base.kind = 'select';
    base.options = Array.from(el.options).map(o => (o.text || '').trim());
    base.value = el.selectedIndex >= 0 ? (el.options[el.selectedIndex].text || '').trim() : '';
  }
  else if (tag === 'textarea') { base.kind = 'textarea'; base.value = el.value; }
  else { base.kind = ['email', 'tel', 'url', 'number', 'date'].includes(type) ? type : 'text'; base.value = el.value; }
  base.el = el;
  out.push(base);
});
return out;
'''

_JS_FILE_INPUTS = _JS_COMMON + r'''
const out = [];
document.querySelectorAll('input[type=file]').forEach(el => {
  if (el.disabled) return;
  const container = el.closest('label, div, li, section, fieldset') || el.parentElement;
  const l = (el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]')) || el.closest('label');
  const label = [text(l), el.getAttribute('aria-label') || '', text(container).slice(0, 120), el.name || '', el.id || ''].join(' | ').toLowerCase();
  out.push({el: el, label: label, has_file: !!(el.files && el.files.length), accept: el.accept || ''});
});
return out;
'''

_JS_BUTTONS = _JS_COMMON + r'''
const sel = 'button, input[type=submit], input[type=button], a[role=button], a.btn, a.button, [role=button]';
const out = [];
document.querySelectorAll(sel).forEach(el => {
  if (!isVisible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
  const t = text(el) || el.value || el.getAttribute('aria-label') || el.title || '';
  if (!t) return;
  out.push({el: el, text: t.trim(), href: el.getAttribute('href') || ''});
});
return out;
'''

_JS_LINKS = _JS_COMMON + r'''
const out = [];
document.querySelectorAll('a[href]').forEach(el => {
  if (!isVisible(el)) return;
  const t = text(el) || el.getAttribute('aria-label') || '';
  if (t) out.push({el: el, text: t, href: el.getAttribute('href') || ''});
});
return out;
'''

_JS_GOOGLE_BUTTONS = _JS_COMMON + r'''
const intent = /(sign|log)[\s-]?(in|up|on)|continue|register|create|apply|connect|join|use|with google|via google/i;
const bad = /policies\.google|support\.google|maps\.google|analytics\.google|google\.com\/(intl|maps|policies)/i;
const out = [];
const sel = 'button, a, [role=button], div[tabindex], span[role=button], input[type=button], input[type=submit], li[role=button]';
document.querySelectorAll(sel).forEach(el => {
  if (!isVisible(el)) return;
  const img = el.querySelector('img'); const svgt = el.querySelector('svg title');
  const bag = [text(el), el.value || '', el.getAttribute('aria-label') || '', el.title || '',
               img ? (img.alt || img.src || '') : '', svgt ? text(svgt) : '',
               el.getAttribute('data-provider') || '', el.getAttribute('data-testid') || '', el.id || ''].join(' | ').toLowerCase();
  if (!bag.includes('google')) return;
  if (bad.test(el.getAttribute('href') || '')) return;
  if (text(el).length > 70) return;
  if (!(intent.test(bag) || text(el).length <= 24)) return;
  if (el.querySelector(sel) && el.querySelectorAll(sel).length > 2) return;
  out.push(el);
});
return out;
'''

_JS_COOKIE_BUTTONS = _JS_COMMON + r'''
const holder = /cookie|consent|gdpr|onetrust|cookiebot|truste|osano|didomi|usercentrics|cmp-|cc-window|cc_banner/i;
const out = [];
document.querySelectorAll('button, a[role=button], [role=button], a.btn').forEach(el => {
  if (!isVisible(el)) return;
  const box = el.closest('[id],[class],[role=dialog]');
  let probe = el, hit = false;
  for (let i = 0; probe && i < 6; i++, probe = probe.parentElement) {
    if (holder.test((probe.id || '') + ' ' + (probe.className && probe.className.toString ? probe.className.toString() : '') + ' ' + (probe.getAttribute('aria-label') || ''))) { hit = true; break; }
  }
  if (hit) out.push({el: el, text: text(el)});
});
return out;
'''

_JS_PAGE_STATE = _JS_COMMON + r'''
const body = document.body ? (document.body.innerText || '') : '';
const busy = Array.from(document.querySelectorAll('[aria-busy="true"], [role=progressbar], .spinner, .loading, .loader, [class*=spinner], [class*=loading]')).filter(isVisible).length;
const captcha = Array.from(document.querySelectorAll('iframe')).filter(f => {
  const src = (f.src || '').toLowerCase();
  if (!isVisible(f)) return false;
  if (src.includes('recaptcha') && src.includes('anchor') && !src.includes('size=invisible')) return true;
  if (src.includes('hcaptcha.com') || src.includes('challenges.cloudflare.com') || src.includes('recaptcha/api2/bframe')) { const r = f.getBoundingClientRect(); return r.width >= 60 && r.height >= 40; }
  return false;
}).length;
const errors = Array.from(document.querySelectorAll('[aria-invalid="true"], .error, .errors, .field-error, .invalid-feedback, [role=alert], [class*=error]')).filter(isVisible).map(text).filter(t => t && t.length < 200).slice(0, 4);
return {text: body.slice(0, 6000), busy: busy, captcha: captcha, errors: errors, has_password: !!Array.from(document.querySelectorAll('input[type=password]')).filter(isVisible).length};
'''

_SUCCESS_TEXT = re.compile(
    r"thank you for (applying|your application|your interest|submitting)|application (has been |was |is )?(successfully )?(submitted|received|sent|complete)|"
    r"successfully (applied|submitted)|we('| ha)ve received your application|you('ve| have) (successfully )?applied|"
    r"your application (is|has been) (in|received|submitted)|application confirmation")
_SUCCESS_URL = re.compile(r"thank|confirm|application-?submitted|/success|submitted")
_BLOCKED_TEXT = re.compile(r"verify you are (a )?human|are you a robot|checking your browser|unusual traffic|access denied|request blocked|attention required")
_APPLY_CTA = re.compile(r"^(apply( now| here| online| today| for this (job|position|role)| to this (job|position|role)| for job| on company (site|website))?|i'?m interested( in this job)?|start( your)? application|apply now →|quick apply|easy apply)\W*$")
_APPLY_BAD = re.compile(r"filter|coupon|saved|applied|status|view|withdraw|track|history|already|alert|later")
_SIGNIN_TRIGGER = re.compile(r"^(sign ?in|log ?in|login|sign ?up|register|create( an)? account|join now|candidate (login|sign ?in))\W*$")
_GUEST = re.compile(r"(apply|continue|proceed) (as (a )?guest|without (an )?(account|(signing|logging) in|registering))|guest (apply|checkout)|skip( sign ?in)?$|i don'?t have an account")
_FINAL = re.compile(r"^(submit( my| your)?( application)?|send( my)? application|finish|complete( application)?|confirm( and)?( apply| submit)?|apply( now)?|submit & apply|submit and apply|done)\W*$")
_NEXT = re.compile(r"^(next|continue|save (and|&|\+) continue|save (and|&) next|proceed|review( (and|&) submit| application)?|next step|go to (the )?next|continue to .+|continue application|next page)\W*$")
_NEVER = re.compile(r"back|previous|cancel|save for later|save draft|sign ?out|log ?out|withdraw|delete|reset|clear|close|search|share|print|download|upload|attach|add (another|more)|remove|edit|no thanks|not now")
_COOKIE_REJECT = re.compile(r"^(reject( all)?|decline( all)?|only (necessary|essential)|necessary only|essential only|refuse|deny)\b")
_COOKIE_ACCEPT = re.compile(r"^(accept( all)?( cookies)?|allow( all)?( cookies)?|i agree|agree|got it|understood)\W*$")
_RESUME_LABEL = re.compile(r"resume|cv\b|curriculum")
_NOT_RESUME = re.compile(r"cover|photo|picture|portfolio|transcript|certificate|letter|passport|id proof|avatar|logo|reference|writing sample")
_FRAME_SKIP = re.compile(r"recaptcha|hcaptcha|doubleclick|googletagmanager|facebook|youtube|google\.com/gsi|accounts\.google|analytics|adsystem|stripe|intercom|zendesk|drift|chat")
# A plain "sign in with Google" screen only shares your name, email and picture. Anything that asks for more than that
# (Drive, Gmail, Calendar, "see, edit, delete"...) must be reviewed by the person - never clicked through automatically.
_GOOGLE_RISKY = re.compile(r"see, edit|edit, create|create, and delete|delete all|permanently delete|google drive|gmail|google calendar|google contacts|"
                           r"read, compose|send email|manage your|all of your|full access|view and manage|offline access|make requests|access to your google account")
_GOOGLE_BLOCKED = re.compile(r"may not be secure|couldn'?t sign you in|this browser or app|try using a different browser")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


class ExternalApplier:
    '''Drives one application on an external site. `run()` returns an ExternalResult.'''

    def __init__(self, driver, profile: Profile, resume_path: str = "", settings: ExternalSettings | None = None,
                 ask_ai=None, confirm_submit=None, log=print):
        self.driver = driver
        self.profile = profile
        self.resume_path = os.path.abspath(resume_path) if resume_path else ""
        self.settings = settings or ExternalSettings()
        self.ask_ai = ask_ai                    # (question, options, kind) -> str
        self.confirm_submit = confirm_submit    # (url) -> True to submit, False to discard
        self.log = log
        self.origin_handle = None
        self._uploads = 0
        self._filled_total = 0
        self._google_attempts = 0
        self._submit_clicks = 0
        self._advanced = False              # True once we have pressed Next/Submit ourselves
        self._reasons = {}                  # question label -> why the tool would not answer it
        self._signin_clicks = 0
        self._deadline = 0.0

    # ------------------------------------------------------------------ utils
    def _js(self, script, *args):
        return self.driver.execute_script(script, *args)

    def _url(self) -> str:
        try:
            return self.driver.current_url
        except WebDriverException:
            return ""

    @staticmethod
    def _host(url: str) -> str:
        return (urlparse(url).hostname or "").lower()

    def _is_google_url(self, url: str) -> bool:
        return self._host(url) in GOOGLE_AUTH_HOSTS

    def _out_of_time(self) -> bool:
        return time.monotonic() > self._deadline

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _click(self, element) -> bool:
        '''Scrolls to and clicks an element, falling back to a script click. True if a click was delivered.'''
        try:
            self._js("arguments[0].scrollIntoView({block:'center', inline:'nearest'});", element)
        except WebDriverException:
            pass
        try:
            element.click()
            return True
        except (ElementNotInteractableException, StaleElementReferenceException, WebDriverException):
            try:
                self._js("arguments[0].click();", element)
                return True
            except WebDriverException:
                return False

    def _wait_for_human(self, reason: str, until, seconds: int) -> bool:
        '''Waits for a person to sort something out in the open browser window. True if `until()` became true.'''
        if seconds <= 0:
            return False
        self.log(f"Waiting up to {seconds}s for you: {reason}")
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                if until():
                    return True
            except WebDriverException:
                return False
            self._sleep(2)
        return False

    def _signature(self) -> str:
        try:
            state = self._js(_JS_PAGE_STATE)
            return f"{self._url()}|{hash(state['text'][:1500])}"
        except WebDriverException:
            return self._url()

    def _wait_for_change(self, before: str, seconds: float = 8.0) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._sleep(0.5)
            try:
                if self.driver.current_window_handle and self._signature() != before:
                    return True
            except WebDriverException:
                return True        # the tab we were on is gone (e.g. a pop-up closed): that is a change
        return False

    # -------------------------------------------------------------- windows
    def _follow_new_window(self, known: set) -> bool:
        '''If a new tab/window opened since `known`, switch to it. Returns True if we switched.'''
        try:
            handles = self.driver.window_handles
        except WebDriverException:
            return False
        fresh = [h for h in handles if h not in known]
        if not fresh:
            return False
        self.driver.switch_to.window(fresh[-1])
        return True

    def _settle(self, seconds: float = 8.0) -> None:
        '''Waits for the page to finish loading and for any spinner to go away.'''
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                ready = self.driver.execute_script("return document.readyState") == "complete"
                busy = self._js(_JS_PAGE_STATE)["busy"]
                if ready and not busy:
                    return
            except WebDriverException:
                return
            self._sleep(0.4)

    # ---------------------------------------------------------------- probes
    def _state(self) -> dict:
        return self._js(_JS_PAGE_STATE)

    def _buttons(self) -> list:
        return self._js(_JS_BUTTONS) or []

    def _find_button(self, pattern, buttons=None):
        for item in (buttons if buttons is not None else self._buttons()):
            label = _norm(item["text"])
            if pattern.match(label) and not _NEVER.search(label):
                return item
        return None

    def _looks_successful(self, state: dict) -> bool:
        if not self._advanced:
            return False
        text = _norm(state["text"])
        if _SUCCESS_TEXT.search(text):
            return True
        url_path = (urlparse(self._url()).path or "").lower()
        return bool(_SUCCESS_URL.search(url_path)) and not self._collect_fields()

    # ---------------------------------------------------------------- frames
    def _form_frames(self) -> list:
        '''Visible, reasonably large iframes that could hold an application form (not ads, chat or captchas).'''
        frames = []
        try:
            candidates = self.driver.find_elements(By.CSS_SELECTOR, "iframe")
        except WebDriverException:
            return frames
        for frame in candidates:
            try:
                size = frame.size
                if (frame.is_displayed() and size["width"] >= 250 and size["height"] >= 150
                        and not _FRAME_SKIP.search((frame.get_attribute("src") or "").lower())):
                    frames.append(frame)
            except WebDriverException:
                continue
        return frames[:4]

    def _enter_form_frame(self) -> bool:
        '''Switches into the first iframe that contains a form. Many career sites embed their application this way.'''
        for frame in self._form_frames():
            try:
                self.driver.switch_to.frame(frame)
                if self._collect_fields() or self._js(_JS_FILE_INPUTS):
                    return True
            except WebDriverException:
                pass
            try:
                self.driver.switch_to.default_content()
            except WebDriverException:
                pass
        return False

    def _success_in_frames(self) -> bool:
        if not self._advanced:
            return False
        for frame in self._form_frames():
            found = False
            try:
                self.driver.switch_to.frame(frame)
                found = bool(_SUCCESS_TEXT.search(_norm(self._state()["text"])))
            except WebDriverException:
                pass
            try:
                self.driver.switch_to.default_content()
            except WebDriverException:
                pass
            if found:
                return True
        return False

    # --------------------------------------------------------------- cookies
    def _dismiss_cookie_banner(self) -> None:
        try:
            options = self._js(_JS_COOKIE_BUTTONS) or []
        except WebDriverException:
            return
        for pattern in (_COOKIE_REJECT, _COOKIE_ACCEPT):
            for item in options:
                if pattern.match(_norm(item["text"])):
                    if self._click(item["el"]):
                        self._sleep(0.5)
                    return

    # ---------------------------------------------------------------- fields
    def _collect_fields(self) -> list:
        '''[(FieldInfo, raw)] for every visible, editable control on the page.'''
        try:
            raw_fields = self._js(_JS_COLLECT_FIELDS) or []
        except WebDriverException:
            return []
        fields = []
        for raw in raw_fields:
            info = FieldInfo(kind=raw["kind"], label=raw.get("label", ""), name=raw.get("name", ""),
                             autocomplete=raw.get("autocomplete", ""), required=bool(raw.get("required")),
                             value=raw.get("value", "") or "", checked=bool(raw.get("checked")),
                             options=raw.get("options", []), input_type=raw.get("input_type", ""))
            fields.append((info, raw))
        return fields

    @staticmethod
    def _is_empty(info: FieldInfo) -> bool:
        if info.kind in ("checkbox", "radio"):
            return not info.checked
        if info.kind == "select":
            return not info.value or is_placeholder_option(info.value)
        return not (info.value or "").strip()

    def _type_into(self, raw: dict, value: str) -> bool:
        element = raw["el"]
        try:
            self._js("arguments[0].scrollIntoView({block:'center'});", element)
            element.click()
        except WebDriverException:
            pass
        try:
            element.send_keys(value)
        except (ElementNotInteractableException, WebDriverException):
            pass
        if (element.get_attribute("value") or "") == "":
            self._js("""
                const el = arguments[0], v = arguments[1];
                const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            """, element, value)
        if raw.get("combobox"):
            self._sleep(0.7)
            try:
                element.send_keys(Keys.ARROW_DOWN)
                element.send_keys(Keys.ENTER)
            except WebDriverException:
                pass
        else:
            try:
                element.send_keys(Keys.TAB)
            except WebDriverException:
                pass
        return (element.get_attribute("value") or "") != ""

    def _choose(self, raw: dict, info: FieldInfo, option_text: str) -> bool:
        if info.kind == "select":
            select = Select(raw["el"])
            index = choose_option([o.text for o in select.options], option_text)
            if index is None:
                return False
            select.select_by_index(index)
            return True
        index = choose_option(info.options, option_text)
        if index is None:
            return False
        radio = raw["els"][index]
        label = None
        try:
            label = self._js("const r=arguments[0]; return (r.id && document.querySelector('label[for=\"'+CSS.escape(r.id)+'\"]')) || r.closest('label');", radio)
        except WebDriverException:
            pass
        clicked = self._click(label) if label is not None else False
        if not clicked or not radio.is_selected():
            self._click(radio)
        return bool(radio.is_selected())

    def _check(self, raw: dict) -> bool:
        box = raw["el"]
        if box.is_selected():
            return True
        label = None
        try:
            label = self._js("const r=arguments[0]; return (r.id && document.querySelector('label[for=\"'+CSS.escape(r.id)+'\"]')) || r.closest('label');", box)
        except WebDriverException:
            pass
        if label is not None:
            self._click(label)
        if not box.is_selected():
            self._click(box)
        return box.is_selected()

    def _ai_decision(self, info: FieldInfo):
        if not self.ask_ai:
            return None
        try:
            answer = self.ask_ai(info.label, info.options, info.kind)
        except Exception as error:   # the AI layer must never sink an application
            self.log(f"AI could not answer \"{info.label}\": {error}")
            return None
        answer = (answer or "").strip()
        if not answer:
            return None
        if info.kind in ("select", "radio"):
            index = choose_option(info.options, answer)
            if index is None:
                return None
            return Decision("choose", value=info.options[index], key="ai")
        return Decision("fill", value=answer, key="ai")

    def _fill_page(self) -> tuple:
        '''Fills what is empty and safe to fill. Returns (number filled, labels of required fields still empty).'''
        filled = 0
        for info, raw in self._collect_fields():
            decision = decide(info, self.profile)
            if decision.action == "unknown" and info.required and self._is_empty(info):
                decision = self._ai_decision(info) or decision
            if decision.action == "unknown" and decision.reason:
                self._reasons[info.label or info.name.strip() or info.kind] = decision.reason
            try:
                if decision.action == "fill" and self._type_into(raw, decision.value):
                    filled += 1
                    self.log(f'Filled "{info.label or info.name.strip()}" ({decision.key})')
                elif decision.action == "choose" and self._choose(raw, info, decision.value):
                    filled += 1
                    self.log(f'Chose "{decision.value}" for "{info.label}" ({decision.key})')
                elif decision.action == "check" and self._check(raw):
                    filled += 1
                    self.log(f'Ticked "{info.label}"')
            except (StaleElementReferenceException, WebDriverException) as error:
                self.log(f'Could not fill "{info.label}": {type(error).__name__}')
        self._filled_total += filled
        return filled, self._unresolved()

    def _unresolved(self) -> list:
        return [(info.label or info.name.strip() or info.kind) for info, _ in self._collect_fields()
                if info.required and self._is_empty(info)]

    # ---------------------------------------------------------------- resume
    def _upload_resume(self) -> bool:
        '''Attaches the resume to the resume field so the site can autofill from it.'''
        if not self.resume_path or not os.path.isfile(self.resume_path) or self._uploads >= 2:
            return False
        try:
            inputs = self._js(_JS_FILE_INPUTS) or []
        except WebDriverException:
            return False
        candidates = [i for i in inputs if not i["has_file"]]
        picked = next((i for i in candidates if _RESUME_LABEL.search(i["label"]) and not _NOT_RESUME.search(i["label"].split("|")[0][:60])), None)
        if picked is None and len(inputs) == 1 and candidates and not _NOT_RESUME.search(candidates[0]["label"]):
            picked = candidates[0]
        if picked is None:
            return False
        element = picked["el"]
        try:
            self._js("""const e = arguments[0];
                e.style.cssText += ';display:block !important;visibility:visible !important;opacity:1 !important;position:static !important;width:auto !important;height:auto !important;';""", element)
            element.send_keys(self.resume_path)
        except (ElementNotInteractableException, WebDriverException) as error:
            self.log(f"Could not attach the resume: {type(error).__name__}")
            return False
        self._uploads += 1
        self.log(f"Uploaded resume: {os.path.basename(self.resume_path)}")
        self._sleep(1.5)
        self._settle(10)
        return True

    # ---------------------------------------------------------------- google
    def _google_buttons(self) -> list:
        try:
            return self._js(_JS_GOOGLE_BUTTONS) or []
        except WebDriverException:
            return []

    def _google_frames(self) -> list:
        selector = ("iframe[src*='accounts.google.com/gsi'], iframe[title*='Sign in with Google' i], "
                    "iframe[id^='gsi_'], iframe[src*='accounts.google.com/o/oauth2'], iframe#credential_picker_iframe")
        try:
            return [f for f in self.driver.find_elements(By.CSS_SELECTOR, selector) if f.is_displayed()]
        except WebDriverException:
            return []

    def _click_google_in_frame(self, frame) -> bool:
        try:
            self.driver.switch_to.frame(frame)
            for selector in ("div[role='button']", "button", "[role='button']", "span[role='button']"):
                for candidate in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    if candidate.is_displayed():
                        candidate.click()
                        return True
        except WebDriverException:
            return False
        finally:
            try:
                self.driver.switch_to.default_content()
            except WebDriverException:
                pass
        return False

    def _has_google_option(self) -> bool:
        return bool(self._google_buttons() or self._google_frames())

    def _sign_in_with_google(self) -> bool:
        '''Clicks the page's Google button and completes Google's account screens. True if we came back signed in.'''
        self._google_attempts += 1
        known = set(self.driver.window_handles)
        origin = self.driver.current_window_handle
        clicked = False
        for element in self._google_buttons():
            if self._click(element):
                clicked = True
                self.log("Clicked the Google sign-in button")
                break
        if not clicked:
            for frame in self._google_frames():
                if self._click_google_in_frame(frame):
                    clicked = True
                    self.log("Clicked the Google sign-in button (inside Google's frame)")
                    break
        if not clicked:
            return False

        google_window = self._await_google_window(known, origin)
        if google_window is None:
            # No Google page opened. Some sites use the browser's own account prompt instead, which can't be
            # driven from here - give the person a chance to pick their account in it.
            before = self._signature()
            if self._wait_for_human("pick your Google account in the sign-in prompt the browser is showing",
                                    lambda: self._signature() != before, self.settings.manual_wait_seconds):
                self._settle(10)
                return True
            self.log("Google's sign-in screen did not open")
            return False
        ok = self._complete_google_screens(google_window, origin)
        try:
            handles = self.driver.window_handles
            self.driver.switch_to.window(origin if origin in handles else handles[-1])
        except WebDriverException:
            return False
        self._settle(10)
        return ok

    def _await_google_window(self, known: set, origin: str):
        '''Returns the handle whose page is a Google sign-in screen (a pop-up, or the same tab), or None.'''
        end = time.monotonic() + 15
        while time.monotonic() < end:
            try:
                for handle in self.driver.window_handles:
                    self.driver.switch_to.window(handle)
                    if self._is_google_url(self._url()) and (handle not in known or handle == origin):
                        return handle
            except WebDriverException:
                pass
            self._sleep(0.5)
        try:
            self.driver.switch_to.window(origin)
        except WebDriverException:
            pass
        return None

    def _complete_google_screens(self, window: str, origin: str) -> bool:
        '''Walks Google's account chooser / consent screens; leaves passwords, 2-step and CAPTCHAs to the person.'''
        budget = max(45, self.settings.manual_wait_seconds + 45)
        end = time.monotonic() + budget
        want = _norm(self.settings.google_email)
        while time.monotonic() < end:
            try:
                handles = self.driver.window_handles
                if window not in handles:
                    return True                                  # pop-up closed itself: signed in
                self.driver.switch_to.window(window)
                if not self._is_google_url(self._url()):
                    return True                                  # same tab was sent back to the site
                text = _norm(self._state()["text"])
            except NoSuchWindowException:
                return True
            except WebDriverException:
                return False
            if _GOOGLE_BLOCKED.search(text):
                self.log("Google refused the automated browser. Sign in by hand once in this browser window, then try again.")
                return False
            if "/challenge" in self._url() or "/signin/v2/challenge" in self._url() or self._has_password_field():
                if not self._wait_for_human("finish Google's password / 2-step screen in the browser window",
                                            lambda: self._google_finished(window), self.settings.manual_wait_seconds):
                    return False
                continue
            accounts = self._google_accounts()
            if accounts:
                chosen = self._choose_google_account(accounts, want)
                if chosen is None:
                    reason = (f'your Google account "{self.settings.google_email}" is not in the list' if want
                              else "several Google accounts are listed")
                    if not self._wait_for_human(f"pick the Google account to use in the browser window ({reason})",
                                                lambda: not self._google_accounts() or self._google_finished(window),
                                                self.settings.manual_wait_seconds):
                        self.log(f"Not choosing a Google account for you: {reason}.")
                        return False
                    continue
                self.log(f"Choosing Google account {chosen.get_attribute('data-identifier')}")
                self._click(chosen)
                self._sleep(1.5)
                continue
            if self._google_email_box() is not None:
                if want and self._type_google_email():
                    self._sleep(1.5)
                    continue
                if not want and not self._wait_for_human(
                        "choose or type your Google account in the browser window (or set your Google email in the Account tab)",
                        lambda: self._google_email_box() is None, self.settings.manual_wait_seconds):
                    return False
                continue
            consent = self._google_consent_button()
            if consent is not None:
                if _GOOGLE_RISKY.search(text):
                    if not self._wait_for_human("Google is asking for permissions beyond signing in - review them in the browser window",
                                                lambda: self._google_finished(window), self.settings.manual_wait_seconds):
                        self.log("Google is asking for more than a sign-in (e.g. access to Drive or Gmail); not approving that for you.")
                        return False
                    continue
                self._click(consent)
                self._sleep(1.5)
                continue
            self._sleep(1)
        return False

    def _google_finished(self, window: str) -> bool:
        try:
            if window not in self.driver.window_handles:
                return True
            self.driver.switch_to.window(window)
            return not self._is_google_url(self._url()) or (not self._has_password_field() and "/challenge" not in self._url())
        except WebDriverException:
            return True

    def _has_password_field(self) -> bool:
        try:
            return any(f.is_displayed() for f in self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']"))
        except WebDriverException:
            return False

    def _google_accounts(self) -> list:
        try:
            return [a for a in self.driver.find_elements(By.CSS_SELECTOR, "[data-identifier]")
                    if a.is_displayed() and a.get_attribute("data-identifier")]
        except WebDriverException:
            return []

    @staticmethod
    def _choose_google_account(accounts: list, want: str):
        """The account to sign in with, or None when it would be a guess (the configured one is missing / several are listed)."""
        if want:
            return next((a for a in accounts if want == _norm(a.get_attribute("data-identifier"))), None)
        return accounts[0] if len(accounts) == 1 else None

    def _google_email_box(self):
        '''The visible, still-empty email box on a Google sign-in page, or None.'''
        try:
            for box in self.driver.find_elements(By.CSS_SELECTOR, "input[type='email'], input#identifierId"):
                if box.is_displayed() and not box.get_attribute("value"):
                    return box
        except WebDriverException:
            pass
        return None

    def _type_google_email(self) -> bool:
        box = self._google_email_box()
        if box is None:
            return False
        try:
            box.send_keys(self.settings.google_email + Keys.ENTER)
            return True
        except WebDriverException:
            return False

    def _google_consent_button(self):
        pattern = re.compile(r"^(continue|allow|confirm|yes|i understand|next|accept|agree)$")
        try:
            for item in self._buttons():
                if pattern.match(_norm(item["text"])):
                    return item["el"]
        except WebDriverException:
            pass
        return None

    # ------------------------------------------------------------------ steps
    def _click_apply(self, buttons: list) -> bool:
        candidates = []
        for item in buttons + (self._js(_JS_LINKS) or []):
            label = _norm(item["text"])
            if _APPLY_CTA.match(label) and not _APPLY_BAD.search(label):
                candidates.append(item)
        if not candidates:
            return False
        known = set(self.driver.window_handles)
        before = self._signature()
        if not self._click(candidates[0]["el"]):
            return False
        self.log(f'Clicked "{candidates[0]["text"]}"')
        self._sleep(1)
        self._follow_new_window(known)
        self._wait_for_change(before, 6)
        return True

    def _click_signin_trigger(self, buttons: list) -> bool:
        if self._signin_clicks >= 3:
            return False
        for item in buttons + (self._js(_JS_LINKS) or []):
            if _SIGNIN_TRIGGER.match(_norm(item["text"])):
                known = set(self.driver.window_handles)
                before = self._signature()
                if self._click(item["el"]):
                    self._signin_clicks += 1
                    self.log(f'Clicked "{item["text"]}" to look for a Google sign-in')
                    self._sleep(1)
                    self._follow_new_window(known)
                    self._wait_for_change(before, 5)
                    return True
        return False

    def _advance(self, buttons: list, state: dict):
        '''Clicks the Next/Submit button. Returns "submitted", "next" or None if there was nothing to click.'''
        final = self._find_button(_FINAL, buttons)
        nxt = self._find_button(_NEXT, buttons)
        target, kind = (final, "submitted") if final else (nxt, "next")
        if target is None:
            return None
        if kind == "submitted" and self.settings.pause_before_submit and self.confirm_submit:
            if not self.confirm_submit(self._url()):
                raise _Discarded()
        before = self._signature()
        known = set(self.driver.window_handles)
        if not self._click(target["el"]):
            return None
        self.log(f'Clicked "{target["text"]}"')
        self._sleep(1)
        self._follow_new_window(known)
        self._wait_for_change(before, 8)
        return kind

    def _await_confirmation(self) -> bool:
        '''After Submit: waits for the site to confirm. False if it shows errors instead, or never confirms.'''
        end = time.monotonic() + self.settings.confirmation_wait_seconds
        while time.monotonic() < end:
            try:
                self.driver.switch_to.default_content()
                state = self._state()
                if self._looks_successful(state) or self._success_in_frames():
                    return True
                if state["errors"]:
                    return False        # the site is complaining about something: that is not a confirmation
            except WebDriverException:
                pass
            self._sleep(1)
        return False

    # -------------------------------------------------------------------- run
    def run(self) -> ExternalResult:
        self._deadline = time.monotonic() + self.settings.timeout_seconds
        try:
            self.origin_handle = self.driver.current_window_handle
            return self._run()
        except _Discarded:
            return ExternalResult(FAILED, "Discarded by you before submitting", self._url(), filled=self._filled_total)
        except NoSuchWindowException:
            return ExternalResult(FAILED, "The browser window was closed", "", filled=self._filled_total)
        except UnexpectedAlertPresentException:
            try:
                self.driver.switch_to.alert.dismiss()
            except WebDriverException:
                pass
            return ExternalResult(NEEDS_MANUAL, "The site showed a pop-up message", self._url(), filled=self._filled_total)
        except WebDriverException as error:
            return ExternalResult(FAILED, f"Browser error: {type(error).__name__}", self._url(), filled=self._filled_total)
        except Exception as error:      # a bug or an odd page must cost one job, never the whole run
            return ExternalResult(FAILED, f"Unexpected error: {type(error).__name__}: {error}", self._url(), filled=self._filled_total)

    def _result(self, status, detail, steps, unresolved=None) -> ExternalResult:
        return ExternalResult(status, detail, self._url(), steps, self._filled_total, unresolved or [])

    def _run(self) -> ExternalResult:
        missing = self.profile.missing_essentials()
        if missing:
            return self._result(NEEDS_MANUAL, "Fill in your " + ", ".join(missing) + " first (Profile tab) - the tool will not send template placeholder values to employers", 0)
        stuck = 0
        idle = 0
        last_signature = None
        for step in range(1, self.settings.max_steps + 1):
            if self._out_of_time():
                return self._result(NEEDS_MANUAL, "Ran out of time on this site", step)
            self._settle(8)
            try:
                self.driver.switch_to.default_content()
            except WebDriverException:
                pass
            self._dismiss_cookie_banner()
            state = self._state()
            text = _norm(state["text"])

            if self._looks_successful(state) or self._success_in_frames():
                return self._result(APPLIED, "The site confirmed the application", step)

            if state["captcha"] or _BLOCKED_TEXT.search(text):
                gone = lambda: not self._state()["captcha"] and not _BLOCKED_TEXT.search(_norm(self._state()["text"]))
                if not self._wait_for_human("solve the CAPTCHA / verification in the browser window", gone, self.settings.manual_wait_seconds):
                    return self._result(NEEDS_MANUAL, "The site asked for a CAPTCHA / human check", step)
                continue

            buttons = self._buttons()
            fields = self._collect_fields()
            # On a sign-in page the email / username box is a credential, not an application question.
            real_fields = [f for f, _ in fields
                           if not (state["has_password"] and (f.kind == "email" or re.search(r"user ?name|e-?mail|log ?in", _norm(f.label + " " + f.name))))]
            has_file = bool(self._js(_JS_FILE_INPUTS))
            google_here = self.settings.use_google_login and self._has_google_option()
            if not real_fields and not has_file and not google_here and not state["has_password"] and self._enter_form_frame():
                # The form lives in an iframe: work inside it from here (the next loop starts back at the top page).
                self._dismiss_cookie_banner()
                state = self._state()
                buttons = self._buttons()
                fields = self._collect_fields()
                real_fields = [f for f, _ in fields]
                has_file = bool(self._js(_JS_FILE_INPUTS))

            # ---- a sign-in / sign-up wall
            if google_here and (state["has_password"] or (len(real_fields) <= 2 and not has_file)):
                if self._google_attempts >= 3:
                    return self._result(NEEDS_MANUAL, "Google sign-in did not get past the login page", step)
                if self._sign_in_with_google():
                    idle = 0
                    continue
                return self._result(NEEDS_MANUAL, "Could not complete the Google sign-in (it may need your password or 2-step verification)", step)

            if state["has_password"] and len(real_fields) <= 2 and not has_file:
                guest = self._find_button(_GUEST, buttons)
                if guest and self._click(guest["el"]):
                    self._sleep(1.5)
                    continue
                return self._result(NEEDS_MANUAL, "This site needs an account and has no Google sign-in option", step)

            # ---- a job page with a small side form (newsletter, alerts): press Apply first, don't fill that box
            form_like = has_file or len(real_fields) >= 3 or any(f.required for f in real_fields)
            if real_fields and not form_like and self._click_apply(buttons):
                idle = 0
                continue

            # ---- an application form
            if real_fields or has_file:
                if has_file:
                    self._upload_resume()
                filled, unresolved = 0, []
                for _ in range(3):
                    passed, unresolved = self._fill_page()
                    filled += passed
                    if not passed:
                        break
                if unresolved:
                    ok = self._wait_for_human(
                        "answer the highlighted questions in the browser window: " + "; ".join(unresolved[:4]),
                        lambda: not self._unresolved(), self.settings.manual_wait_seconds)
                    if not ok:
                        described = [f"{label} ({self._reasons[label]})" if label in self._reasons else label for label in unresolved[:6]]
                        return self._result(NEEDS_MANUAL, "Required questions the tool can't answer: " + "; ".join(described), step, unresolved)
                buttons = self._buttons()
                clicked = self._advance(buttons, state)
                if clicked is None:
                    return self._result(NEEDS_MANUAL, "Filled the form but found no Next / Submit button", step)
                self._advanced = True
                if clicked == "submitted":
                    self._submit_clicks += 1
                    if self._await_confirmation():
                        return self._result(APPLIED, "The site confirmed the application", step)
                    try:
                        showing_errors = bool(self._state()["errors"])
                    except WebDriverException:
                        showing_errors = False
                    if not showing_errors or self._submit_clicks >= 2:
                        return self._result(NEEDS_MANUAL, "Pressed Submit but the site never confirmed it - check whether the application went through before applying again", step)
                signature = self._signature()
                stuck = stuck + 1 if signature == last_signature else 0
                last_signature = signature
                if stuck >= 2:
                    errors = self._state()["errors"]
                    return self._result(NEEDS_MANUAL, "Could not get past this page" + (": " + " | ".join(errors[:3]) if errors else ""), step)
                continue

            # ---- a job page: press Apply
            if self._click_apply(buttons):
                idle = 0
                continue
            if self.settings.use_google_login and self._click_signin_trigger(buttons):
                continue

            idle += 1
            if idle >= 3:
                return self._result(NEEDS_MANUAL, "Could not find an application form or an Apply button on this page", step)
            try:
                self._js("window.scrollBy(0, Math.max(400, window.innerHeight * 0.8));")
            except WebDriverException:
                pass
            self._sleep(1)
        return self._result(NEEDS_MANUAL, "Too many steps without finishing - stopped for safety", self.settings.max_steps)


class _Discarded(Exception):
    pass


def apply_on_external_site(driver, profile: Profile, resume_path: str, settings: ExternalSettings | None = None,
                           ask_ai=None, confirm_submit=None, log=print) -> ExternalResult:
    '''Convenience entry point: apply on whatever site the driver's current tab is showing.'''
    return ExternalApplier(driver, profile, resume_path, settings, ask_ai, confirm_submit, log).run()
