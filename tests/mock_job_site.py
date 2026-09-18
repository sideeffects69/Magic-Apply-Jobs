"""
A small local website that behaves like a real employer's career portal, used to test
modules/external_apply.py without ever touching a real company's site.

It serves the job page, a login wall with a Google pop-up (the "Google" screens live on a
different hostname, `localhost`, while the site is on `127.0.0.1`, exactly like the real
accounts.google.com / company split), a Google button inside an iframe, a two-page form
with some fields already filled in, a resume upload that triggers the site's own
"autofill", a CAPTCHA page, and a question no profile can answer.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STYLE = "<style>body{font-family:sans-serif;margin:0}main{padding:20px;max-width:640px}label{display:block;margin-top:10px}" \
        ".hidden-file{display:none}.error{color:#b00}#cookie-banner{position:fixed;left:0;right:0;bottom:0;background:#222;color:#fff;padding:16px}</style>"

COOKIE = """<div id="cookie-banner" class="cookie-consent"><p>We use cookies.</p>
<button id="cookie-reject">Reject all</button> <button id="cookie-accept">Accept all</button></div>
<script>document.querySelectorAll('#cookie-banner button').forEach(b => b.onclick = () => document.getElementById('cookie-banner').remove());</script>"""

POPUP = ("window.open('http://localhost:%PORT%/google/accounts.html', 'googleauth', 'width=480,height=640')")

PAGES = {
    "/job.html": """<!doctype html><title>Senior Ad Ops - Acme</title>""" + STYLE + """
<header><input type="search" placeholder="Search jobs"> <a href="/about.html">About us</a></header>
<main><h1>Senior Ad Operations Manager</h1><p>Join Acme. Applications submitted: 12 so far.</p>
<a class="btn" id="apply" href="/login.html" target="_blank">Apply now</a>
<p><a href="/saved.html">Saved jobs</a> <a href="/status.html">Application status</a></p></main>""" + COOKIE,

    "/login.html": """<!doctype html><title>Sign in</title>""" + STYLE + """
<main><h1>Sign in to apply</h1>
<form onsubmit="return false"><label>Email <input type="email" id="lemail"></label>
<label>Password <input type="password" id="lpass"></label><button type="submit">Sign in</button></form>
<hr><button id="g" type="button"><img alt="Google" width="16" height="16" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="> Continue with Google</button>
<footer><a href="https://policies.google.com/privacy">Google privacy</a> <a href="/maps.html">Google Maps directions</a></footer></main>
<script>
document.getElementById('g').onclick = () => { """ + POPUP + """; };
window.addEventListener('message', e => { if (e.data === 'google-ok') location.href = '/apply.html'; });
</script>""",

    "/gsi-login.html": """<!doctype html><title>Sign in</title>""" + STYLE + """
<main><h1>Create your account</h1>
<label>Email <input type="email"></label><label>Password <input type="password"></label>
<iframe src="/gsi-button.html" title="Sign in with Google" width="300" height="60" style="border:0"></iframe></main>
<script>window.addEventListener('message', e => { if (e.data === 'google-ok') location.href = '/apply.html'; });</script>""",

    "/gsi-button.html": """<!doctype html><body style="margin:0"><div role="button" id="gsi" style="border:1px solid #888;padding:12px;cursor:pointer">Sign in with Google</div>
<script>document.getElementById('gsi').onclick = () => { """ + POPUP + """; };
window.addEventListener('message', e => { if (e.data === 'google-ok') window.top.location.href = '/apply.html'; });</script>""",

    "/google/accounts.html": """<!doctype html><title>Choose an account</title><body>
<h1>Choose an account</h1>
<div role="link" data-identifier="other@example.com" style="padding:12px;border:1px solid #ccc;cursor:pointer">Other Person other@example.com</div>
<div role="link" data-identifier="tester@example.com" id="me" style="padding:12px;border:1px solid #ccc;cursor:pointer">Test User tester@example.com</div>
<div style="padding:12px;cursor:pointer">Use another account</div>
<script>document.querySelectorAll('[data-identifier]').forEach(a => a.onclick = () => {
  fetch('/picked?account=' + encodeURIComponent(a.dataset.identifier));
  setTimeout(() => { window.opener && window.opener.postMessage('google-ok', '*'); window.close(); }, 200); });</script>""",

    "/google/password.html": """<!doctype html><title>Welcome</title><h1>Enter your password</h1><input type="password" id="pw">""",

    "/apply.html": """<!doctype html><title>Apply - personal information</title>""" + STYLE + """
