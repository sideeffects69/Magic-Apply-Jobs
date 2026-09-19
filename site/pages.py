"""
The pages of the website and everything search engines read about them.

One place holds each page's title, description, dates, related pages and FAQ, so the visible text, the structured data,
the navigation, the sitemap and the HTML site map can never drift apart. `build.py` turns this into `docs/`.
"""

SITE_URL = "https://sideeffects69.github.io/Magic-Apply-Jobs/"
REPO_URL = "https://github.com/sideeffects69/Magic-Apply-Jobs"
RELEASES_URL = REPO_URL + "/releases"
SITE_NAME = "Magic Apply - Jobs"
VERSION = "1.0.0-beta.2"
OG_IMAGE = SITE_URL + "og-image.png"
PUBLISHED = "2026-09-19"
LINKEDIN_PROHIBITED = "https://www.linkedin.com/help/linkedin/answer/a1341387"
LINKEDIN_AUTOMATED = "https://www.linkedin.com/help/linkedin/answer/a1340567"
LINKEDIN_RESTRICTED = "https://www.linkedin.com/help/linkedin/answer/a1340522"

# ---------------------------------------------------------------------------
# Questions and answers. Each id can be shown on any page; the same text feeds the visible FAQ and the FAQPage data.
# ---------------------------------------------------------------------------
FAQ = {
    "free": ("Is Magic Apply - Jobs really free?",
             "Yes. It is free and open source under the MIT License, with no account, subscription or paid tier. You can read, change and share the code."),
    "what": ("What is Magic Apply - Jobs?",
             "It is a free, open-source program that runs on your own computer. It searches LinkedIn with your own account, applies with Easy Apply, and for jobs that send you to a company's own website it opens the application, signs in with Google if the site asks, and fills in the form from your details."),
    "extension": ("Is it a Chrome extension?",
                  "No. It is a program that runs on your computer and controls a Chrome window, with a control panel that opens in your browser. Nothing is installed into Chrome, and there is no cloud service or account."),
    "any-site": ("Will it work on any company website?",
                 "It handles ordinary application forms, including multi-page flows and forms inside iframes. Some sites will always need you: those that force an email-and-password account with no Google option, CAPTCHAs, and heavily custom questions. Anything it cannot finish is saved to a Failed jobs list with the reason and the company's link. So far it has been tested against realistic local mock sites, not every employer, so treat it as a beta and watch the first few runs."),
    "ats": ("Does it work with Workday, Greenhouse or Lever?",
            "We have not verified it against specific applicant tracking systems, so we do not claim support for any of them. Forms that are a single public page are the easiest case. Some systems, such as Workday, commonly ask you to create an account for each employer; if a site has no Google sign-in option, the tool leaves the job for you and saves it, with the link, to the Failed jobs list."),
    "safe": ("Is it safe for my LinkedIn account?",
             "LinkedIn has rules about automated activity, and it may limit or restrict accounts that break them. You use the tool at your own risk. Keep the daily cap low, watch your first runs and read the disclaimer before you start."),
    "per-day": ("How many jobs can it apply to per day?",
                "You choose. The daily cap is 40 by default and you can change it in Run settings, or set it to -1 for no cap. LinkedIn has not published an official Easy Apply limit, but many people report being blocked after roughly 50 Easy Apply submissions in 24 hours, so a cap below that is sensible."),
    "limit": ("What happens when LinkedIn's Easy Apply limit is reached?",
              "The tool notices LinkedIn's limit message. If company-website applying is on, it carries on with jobs that apply on company sites and skips Easy Apply jobs for the rest of the run. If it is off, it stops and tells you to resume tomorrow."),
    "data": ("Does it store or upload my personal data?",
             "No. It runs on your own computer, keeps your details in a private folder only while it is open, and erases them when you close it. If you turn on the optional AI answers, the question, the job description and the about-me text you wrote are sent to the AI provider you choose. Otherwise nothing leaves your computer except the applications themselves."),
    "google": ("Does it type my Google password or solve CAPTCHAs?",
               "No. It never types a Google password and never gets past a CAPTCHA or 2-step verification. When Google or a site asks for one, the tool waits while you finish that screen in the browser window, then carries on."),
    "review": ("Does it submit applications without me checking?",
               "Only if you allow it. Pause before submitting is on by default, so the tool stops before each submission for you to review. Turn it off in Run settings for hands-free running. It never submits with a required question empty and never invents an answer."),
    "ai": ("Can it answer screening questions with AI?",
           "Yes, optionally. Add an API key for OpenAI, Gemini or DeepSeek in the Account tab and turn on AI answers. It is off by default. When it is on, the question, the job description and the about-me text you wrote are sent to the provider you chose."),
    "need": ("What do I need to run it?",
             "Google Chrome. The Windows .exe needs nothing else. On Windows the start.bat launcher also installs Python and Chrome if they are missing. On macOS and Linux, install Python 3.10 or newer and Chrome first, then double-click the launcher; those two launchers are included but less tested than the Windows ones."),
    "smartscreen": ("Windows says it protected my PC. Is the file safe?",
                    "The .exe is not code-signed, so Windows SmartScreen shows a warning the first time. Click More info, then Run anyway. You can compare the file's SHA-256 with the one on the release page, or build the exe yourself from the source with build_exe.bat. Some antivirus programs flag anything that drives a browser."),
    "report": ("How do I report a problem?",
               "Click Download report in the control panel before you close it. It saves a text file with your recent log and why jobs failed, with your name, email, phone, passwords and links masked. Read it, then attach it to an issue on GitHub."),
    "code": ("Do I need to know how to code?",
             "No. You set everything up in a control panel that opens in your browser and run the tool with a button. There are no code files to edit."),
    "stop": ("Can I stop it at any time?",
             "Yes. Click Stop in the Run tab. Anything it has already applied for stays recorded in the Applied jobs list for that session, and jobs it could not finish are in the Failed jobs list."),
    "setup-time": ("How long does setup take?",
                   "A few minutes with the Windows .exe. The launcher's first run can take longer because it installs the tool's packages; after that it starts in seconds. Filling in your profile takes about as long as one job application."),
    "premium": ("Does LinkedIn Premium remove the Easy Apply limit?",
                "People consistently report that it does not: the limit is reported to apply to every account type. LinkedIn has not published details, so treat this as a report rather than a rule."),
    "reset": ("Does the Easy Apply limit reset at midnight?",
              "Reports say it resets on a rolling 24-hour basis rather than at midnight in your time zone. LinkedIn has not published details, so if you are blocked, the safest plan is to wait a full day."),
    "after-limit": ("Can I still apply for jobs after reaching the limit?",
                    "Yes, on the employer's own website. The limit is reported to apply to Easy Apply submissions, so jobs that send you to a company site are not affected. That is why Magic Apply - Jobs carries on with company-site jobs when it sees the limit."),
    "banned": ("Can I get banned for using an auto apply tool?",
               "Yes, it is possible. LinkedIn's rules prohibit third-party software that automates activity on its site, and it says members who break them risk having their accounts restricted or shut down. No tool, this one included, can make that risk zero. Keeping volume modest and reviewing your first runs lowers it but does not remove it."),
    "mac": ("Does it work on Mac and Linux?",
            "There are launchers for both (start.command and start.sh) and the code is cross-platform, but the maintainers test on Windows, so the macOS and Linux launchers are less tested. The portable .exe is Windows only."),
    "backup": ("How do I keep my settings between sessions?",
               "Click Download backup before you close the tool, and Restore from backup next time. Nothing is kept otherwise: the tool erases your details when it closes. Restoring your backup also lets it count the applications you already made today, so the daily cap stays accurate."),
}

