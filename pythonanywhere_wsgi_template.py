# Template for PythonAnywhere's WSGI configuration file.
#
# This file does NOT run as part of the app — it's a reference to copy into
# the real WSGI config file that PythonAnywhere generates for you (linked
# near the top of the Web tab). Paste this in place of its "Flask" section.
#
# Before pasting:
#   1. Replace 'yourusername' with your PythonAnywhere username.
#   2. Replace the admin credentials and secret key below with your own.

import os
import sys

path = "/home/yourusername/dinkEngine"
if path not in sys.path:
    sys.path.insert(0, path)

# Manually-configured PythonAnywhere apps have no dashboard env-var UI, so set
# these here instead. This file lives only in your own PythonAnywhere account.
os.environ.setdefault("ADMIN_USERNAME", "yourname")
os.environ.setdefault("ADMIN_PASSWORD", "your-strong-password")
os.environ.setdefault("SECRET_KEY", "a-random-secret-string")

from app import app as application  # noqa: E402
