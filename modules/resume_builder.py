'''
License:    MIT License
            https://opensource.org/license/mit
GitHub:     https://github.com/sideeffects69

Turns your resume data (name, work history, education, skills - entered in
the control panel's Resume Builder tab) into a clean, ATS-friendly PDF using
RenderCV (https://github.com/rendercv/rendercv), an open-source resume
typesetter that renders plain single-column PDFs with a real, parseable text
layer - the format ATS parsers read most reliably.

The YAML source lives in the OS's per-user app data folder alongside
user_config.json (see config/_overrides.py) - deliberately OUTSIDE this
project folder, since it's personal data (your name, employer, experience)
and this project gets copied, renamed, zipped and shared.

This is optional: the job applier itself never imports this module. It's only
used by the "Generate ATS Resume" button in the control panel (see app.py).
Requires `pip install -r requirements-resume.txt` (Python 3.12+).
'''

import os
import subprocess
import sys
from glob import glob

from config._overrides import DATA_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESUME_YAML_PATH = os.path.join(DATA_DIR, "resume_data.yaml")
_LEGACY_RESUME_YAML_PATH = os.path.join(ROOT, "config", "resume_data.yaml")
RESUME_OUTPUT_DIR = os.path.join(DATA_DIR, "all resumes", "default")


def _migrate_legacy_resume_yaml() -> None:
    '''One-time migration from the old in-project location - see config/_overrides.py for why.'''
    if os.path.exists(RESUME_YAML_PATH) or not os.path.exists(_LEGACY_RESUME_YAML_PATH):
        return
    try:
        os.makedirs(os.path.dirname(RESUME_YAML_PATH), exist_ok=True)
        with open(_LEGACY_RESUME_YAML_PATH, "r", encoding="utf-8") as src:
            content = src.read()
        with open(RESUME_YAML_PATH, "w", encoding="utf-8") as dst:
            dst.write(content)
        os.remove(_LEGACY_RESUME_YAML_PATH)
    except OSError:
        pass


_migrate_legacy_resume_yaml()


def is_available() -> bool:
    '''True if RenderCV is importable, i.e. `requirements-resume.txt` was installed.'''
    try:
        import rendercv  # noqa: F401
        return True
    except ImportError:
        return False


def generate_ats_resume() -> tuple[bool, str]:
    '''
    Renders `resume_data.yaml` (in the per-user data folder) into a PDF under `all resumes/default/` there.
    Returns `(success, message)` - on success, `message` is the absolute path
    to the generated PDF; on failure, a human-readable explanation.
    '''
    if not is_available():
        return False, (
            "RenderCV isn't installed. Run `pip install -r requirements-resume.txt` "
            "(needs Python 3.12+), then try again."
        )
    if not os.path.exists(RESUME_YAML_PATH):
        return False, "No resume data found yet. Fill in the Resume Builder tab and save first."

    os.makedirs(RESUME_OUTPUT_DIR, exist_ok=True)
    before = set(glob(os.path.join(RESUME_OUTPUT_DIR, "*.pdf")))

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # RenderCV writes UTF-8 (checkmarks, box-drawing) regardless of the console's codepage
    try:
        result = subprocess.run(
            [sys.executable, "-m", "rendercv", "render", RESUME_YAML_PATH,
             "--output-folder", RESUME_OUTPUT_DIR,
             "--dont-generate-markdown", "--dont-generate-html", "--dont-generate-png"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=120, env=env,
        )
    except FileNotFoundError:
        return False, "RenderCV isn't installed. Run `pip install -r requirements-resume.txt`."
    except subprocess.TimeoutExpired:
        return False, "Resume rendering timed out after 2 minutes."

    after = set(glob(os.path.join(RESUME_OUTPUT_DIR, "*.pdf")))
    new_or_updated = after - before or after
    if result.returncode != 0 or not new_or_updated:
        detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        return False, f"RenderCV couldn't generate the resume:\n{detail[-2000:]}"

    output_pdf = max(new_or_updated, key=os.path.getmtime)
    return True, output_pdf