# ---------------------------------------------------------------------------
# Pages. `slug` is the folder under docs/ ("" is the home page). `related` are the guides shown at the foot of a page.
# ---------------------------------------------------------------------------
PAGES = [
    {
        "slug": "", "content": "home", "kind": "home",
        "title": "Magic Apply - Jobs: Free Open-Source Job Application Bot",
        "description": "Free, open-source tool that finds jobs on LinkedIn, applies with Easy Apply and fills in company career-site forms for you. Runs on your PC and keeps no data.",
        "nav": "Home", "crumb": "Home", "updated": "2026-09-19",
        "faq": ["free", "any-site", "safe", "data", "google", "need", "smartscreen", "report"],
        "faq_more": True,
    },
    {
        "slug": "how-to-auto-apply-on-linkedin", "content": "how-to", "kind": "guide",
        "title": "How to Auto Apply on LinkedIn: Free Step-by-Step Setup",
        "description": "Set up a free, open-source LinkedIn auto apply tool in minutes: download it, fill in your profile, pick your search and click Start. No coding needed.",
        "nav": "How to", "crumb": "How to auto apply on LinkedIn", "updated": "2026-09-19",
        "h1": "How to auto apply on LinkedIn (free, step by step)",
        "lede": "This guide takes you from download to your first supervised run with Magic Apply - Jobs, a free open-source tool that runs on your own computer. You do not edit any code.",
        "faq": ["code", "setup-time", "stop", "need"],
        "related": ["is-linkedin-auto-apply-safe", "linkedin-easy-apply-limit", "apply-on-company-websites"],
    },
    {
        "slug": "linkedin-easy-apply-limit", "content": "easy-apply-limit", "kind": "guide",
        "title": "LinkedIn Easy Apply Limit (2026): How Many Per Day?",
        "description": "What people report about LinkedIn's daily Easy Apply limit, what happens when you reach it, and how to keep going by applying on company sites.",
        "nav": "Easy Apply limit", "crumb": "LinkedIn Easy Apply limit", "updated": "2026-09-19",
        "h1": "LinkedIn Easy Apply limit: how many applications per day?",
        "lede": "LinkedIn stops accepting Easy Apply submissions once you have sent too many in a day. Here is what people report about the limit, what to do when you hit it, and how Magic Apply - Jobs handles it.",
        "faq": ["per-day", "limit", "premium", "reset", "after-limit"],
        "related": ["is-linkedin-auto-apply-safe", "apply-on-company-websites", "how-to-auto-apply-on-linkedin"],
    },
    {
        "slug": "is-linkedin-auto-apply-safe", "content": "safe", "kind": "guide",
        "title": "Is LinkedIn Auto Apply Safe? Risks and How to Lower Them",
        "description": "LinkedIn's rules ban tools that automate activity on its site. Here is the real risk to your account, what raises it, and how to keep your use modest.",
        "nav": "Safety", "crumb": "Is LinkedIn auto apply safe?", "updated": "2026-09-19",
        "h1": "Is LinkedIn auto apply safe? The risks, plainly",
        "lede": "Short answer: not risk-free. LinkedIn's rules prohibit tools that automate activity on its site, and it says accounts that use them can be restricted or shut down. Here is what that means and how to keep your use modest.",
        "faq": ["banned", "safe", "review", "per-day"],
        "related": ["linkedin-easy-apply-limit", "how-to-auto-apply-on-linkedin", "free-linkedin-auto-apply-tools"],
    },
    {
        "slug": "apply-on-company-websites", "content": "company-sites", "kind": "guide",
        "title": "Auto Apply on Company Career Sites: How It Works",
        "description": "Most LinkedIn jobs send you to the employer's own site. See how Magic Apply - Jobs opens it, signs in with Google and fills the form, and where it stops.",
        "nav": "Company sites", "crumb": "Applying on company websites", "updated": "2026-09-19",
        "h1": "Auto apply on company career sites: how it works",
        "lede": "Most jobs on LinkedIn are not Easy Apply. They send you to the employer's own application page, and that is where most tools stop. Here is what Magic Apply - Jobs does there, and where it hands over to you.",
        "faq": ["any-site", "ats", "google", "review"],
        "related": ["linkedin-easy-apply-limit", "is-linkedin-auto-apply-safe", "how-to-auto-apply-on-linkedin"],
    },
    {
        "slug": "free-linkedin-auto-apply-tools", "content": "free-tools", "kind": "guide",
        "title": "Free LinkedIn Auto Apply Tools: Open Source vs Extensions",
        "description": "Compare the kinds of LinkedIn auto apply tools: subscription services, browser extensions and free open-source programs, with honest trade-offs for each.",
        "nav": "Free tools", "crumb": "Free LinkedIn auto apply tools", "updated": "2026-09-19",
        "h1": "Free LinkedIn auto apply tools: open source vs extensions",
        "lede": "Auto apply tools come in a few kinds, and the differences matter more than the brand names. Here is how they compare on cost, where your data goes, setup effort and limits, including where a free open-source tool is the weaker choice.",
        "faq": ["free", "extension", "data", "mac"],
        "related": ["is-linkedin-auto-apply-safe", "how-to-auto-apply-on-linkedin", "apply-on-company-websites"],
    },
    {
        "slug": "faq", "content": "faq", "kind": "faq",
        "title": "Magic Apply - Jobs FAQ: Safety, Limits, Data and Setup",
        "description": "Answers about Magic Apply - Jobs: cost, LinkedIn account safety, daily limits, company websites, your data, AI answers, setup and reporting problems.",
        "nav": "FAQ", "crumb": "FAQ", "updated": "2026-09-19",
        "h1": "Frequently asked questions",
        "lede": "Straight answers about what the tool does, what it does not do, and what it costs you in risk, time and data.",
        "faq": ["what", "free", "extension", "safe", "banned", "per-day", "limit", "after-limit", "any-site", "ats", "review", "google", "ai", "data",
                "need", "mac", "smartscreen", "backup", "code", "report"],
        "related": ["how-to-auto-apply-on-linkedin", "is-linkedin-auto-apply-safe", "free-linkedin-auto-apply-tools"],
    },
    {
        "slug": "sitemap", "content": None, "kind": "sitemap",
        "title": "Site Map - Magic Apply - Jobs",
        "description": "Every page on the Magic Apply - Jobs website in one list: the guides, the FAQ and where to download the free open-source LinkedIn auto apply tool.",
        "nav": "Site map", "crumb": "Site map", "updated": "2026-09-19",
        "h1": "Site map",
        "lede": "Every page on this site, and where to find the tool itself.",
        "faq": [], "related": [],
    },
]

BY_SLUG = {page["slug"]: page for page in PAGES}


def url(slug: str) -> str:
    return SITE_URL + (slug + "/" if slug else "")