<main><h1>Personal information</h1>
<form id="f1" novalidate>
<label>First name * <input id="first" name="first_name" required></label>
<label>Last name * <input id="last" name="last_name" required></label>
<label>Email * <input id="email" name="email" type="email" required value="tester@example.com"></label>
<label>Phone * <input id="phone" name="phone" type="tel" required value="000111"></label>
<label>City <input id="city" name="city"></label>
<label>LinkedIn profile <input id="linkedin" name="linkedin"></label>
<label>Attach your résumé <span>upload</span><input type="file" id="resume" name="resume" class="hidden-file"></label>
<p id="parsing" style="display:none">Parsing your resume...</p>
<p class="error" id="err"></p>
<button type="submit" id="next">Next</button></form></main>
<script>
const inp = document.getElementById('resume');
inp.onchange = () => {
  window.uploadedName = inp.files[0].name;
  document.getElementById('parsing').style.display = 'block';
  setTimeout(() => {                                   // the site's own resume autofill
    const first = document.getElementById('first'); if (!first.value) first.value = 'SiteParsedFirst';
    document.getElementById('parsing').style.display = 'none';
  }, 900);
};
document.getElementById('f1').onsubmit = (e) => {
  e.preventDefault();
  const missing = ['first', 'last', 'email', 'phone'].filter(id => !document.getElementById(id).value.trim());
  if (missing.length) { document.getElementById('err').textContent = 'Please complete: ' + missing.join(', '); return; }
  sessionStorage.setItem('page1', JSON.stringify({first_name: first.value, last_name: last.value, email: email.value, phone: phone.value,
    city: city.value, linkedin: linkedin.value, resume_name: window.uploadedName || ''}));
  location.href = '/apply2.html';
};
</script>""" + COOKIE,

    "/apply2.html": """<!doctype html><title>Apply - questions</title>""" + STYLE + """
<main><h1>Questions</h1>
<form id="f2" novalidate>
<label>Are you legally authorized to work in India? * <select id="auth" name="auth" required><option>Select...</option><option>Yes</option><option>No</option></select></label>
<fieldset><legend>Will you now or in the future require visa sponsorship? *</legend>
<label><input type="radio" name="sponsor" value="yes"> Yes</label><label><input type="radio" name="sponsor" value="no"> No</label></fieldset>
<label>Notice period <select id="notice" name="notice"><option>Select...</option><option>30 days</option><option selected>60 days</option></select></label>
<label>Gender <select id="gender" name="gender"><option>Select...</option><option>Male</option><option>Female</option><option>Decline to self-identify</option></select></label>
<label>Expected salary (annual) <input id="salary" name="salary" type="number"></label>
<label>Cover letter <textarea id="cover" name="cover"></textarea></label>
<label>Additional information <textarea id="extra" name="extra">Typed by the applicant, keep me.</textarea></label>
<label><input type="checkbox" id="privacy" name="privacy"> I agree to the Privacy Policy and Terms *</label>
<label><input type="checkbox" id="news" name="news"> Send me the newsletter</label>
<p class="error" id="err"></p>
<button type="submit" id="submit">Submit application</button></form></main>
<script>
document.getElementById('f2').onsubmit = (e) => {
  e.preventDefault();
  const f = document.getElementById('f2');
  const sponsor = (f.querySelector('input[name=sponsor]:checked') || {}).value || '';
  if (f.auth.selectedIndex < 1 || !sponsor || !f.privacy.checked) { document.getElementById('err').textContent = 'Please answer all required questions'; return; }
  const body = Object.assign(JSON.parse(sessionStorage.getItem('page1') || '{}'), {auth: f.auth.value, sponsor: sponsor,
    notice: f.notice.value, gender: f.gender.value, salary: f.salary.value, cover: f.cover.value, extra: f.extra.value,
    privacy: f.privacy.checked, news: f.news.checked});
  fetch('/submit', {method: 'POST', body: JSON.stringify(body)}).then(() => location.href = '/thanks.html');
};
</script>""",

    "/thanks.html": """<!doctype html><title>Thanks</title><main><h1>Thank you for applying!</h1><p>Your application has been submitted.</p></main>""",

    "/unknown-question.html": """<!doctype html><title>Apply</title>""" + STYLE + """
<main><h1>One more thing</h1><form id="f" novalidate>
<label>First name * <input name="first_name" required></label>
<label>Do you have experience with Kubernetes? * <input id="k8s" name="k8s" required></label>
<p class="error" id="err"></p><button type="submit">Submit application</button></form></main>
<script>document.getElementById('f').onsubmit = (e) => { e.preventDefault();
 if (!k8s.value) { err.textContent = 'required'; return; }
 fetch('/submit', {method: 'POST', body: JSON.stringify({k8s: k8s.value})}).then(() => location.href = '/thanks.html'); };</script>""",

    "/captcha.html": """<!doctype html><title>Verify</title><main><h1>Please verify</h1>
