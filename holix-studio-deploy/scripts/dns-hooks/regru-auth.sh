#!/usr/bin/env python3
"""Certbot --manual-auth-hook entry (must run with python3, not bash)."""
import os
import runpy
import sys

# same directory as this file
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
os.chdir(here)
runpy.run_path(os.path.join(here, "regru_dns.py"), run_name="__not_main__")
# invoke auth
sys.argv = ["regru_dns.py", "auth"]
from regru_dns import cmd_auth  # noqa: E402

cmd_auth()
