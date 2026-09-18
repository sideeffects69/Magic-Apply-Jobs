'''
Author:     Om Abhyankar

Copyright (c) 2026 Om Abhyankar

License:    MIT License
            https://opensource.org/license/mit
            
GitHub:     https://github.com/sideeffects69


version:    26.01.20.5.08
'''

from config._overrides import DATA_DIR


###################################################### CONFIGURE YOUR BOT HERE ######################################################

# >>>>>>>>>>> LinkedIn Settings <<<<<<<<<<<

# Keep the External Application tabs open?
close_tabs = False                  # True or False, Note: True or False are case-sensitive
'''
Note: RECOMMENDED TO LEAVE IT AS `True`, if you set it `False`, be sure to CLOSE ALL TABS BEFORE CLOSING THE BROWSER!!!
'''

# Follow easy applied companies
follow_companies = False            # True or False, Note: True or False are case-sensitive

## Upcoming features (In Development)
# # Send connection requests to HR's 
# connect_hr = True                  # True or False, Note: True or False are case-sensitive

# # What message do you want to send during connection request? (Max. 200 Characters)
# connect_request_message = ""       # Leave Empty to send connection request without personalized invitation (recommended to leave it empty, since you only get 10 per month without LinkedIn Premium*)

# Do you want the program to run continuously until you stop it? (Beta)
run_non_stop = False                # True or False, Note: True or False are case-sensitive
'''
Note: Will be treated as False if `run_in_background = True`
'''
alternate_sortby = True             # True or False, Note: True or False are case-sensitive
cycle_date_posted = True            # True or False, Note: True or False are case-sensitive
stop_date_cycle_at_24hr = True      # True or False, Note: True or False are case-sensitive

# >>>>>>>>>>> Applying on company websites (not just LinkedIn Easy Apply) <<<<<<<<<<<

# For jobs that are not Easy Apply, open the company's own application page and fill it in with your resume and details.
# Needs `easy_apply_only = False` in the search settings. If False, only the application link is saved.
external_apply_enabled = True       # True or False, Note: True or False are case-sensitive

# When a company site asks you to sign in or create an account, use its "Sign in / Sign up with Google" button.
use_google_login = True             # True or False, Note: True or False are case-sensitive

# If the tool needs a person (a CAPTCHA, Google's password or 2-step screen, a question it can't answer), how many seconds to wait
# for you in the browser window before giving up on that job. 0 = never wait. (Always 0 when running in the background.)
external_manual_wait_seconds = 120  # Integers >= 0

# Give up on one company site after this many seconds / page steps, so a stuck site never holds up the whole run.
external_apply_timeout_seconds = 300   # Integers >= 30
external_apply_max_steps = 25          # Integers >= 3



# Safety cap on how many applications (Easy Apply + external combined) the bot will
# submit in a single calendar day, counted across all your runs that day - not just
# this one. Protects your LinkedIn account from being flagged for automated activity.
# Set to -1 to disable (no daily cap, only `switch_number` per search term applies).
max_applications_per_day = -1       # -1 for no limit, or a positive integer like 100





# >>>>>>>>>>> RESUME GENERATOR (Experimental & In Development) <<<<<<<<<<<

# Give the path to the folder where all the generated resumes are to be stored
generated_resume_path = DATA_DIR + "/all resumes/" # (In Development)





# >>>>>>>>>>> Global Settings <<<<<<<<<<<

# Directory and name of the files where history of applied jobs is saved (Sentence after the last "/" will be considered as the file name).
# These live in the per-user data folder (outside this project) so sharing the project never shares your history.
file_name = DATA_DIR + "/all excels/all_applied_applications_history.csv"
failed_file_name = DATA_DIR + "/all excels/all_failed_applications_history.csv"
logs_folder_path = DATA_DIR + "/logs/"

# Set the maximum amount of time allowed to wait between each click in secs
click_gap = 1                       # Enter max allowed secs to wait approximately. (Only Non Negative Integers Eg: 0,1,2,3,....)

# If you want to see Chrome running then set run_in_background as False (May reduce performance). 
run_in_background = False           # True or False, Note: True or False are case-sensitive ,   If True, this will make pause_at_failed_question, pause_before_submit and run_in_background as False

# If you want to disable extensions then set disable_extensions as True (Better for performance)
disable_extensions = False          # True or False, Note: True or False are case-sensitive

# Run in safe mode. Set this true if chrome is taking too long to open or if you have multiple profiles in browser. This will open chrome in guest profile!
safe_mode = False                   # True or False, Note: True or False are case-sensitive

# Do you want scrolling to be smooth or instantaneous? (Can reduce performance if True)
smooth_scroll = False               # True or False, Note: True or False are case-sensitive

# If enabled (True), the program would keep your screen active and prevent PC from sleeping. Instead you could disable this feature (set it to false) and adjust your PC sleep settings to Never Sleep or a preferred time. 
keep_screen_awake = True            # True or False, Note: True or False are case-sensitive (Note: Will temporarily deactivate when any application dialog boxes are present (Eg: Pause before submit, Help needed for a question..))

# Automatically download and manage the matching Chrome driver, so you don't have to install ChromeDriver yourself. If False, you must install a matching ChromeDriver manually (see setup step 5).
auto_manage_driver = True          # True or False, Note: True or False are case-sensitive

# Do you want to get alerts on errors related to AI API connection?
showAiErrorAlerts = False            # True or False, Note: True or False are case-sensitive

# Use ChatGPT for resume building (Experimental Feature can break the application. Recommended to leave it as False) 
# use_resume_generator = False       # True or False, Note: True or False are case-sensitive ,   This experimental feature may only work with 'auto_manage_driver = True'.











############################################################################################################

# --- Load user settings saved by the local control panel (user_config.json).
# --- No-op if that file is absent: values fall back to the defaults above.
from config import _overrides as _o
_o.apply(__name__, globals())
############################################################################################################