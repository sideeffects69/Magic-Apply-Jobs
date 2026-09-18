# Magic Apply - Jobs 🤖

A free, open-source tool that automates job applications. It runs entirely on your own computer, using your own LinkedIn account. It finds jobs relevant to you on LinkedIn, applies with Easy Apply, and - for every other job - **opens the company's own application site, signs in with Google when the site asks you to, fills the form from your resume and details, and submits it.** It can also tailor answers to each job with AI.

Maintained by **Om Abhyankar** · https://github.com/sideeffects69

## ✨ Content
- [Easy start (recommended)](#-easy-start-recommended)
- [Portable exe (no install)](#-portable-exe-no-install)
- [Applying on company websites](#-applying-on-company-websites)
- [Your data: nothing is kept (backup and restore)](#-your-data-nothing-is-kept-backup-and-restore)
- [Manual install](#%EF%B8%8F-manual-install)
- [Manual configuration](#-manual-configuration)
- [Disclaimer](#-disclaimer)
- [Terms and Conditions](#%EF%B8%8F-terms-and-conditions)
- [License](#%EF%B8%8F-license)

<br>

## 🚀 Easy start (recommended)

New here, or not comfortable editing code? Use the built-in control panel. You set everything up in your web browser and run the tool with a button - no editing Python files, no terminal commands.

1. **Download this project** (green "Code" button → "Download ZIP", then unzip; or clone it).
2. **Double-click the launcher for your system:**
    - **Windows:** `start.bat`
    - **macOS:** `start.command`
    - **Linux:** `start.sh` (run `./start.sh` in a terminal)

    **On Windows, `start.bat` checks your computer and installs anything that is missing - Python 3.12, Google Chrome and all the tool's packages - so there is nothing to install by hand.** The first run can take a few minutes; after that it starts in seconds. (On macOS and Linux, install [Python 3.10+](https://www.python.org/downloads/) and [Google Chrome](https://www.google.com/chrome) first; the launcher does the rest.)
3. Your browser opens the **control panel** automatically (the exact address, e.g. `http://127.0.0.1:5000`, is shown in the launcher window). If you saved a backup file last time, click **Restore from backup** and everything fills back in. Otherwise fill in the tabs - **Account, Profile, Search, Filters, Run settings** - and click **Save**.
4. Go to the **Run** tab and click **Start**. A Chrome window opens and begins applying - keep it in the foreground. You can watch progress in the log and click **Stop** any time.
5. When you're done, click **Download backup** (if you want to keep your details), then **Finish & erase**.

The control panel is reachable only from your own computer, and it refuses requests coming from other websites.

[back to index](#-content)

<br>

## 📦 Portable exe (no install)

Prefer one file you can copy to any Windows PC? Build it once and share it:

1. On a PC that already ran `start.bat`, double-click **`build_exe.bat`**. It takes a few minutes and produces **`dist\MagicApply.exe`**.
2. Copy that single file anywhere (a USB stick, another PC) and double-click it. It opens the control panel in your browser - no Python, no installer. It only needs **Google Chrome** on the PC.
3. Behaviour is identical to `start.bat`: your data is erased when you close the window, so use **Download backup** first if you want to keep it.

The exe is not code-signed, so Windows SmartScreen may say "Windows protected your PC" the first time: click *More info* then *Run anyway*. Because it can drive a browser it is sometimes flagged by antivirus programs; if yours complains, build it yourself with `build_exe.bat` so you know exactly what is inside.

`MagicApply.exe --selftest` checks that everything the exe needs is bundled.

[back to index](#-content)

<br>

## 🌐 Applying on company websites

Most jobs on LinkedIn are not Easy Apply - they send you to the employer's own site. In **Search**, turn **Easy Apply only** off (it is off by default) and the tool handles those too:

1. **Opens the company's application page** from the LinkedIn job.
2. **Signs in with Google if the site asks.** It looks for a "Sign in / Sign up / Continue with Google" button (on the page, in a pop-up, or inside Google's own frame), clicks it, and picks your Google account (set it in **Account → Google account for company sites**). If your browser is already signed in to Google this is automatic.
3. **Uploads your resume first**, so the site's own resume-autofill runs.
4. **Fills only what is still empty.** A field the site already filled, or that you typed, is never replaced - not by the tool and not by your profile.
5. **Clicks Next / Continue / Submit** page after page and stops when the site confirms the application.

It is deliberately cautious:

- **It never submits with a required question empty**, and it **never invents an answer**. A question it can't answer from your profile goes to the AI (if you turned that on); otherwise it waits for you in the browser window (**Run settings → Wait for me on hard steps**), and if you don't answer in time the job is saved to the **Failed jobs** list with the reason and a screenshot - never submitted half-empty.
- **It never types a Google password, and never gets past a CAPTCHA or 2-step verification.** Those are left to you: the tool waits, you finish that screen in the browser, and it carries on.
- Marketing opt-ins ("send me the newsletter") are left unticked; privacy/terms consent boxes are ticked.
- Your name, email and phone must be set first (Profile tab). The template placeholders (`First`, `123 Main Street`, ...) are never sent to an employer.
- If LinkedIn's daily Easy Apply cap is reached, the tool carries on with company-site jobs instead of stopping.

**Honest limits.** Career sites are all different. The tool works on ordinary forms (including forms inside iframes, styled radio buttons and multi-page flows), but some will always need you: sites that force an email-and-password account with no Google option, heavily custom dropdowns, CAPTCHAs, and file-upload-only steps. Those end up in the Failed jobs list with the company's link so you can finish them by hand. It has been tested against realistic local mock sites, not against every employer on the internet - watch the first few runs.

[back to index](#-content)

<br>

## 🔒 Your data: nothing is kept (backup and restore)

**This tool does not remember anything between sessions.** Everything you enter - settings, LinkedIn login, resume text, uploaded resumes, applied-jobs history - exists only while the control panel is open, and is **erased when you close it**. Whoever opens the tool next starts completely fresh.

To keep your details, use the bar at the top of the control panel:

- **Download backup** saves everything into one file (`AutoJobApplier-backup-<date>.json`). Untick *Include passwords & API keys* if you would rather retype them next time - the file is then free of secrets. A backup with passwords in it is as sensitive as the passwords themselves, so keep it somewhere private.
- **Restore from backup** loads that file next time and every field fills back in - settings, resume text, resume files and applied-jobs history (which also keeps the daily application cap accurate).
- **Finish & erase** offers a backup, then erases everything and closes the tool. Closing the launcher window, pressing Ctrl+C or logging off does the same erase - so if you don't save a backup, your data is gone.

What a backup contains: settings, resume text, uploaded/generated resume files, applied-jobs history. It does not contain the failed-jobs list, logs, screenshots or the browser profile.

**Where it lives while the tool is open:** in a private per-user folder, never inside the project folder, so you can zip, copy or share the project without any of your data going along:

| System | Folder |
|--------|--------|
| Windows | `%LOCALAPPDATA%\AutoJobApplier` |
| macOS | `~/Library/Application Support/AutoJobApplier` |
| Linux | `~/.config/AutoJobApplier` |

A relative resume path such as `all resumes/default/resume.pdf` is looked up inside that folder; you can also give a full path to a file anywhere on your computer. The tool's own Chrome guest profile (safe mode) lives there too and is erased with the rest. If you are *not* in safe mode, the tool uses your normal Chrome profile, and your LinkedIn login stays in Chrome itself - the tool never erases that.

**For developers:** set the environment variable `AUTOJOBAPPLIER_KEEP_DATA=1` before starting the tool to switch the erase off while you work on it. The panel shows a "Keep-data mode is on" notice when it is active. If the tool crashes, leftover data can remain until you next open the panel - use **Finish & erase** to clear it.

[back to index](#-content)

<br>

## ⚙️ Manual install

Only needed if you don't use the launchers above.

1. Install [Python 3.10](https://www.python.org/downloads/) or above and make sure it is added to PATH.
2. Install [Google Chrome](https://www.google.com/chrome).
3. In a terminal, in the project folder, install the packages:
    ```
    pip install -r requirements.txt
    ```
4. Chrome Driver is downloaded automatically (`auto_manage_driver = True` in `config/settings.py`). If you turn that off, download the [Chrome Driver](https://googlechromelabs.github.io/chrome-for-testing/) matching your Chrome version and place it where Chrome is installed, or run `windows-setup.bat` from the `/setup` folder on Windows.

[back to index](#-content)

<br>

## 🔧 Manual configuration

Prefer editing files to using the control panel? The `/config` folder holds the defaults:

1. `personals.py` - your name, phone number, address, etc.
2. `questions.py` - your answers for application questions, and whether the bot should pause before submitting or when it can't answer a question.
3. `search.py` - search terms, job filters, and rules for which jobs to apply for or skip.
4. `secrets.py` - your LinkedIn username and password and an optional AI API key. Leave the username and password blank to use the browser's saved login, or log in by hand when asked.
5. `settings.py` - keep screen awake, click interval, run in background, automatic Chrome-driver management, and the daily application cap.

Then run `runAiBot.py`. To open the control panel instead (settings, run controls, applied-jobs history), run `app.py` - it prints the address to open.

> The `/config/*.py` files are generic templates. Anything you save in the control panel lives only for that session (see above) and overrides them, so **never put real personal details in these files** if you plan to share the project.

**Resume Builder (optional):** don't have an ATS-friendly resume? Open the control panel's **Resume Builder** tab, fill in your experience, education and skills as YAML, and click **Generate ATS Resume** to get a clean, single-column PDF (built with the open-source [RenderCV](https://github.com/rendercv/rendercv)). It needs `pip install -r requirements-resume.txt` (Python 3.12+); `start.bat` installs it for you when it can.

[back to index](#-content)

<br>

## 📜 Disclaimer

**This tool runs on your own computer and acts through your own accounts. It is provided free and open source, with no warranty of any kind. You are responsible for how you use it, including making sure your use complies with the terms of any website or service you use it with. The authors and contributors accept no liability for how it is used.**


## 🏛️ Terms and Conditions

Please consider the following:

- **LinkedIn Policies**: LinkedIn has policies regarding automated activity on its platform. It is your responsibility to review and comply with them before using this tool with your account.

- **No Warranties or Guarantees**: This program is provided as-is, without any warranties or guarantees of any kind. The accuracy, reliability, and effectiveness of the program cannot be guaranteed. Use it at your own risk.

- **Disclaimer of Liability**: The creators and contributors of this program shall not be held responsible or liable for any damages or consequences arising from the direct or indirect use, interaction, or actions performed with this program. This includes but is not limited to any legal issues, loss of data, or other damages incurred.

- **Use at Your Own Risk**: It is important to exercise caution and ensure that your usage, interactions, and actions with this program comply with applicable laws, regulations, and the terms of the services you use it with.

- **Chrome Driver**: This program uses the Chrome Driver to control your browser. Please review and comply with the terms and conditions specified for [Chrome Driver](https://chromedriver.chromium.org/home).


## ⚖️ License

Copyright (c) 2026 Om Abhyankar

This project is licensed under the **MIT License**. You are free to use, copy, modify, and distribute it - including in commercial and closed-source work - as long as the copyright notice and permission notice are preserved. It is provided "as is", without warranty of any kind.

Parts of this project build on earlier MIT-licensed work; that work's copyright notice is preserved in the [`LICENSE`](LICENSE) file, as the MIT License requires.

<br>

[back to index](#-content)

---

[back to the top](#linkedin-ai-auto-job-applier-)