<iframe src="/recaptcha/api2/anchor?ar=1&k=test" title="reCAPTCHA" width="304" height="78"></iframe></main>""",

    "/recaptcha/api2/anchor": """<!doctype html><body><div style="padding:20px;border:1px solid #999">I'm not a robot</div>""",

    "/no-google-login.html": """<!doctype html><title>Sign in</title>""" + STYLE + """
<main><h1>Create an account to apply</h1><form onsubmit="return false"><label>Email <input type="email"></label>
<label>Password <input type="password"></label><label>Confirm password <input type="password"></label>
<button type="submit">Create account</button></form></main>""",

    "/embed.html": """<!doctype html><title>Careers - Acme</title>""" + STYLE + """
<header><h1>Acme careers</h1></header>
<iframe src="/apply.html" title="Application form" width="900" height="1000" style="border:0"></iframe>""",

    "/styled.html": """<!doctype html><title>Apply</title>""" + STYLE + """
<style>.sr{position:absolute;opacity:0;width:1px;height:1px}.pill{display:inline-block;border:1px solid #888;padding:8px 14px;margin:4px;cursor:pointer}</style>
<main><h1>Quick questions</h1><form id="f" novalidate>
<fieldset><legend>Will you now or in the future require visa sponsorship? *</legend>
<label class="pill"><input type="radio" name="sponsor" value="yes" class="sr"><span>Yes</span></label>
<label class="pill"><input type="radio" name="sponsor" value="no" class="sr"><span>No</span></label></fieldset>
<label class="pill"><input type="checkbox" id="privacy" class="sr"><span>I agree to the Privacy Policy *</span></label>
<p class="error" id="err"></p><button type="submit" id="submit">Submit application</button></form></main>
<script>document.getElementById('f').onsubmit = (e) => { e.preventDefault();
 const sponsor = (document.querySelector('input[name=sponsor]:checked') || {}).value || '';
 if (!sponsor || !privacy.checked) { err.textContent = 'Please answer all required questions'; return; }
 fetch('/submit', {method: 'POST', body: JSON.stringify({sponsor: sponsor, privacy: privacy.checked})}).then(() => location.href = '/thanks.html'); };</script>""",

    "/login-password.html": """<!doctype html><title>Sign in</title>""" + STYLE + """
<main><h1>Sign in to apply</h1><form onsubmit="return false"><label>Email <input type="email"></label>
<label>Password <input type="password"></label></form>
<button id="g" type="button">Continue with Google</button></main>
<script>document.getElementById('g').onclick = () => { window.open('http://localhost:%PORT%/google/password.html', 'googleauth', 'width=480,height=640'); };</script>""",

    "/job-newsletter.html": """<!doctype html><title>Ad Ops Manager - Acme</title>""" + STYLE + """
<div class="hero-banner"><p>We are hiring!</p><button id="hero-continue" onclick="fetch('/event?name=hero-clicked')">Continue</button></div>
<main><h1>Ad Ops Manager</h1>
<form id="news" onsubmit="return false"><label>Get job alerts: <input type="email" id="newsletter" oninput="fetch('/event?name=newsletter-typed')"></label><button>Subscribe</button></form>
<a id="apply" href="/apply.html">Apply now</a></main>""",

    "/faq.html": """<!doctype html><title>Careers FAQ</title><main><h1>Careers FAQ</h1>
<p>Once your application has been submitted you will receive an email. We have received your application volume is high.</p></main>""",

    "/silent-submit.html": """<!doctype html><title>Apply</title>""" + STYLE + """
<main><h1>Apply</h1><form onsubmit="return false"><label>First name * <input name="first_name" required value="Asha"></label>
<button type="submit" id="go" onclick="fetch('/event?name=submit-click')">Submit application</button></form></main>""",

    "/blank.html": """<!doctype html><title>Nothing here</title><main><h1>Company news</h1><p>No jobs on this page.</p></main>""",
}


class MockSite:
    '''Runs the mock site on a free local port and records what the applicant submitted.'''

    def __init__(self):
        self.submissions = []
        self.google_picks = []
        self.events = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, body: bytes, status=200, content_type="text/html; charset=utf-8"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/event":
                    outer.events.append(self.path.split("name=")[-1])
                    return self._send(b"ok", content_type="text/plain")
                if path == "/picked":
                    outer.google_picks.append(self.path.split("account=")[-1].replace("%40", "@"))
                    return self._send(b"ok", content_type="text/plain")
                page = PAGES.get(path)
                if page is None:
                    return self._send(b"not found", 404, "text/plain")
                self._send(page.replace("%PORT%", str(outer.port)).encode("utf-8"))

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                if self.path == "/submit":
                    try:
                        outer.submissions.append(json.loads(raw.decode("utf-8")))
                    except ValueError:
                        outer.submissions.append({"_raw": raw.decode("utf-8", "replace")})
                self._send(b"{}", content_type="application/json")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def reset(self):
        self.submissions.clear()
        self.google_picks.clear()
        self.events.clear()
