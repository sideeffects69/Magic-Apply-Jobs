'''
Author:     Om Abhyankar
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

Entry point of the portable MagicApply.exe (it also works from source: `python magic_apply.py`).

  MagicApply.exe               starts the control panel and opens it in your browser
  MagicApply.exe --run-bot     runs the job-applying bot (the panel starts this itself when you click Start)
  MagicApply.exe --selftest    checks that everything the exe needs is inside it, then exits
'''

import importlib.util
import multiprocessing
import os
import sys


def _selftest() -> int:
    results = []

    def check(name, function):
        try:
            function()
            results.append((name, True, ""))
        except Exception as error:
            results.append((name, False, f"{type(error).__name__}: {error}"))

    def panel_and_templates():
        import app
        for template in ("control_panel.html", "index.html", "failures.html"):
            app.app.jinja_env.get_template(template)

    def company_site_applier():
        from modules import external_apply, form_profile
        assert form_profile.decide(form_profile.FieldInfo("text", "First name"), form_profile.Profile(first_name="Asha")).value == "Asha"
        assert external_apply.ExternalSettings().max_steps > 0

    def browser_automation():
        import selenium.webdriver
        import undetected_chromedriver  # noqa: F401
        import pyautogui, tkinter  # noqa: F401,E401  (pause dialogs)

    def ai_providers():
        from langchain.chat_models import init_chat_model
        init_chat_model("gpt-4o-mini", model_provider="openai", api_key="self-test")
        init_chat_model("gemini-2.0-flash", model_provider="google_genai", api_key="self-test")
        import modules.ai.connections  # noqa: F401

    def bot_is_bundled():
        assert importlib.util.find_spec("runAiBot") is not None, "runAiBot is missing from the bundle"

    def data_folder_is_private():
        from config import _overrides
        assert "AutoJobApplier" in _overrides.DATA_DIR

    check("control panel + its pages", panel_and_templates)
    check("company-site applier", company_site_applier)
    check("Selenium / Chrome driver / dialogs", browser_automation)
    check("AI providers (OpenAI, Gemini)", ai_providers)
    check("bot module bundled", bot_is_bundled)
    check("private data folder", data_folder_is_private)

    for name, ok, detail in results:
        print(("OK    " if ok else "FAIL  ") + name + (f"  ({detail})" if detail else ""))
    return 0 if all(ok for _, ok, _ in results) else 1


def main() -> int:
    multiprocessing.freeze_support()
    args = sys.argv[1:]
    if "--selftest" in args:
        return _selftest()
    if "--run-bot" in args:
        sys.argv = [sys.argv[0]] + [a for a in args if a != "--run-bot"]
        import runAiBot                       # opens Chrome as it loads, like `python runAiBot.py`
        runAiBot.main()
        return 0
    os.environ.setdefault("PANEL_OPEN_BROWSER", "1")
    import app
    app.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
