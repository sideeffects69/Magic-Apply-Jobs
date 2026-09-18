"""
Guards the privacy guarantee: nothing personal (history, logs, resumes, browser
profile) is ever written inside the project folder, so sharing or zipping the
project never carries the previous user's data along.
"""

import os
import sys

import pytest

import config._overrides as overrides

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _inside_project(path: str) -> bool:
    path = os.path.abspath(path)
    return os.path.commonpath([path, PROJECT_ROOT]) == PROJECT_ROOT


def test_runtime_paths_live_outside_project_folder():
    import config.settings as settings
    import config.questions as questions
    import modules.resume_builder as resume_builder
    import modules.helpers as helpers

    for path in (
        settings.file_name,
        settings.failed_file_name,
        settings.logs_folder_path,
        settings.generated_resume_path,
        questions.default_resume_path,
        resume_builder.RESUME_YAML_PATH,
        resume_builder.RESUME_OUTPUT_DIR,
        helpers.get_default_temp_profile(),
    ):
        assert not _inside_project(path), f"{path} is inside the project folder"


def test_merge_move_merges_directories_and_never_overwrites(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "sub").mkdir(parents=True)
    (src / "new.txt").write_text("new")
    (src / "same.txt").write_text("from-src")
    (src / "sub" / "deep.txt").write_text("deep")
    dst.mkdir()
    (dst / "same.txt").write_text("already-here")

    overrides._merge_move(str(src), str(dst))

    assert (dst / "new.txt").read_text() == "new"
    assert (dst / "sub" / "deep.txt").read_text() == "deep"
    assert (dst / "same.txt").read_text() == "already-here"  # never overwritten
    assert (src / "same.txt").exists()  # the conflicting legacy file is left, not destroyed


def test_migrate_legacy_data_moves_project_data_to_data_dir(tmp_path, monkeypatch):
    project = tmp_path / "project"
    data = tmp_path / "data"
    (project / "all excels").mkdir(parents=True)
    (project / "all excels" / "history.csv").write_text("a,b")
    (project / "logs").mkdir()
    (project / "logs" / "log.txt").write_text("log")
    (project / ".bot_run.log").write_text("run")
    monkeypatch.setattr(overrides, "_ROOT_DIR", str(project))
    monkeypatch.setattr(overrides, "DATA_DIR", str(data))

    overrides._migrate_legacy_data()

    assert (data / "all excels" / "history.csv").read_text() == "a,b"
    assert (data / "logs" / "log.txt").read_text() == "log"
    assert (data / ".bot_run.log").read_text() == "run"
    assert not (project / "all excels").exists()
    assert not (project / "logs").exists()
    assert not (project / ".bot_run.log").exists()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-only guest profile location")
def test_migrate_moves_chrome_profile_whole_and_only_once(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy-profile"
    (legacy / "Default").mkdir(parents=True)
    (legacy / "Default" / "Cookies").write_text("session")
    new_profile = tmp_path / "data" / "chrome-profile"
    monkeypatch.setattr(overrides, "_ROOT_DIR", str(tmp_path / "project"))
    monkeypatch.setattr(overrides, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(overrides, "_LEGACY_WIN_CHROME_PROFILE", str(legacy))
    monkeypatch.setattr(overrides, "CHROME_GUEST_PROFILE_DIR", str(new_profile))

    overrides._migrate_legacy_data()

    assert (new_profile / "Default" / "Cookies").read_text() == "session"
    assert not legacy.exists()

    # An already-populated destination is never clobbered by a stale legacy copy.
    legacy.mkdir()
    (legacy / "stale.txt").write_text("x")
    overrides._migrate_legacy_data()
    assert (new_profile / "Default" / "Cookies").exists()
    assert legacy.exists()
