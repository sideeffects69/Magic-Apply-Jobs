'''
Author:     Om Abhyankar

Copyright (c) 2026 Om Abhyankar

License:    MIT License
            https://opensource.org/license/mit

GitHub:     https://github.com/sideeffects69

version:    2024.11.28.16.00
'''


###################################################### CONFIGURE YOUR TOOLS HERE ######################################################


# >>>>>>>>>>> Easy Apply Questions & Inputs <<<<<<<<<<<

# Your legal name
first_name = "First"               # Your first name in quotes Eg: "First", "John"
middle_name = ""                   # Your middle name in quotes Eg: "Middle", ""
last_name = "Last"                 # Your last name in quotes Eg: "Last", "Smith"

# Email address to put on job applications. Leave empty to use your Google email (see secrets.py) or your LinkedIn login email.
email = ""                         # "you@example.com" or ""

# Phone number (required), make sure it's valid.
phone_number = "9876543210"        # Enter your 10 digit number in quotes Eg: "9876543210"

# What is your current city?
current_city = ""                  # Los Angeles, San Francisco, etc.
'''
Note: If left empty as "", the bot will fill in location of jobs location.
'''

# Address, not so common question but some job applications make it required!
street = "123 Main Street"
state = "STATE"
zipcode = "12345"
country = "Will Let You Know When Established"

## US Equal Opportunity questions
# What is your ethnicity or race? If left empty as "", tool will not answer the question. However, note that some companies make it compulsory to be answered
ethnicity = "Decline"              # "Decline", "Hispanic/Latino", "American Indian or Alaska Native", "Asian", "Black or African American", "Native Hawaiian or Other Pacific Islander", "White", "Other"

# How do you identify yourself? If left empty as "", tool will not answer the question. However, note that some companies make compulsory to be answered
gender = "Decline"                 # "Male", "Female", "Other", "Decline" or ""

# Are you physically disabled or have a history/record of having a disability? If left empty as "", tool will not answer the question. However, note that some companies make it compulsory to be answered
disability_status = "Decline"      # "Yes", "No", "Decline"

veteran_status = "Decline"         # "Yes", "No", "Decline"
##


'''
For string variables followed by comments with options, only use the answers from given options.
Some valid examples are:
* variable1 = "option1"         # "option1", "option2", "option3" or ("" to not select). Answers are case sensitive.#
* variable2 = ""                # "option1", "option2", "option3" or ("" to not select). Answers are case sensitive.#

Other variables are free text. No restrictions other than compulsory use of quotes.
Some valid examples are:
* variable3 = "Random Answer 5"         # Enter your answer. Eg: "Answer1", "Answer2"

Invalid inputs will result in an error!
'''




############################################################################################################

# --- Load user settings saved by the local control panel (user_config.json).
# --- No-op if that file is absent: values fall back to the defaults above.
from config import _overrides as _o
_o.apply(__name__, globals())
############################################################################################################
