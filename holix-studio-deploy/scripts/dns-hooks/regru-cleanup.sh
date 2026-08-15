#!/usr/bin/env python3
"""Certbot --manual-cleanup-hook entry (must run with python3, not bash)."""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
os.chdir(here)
sys.argv = ["regru_dns.py", "cleanup"]
from regru_dns import cmd_cleanup  # noqa: E402

cmd_cleanup()
