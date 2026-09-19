'''
Author:     Om Abhyankar

Copyright (c) 2026 Om Abhyankar

License:    MIT License
            https://opensource.org/license/mit
            
GitHub:     https://github.com/sideeffects69


version:    26.01.20.5.08
'''


# Imports

import os
import sys
import json
import pathlib

from time import sleep
from random import randint
from datetime import datetime, timedelta
from pyautogui import alert
from pprint import pprint

from config.settings import logs_folder_path
from config._overrides import CHROME_GUEST_PROFILE_DIR



#### Common functions ####

#< Directories related
def make_directories(paths: list[str]) -> None:
    '''Create any of the given directories that don't yet exist (a path pointing at a file creates its parent folder).'''
    for raw_path in paths:
        target = os.path.expanduser(raw_path).replace("//", "/")
        # If the last segment has an extension it's a file, so keep only its folder.
        if '.' in os.path.basename(target):
            target = os.path.dirname(target)
        if not target:
            continue
        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            print(f'Could not create the directory "{target}":', e)


def get_default_temp_profile() -> str:
    # Thanks to https://github.com/vinodbavage31 for suggestion!
    home = pathlib.Path.home()
    if sys.platform.startswith('win'):
        return CHROME_GUEST_PROFILE_DIR
    elif sys.platform.startswith('linux'):
        return str(home / ".auto-job-apply-profile")
    return str(home / "Library" / "Application Support" / "Google" / "Chrome" / "auto-job-apply-profile")


def find_default_profile_directory() -> str | None:
    '''
    Dynamically finds the default Google Chrome 'User Data' directory path
    across Windows, macOS, and Linux, regardless of OS version.

    Returns the absolute path as a string, or None if the path is not found.
    '''
    
    home = pathlib.Path.home()
    
    # Windows
    if sys.platform.startswith('win'):
        paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data"),
            os.path.expandvars(r"%USERPROFILE%\Local Settings\Application Data\Google\Chrome\User Data")
        ]
    # Linux
    elif sys.platform.startswith('linux'):
        paths = [
            str(home / ".config" / "google-chrome"),
            str(home / ".var" / "app" / "com.google.Chrome" / "data" / ".config" / "google-chrome"),
        ]
    # MacOS ## For some reason, opening with profile in MacOS is not creating a session for undetected-chromedriver!
    # elif sys.platform == 'darwin':
    #     paths = [
    #         str(home / "Library" / "Application Support" / "Google" / "Chrome")
    #     ]
    else:
        return None

    # Check each potential path and return the first one that exists
    for path_str in paths:
        if os.path.exists(path_str):
            return path_str
            
    return None
#>


def find_installed_chrome_major_version() -> int | None:
    '''
    Finds the major version number (e.g. 152) of the Chrome actually
    installed on this machine, or None if it can't be determined.

    When `auto_manage_driver` downloads a chromedriver without being told a
    version, it does NOT detect the installed browser - it just grabs
    whatever "latest" chromedriver Google's API currently reports, which can
    be ahead of what's actually installed (especially right after a new
    Chrome release). That mismatch makes Selenium refuse to start with
    "This version of ChromeDriver only supports Chrome version X". Passing
    this detected version to `uc.Chrome(version_main=...)` avoids that.
    '''
    if sys.platform.startswith('win'):
        try:
            import winreg
            # The Google Update GUID for Chrome stable. This key is written by
            # the Google Update service itself the moment Chrome is installed
            # OR silently auto-updated in the background - unlike BLBeacon
            # below, it does NOT require the browser to have ever actually been
            # opened by this Windows user, which BLBeacon does. Checked across
            # all three locations Chrome installs to (per-user, system-wide
            # 64-bit, system-wide 32-bit registry view on 64-bit Windows).
            guid = r"{8A69D345-D564-463C-AFF1-A69D9E530F96}"
            for hive, subkey in [
                (winreg.HKEY_CURRENT_USER, r"Software\Google\Update\Clients\%s" % guid),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Update\Clients\%s" % guid),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Google\Update\Clients\%s" % guid),
            ]:
                try:
                    key = winreg.OpenKey(hive, subkey)
                    version, _ = winreg.QueryValueEx(key, "pv")
                    return int(version.split(".")[0])
                except OSError:
                    continue
        except (ImportError, ValueError, IndexError):
            pass
        try:
            import winreg
            # Only present after Chrome has actually been launched at least
            # once by this Windows user - kept as a fallback, not primary.
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Google\Chrome\BLBeacon")
            version, _ = winreg.QueryValueEx(key, "version")
            return int(version.split(".")[0])
        except (OSError, ValueError, IndexError):
            pass
        try:
            import subprocess
            candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                # Chrome installed without admin rights (common on locked-down
                # or work PCs) lands here instead of Program Files.
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ]
            chrome_path = next((p for p in candidates if os.path.exists(p)), None)
            if not chrome_path:
                return None
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Item '{chrome_path}').VersionInfo.ProductVersion"],
                capture_output=True, text=True, timeout=10,
            )
            return int(result.stdout.strip().split(".")[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None
    elif sys.platform == 'darwin':
        try:
            import subprocess
            result = subprocess.run(
                ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            # Output looks like "Google Chrome 152.0.7977.82"
            digits = result.stdout.strip().split()[-1]
            return int(digits.split(".")[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None
    elif sys.platform.startswith('linux'):
        try:
            import subprocess
            for binary in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
                try:
                    result = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
                    digits = result.stdout.strip().split()[-1]
                    return int(digits.split(".")[0])
                except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                    continue
        except ImportError:
            pass
    return None
#>


#< Logging related
def critical_error_log(possible_reason: str, stack_trace: Exception) -> None:
    '''
    Function to log and print critical errors along with datetime stamp
    '''
    print_lg(possible_reason, stack_trace, datetime.now(), from_critical=True)


def get_log_path():
    '''
    Function to replace '//' with '/' for logs path
    '''
    try:
        path = logs_folder_path+"/log.txt"
        return path.replace("//","/")
    except Exception as e:
        critical_error_log("Failed getting log path! So assigning default logs path: './logs/log.txt'", e)
        return "logs/log.txt"


__logs_file_path = get_log_path()


def print_lg(*msgs: str | dict, end: str = "\n", pretty: bool = False, flush: bool = False, from_critical: bool = False) -> None:
    '''
    Function to log and print. **Note that, `end` and `flush` parameters are ignored if `pretty = True`**

    Printing to the console and writing to the log file are handled independently:
    a message the console's codepage can't display (common with job titles,
    companies or descriptions containing accents, emoji or non-Latin scripts)
    must not stop it from being saved to log.txt, and must never be mistaken
    for log.txt actually being locked by another program.
    '''
    for message in msgs:
        try:
            pprint(message) if pretty else print(message, end=end, flush=flush)
        except Exception:
            # Console can't display this message (encoding). Non-fatal: it still
            # gets written to log.txt below, which is always opened as UTF-8.
            pass
        try:
            try:
                file = open(__logs_file_path, 'a+', encoding="utf-8")
            except FileNotFoundError:
                os.makedirs(os.path.dirname(os.path.abspath(__logs_file_path)), exist_ok=True)
                file = open(__logs_file_path, 'a+', encoding="utf-8")
            with file:
                file.write(str(message) + end)
        except OSError as e:
            # print_lg() is called from hundreds of places throughout a run - a
            # blocking modal here (especially with this project living inside a
            # OneDrive-synced folder, where transient locks are common) could
            # fire repeatedly and freeze an unattended run entirely. The console
            # print above already happened, so nothing is silently lost; just
            # note it once via the one-shot retry below instead of a popup.
            if not from_critical:
                critical_error_log(f"log.txt in {logs_folder_path} is open or occupied by another program! Skipped saving: \"{message}\"", e)
#>


def buffer(speed: int=0) -> None:
    '''
    Function to wait within a period of selected random range.
    * Will not wait if input `speed <= 0`
    * Will wait within a random range of 
      - `0.6 to 1.0 secs` if `1 <= speed < 2`
      - `1.0 to 1.8 secs` if `2 <= speed < 3`
      - `1.8 to speed secs` if `3 <= speed`
    '''
    if speed<=0:
        return
    elif speed < 2:
        return sleep(randint(6,10)*0.1)
    elif speed < 3:
        return sleep(randint(10,18)*0.1)
    else:
        return sleep(randint(18,round(speed)*10)*0.1)
    

def manual_login_retry(is_logged_in: callable, limit: int = 2) -> None:
    '''
    Function to ask and validate manual login
    '''
    count = 0
    while not is_logged_in():
        print_lg("Seems like you're not logged in!")
        button = "Confirm Login"
        message = 'After you successfully Log In, please click "{}" button below.'.format(button)
        if count > limit:
            button = "Skip Confirmation"
            message = 'If you\'re seeing this message even after you logged in, Click "{}". Seems like auto login confirmation failed!'.format(button)
        count += 1
        if alert(message, "Login Required", button) and count > limit: return



def calculate_date_posted(time_string: str) -> datetime | None:
    '''
    Turn a LinkedIn "posted" phrase like "3 days ago" into an approximate datetime.
    Returns None when the phrase can't be understood. Months and years are
    approximated as 30 and 365 days respectively.
    '''
    import re
    match = re.search(r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago',
                      time_string.strip(), re.IGNORECASE)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    spans = {
        'second': timedelta(seconds=amount),
        'minute': timedelta(minutes=amount),
        'hour': timedelta(hours=amount),
        'day': timedelta(days=amount),
        'week': timedelta(weeks=amount),
        'month': timedelta(days=amount * 30),
        'year': timedelta(days=amount * 365),
    }
    delta = spans.get(unit)
    return datetime.now() - delta if delta else None


def convert_to_lakhs(value: str) -> str:
    '''
    Converts str value to lakhs, no validations are done except for length and stripping.
    Examples:
    * "100000" -> "1.00"
    * "101,000" -> "10.1," Notice ',' is not removed 
    * "50" -> "0.00"
    * "5000" -> "0.05" 
    '''
    value = value.strip()
    l = len(value)
    if l > 0:
        if l > 5:
            value = value[:l-5] + "." + value[l-5:l-3]
        else:
            value = "0." + "0"*(5-l) + value[:2]
    return value


def convert_to_json(data) -> dict:
    '''
    Function to convert data to JSON, if unsuccessful, returns `{"error": "Unable to parse the response as JSON", "data": data}`
    '''
    try:
        result_json = json.loads(data)
        return result_json
    except json.JSONDecodeError:
        return {"error": "Unable to parse the response as JSON", "data": data}


def truncate_for_csv(data, max_length: int = 131000, suffix: str = "...[TRUNCATED]") -> str:
    '''
    Coerce any value to a string that's safe to write into a CSV cell, shortening it
    (with a marker suffix) if it would exceed max_length. Never raises.
    '''
    try:
        text = "" if data is None else str(data)
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix
    except Exception as e:
        return f"[could not stringify value: {e}]"


