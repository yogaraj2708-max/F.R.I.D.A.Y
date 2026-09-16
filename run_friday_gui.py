"""
F.R.I.D.A.Y. 2.0 - Graphical Launcher
Run this script to launch the Windows 11 Fluent Design AI Assistant.
"""

import os
import sys

# Ensure Windows SSL certificate authority bundle is explicitly registered
try:
    import certifi
    ca_bundle = certifi.where()
    if os.path.exists(ca_bundle):
        os.environ["SSL_CERT_FILE"] = ca_bundle
        os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
        os.environ["CURL_CA_BUNDLE"] = ca_bundle
except Exception as e:
    import logging
    logging.getLogger("FRIDAY.Launcher").warning(f"Failed to register custom CA bundle: {e}")

# Ensure root directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from friday_ui.app import main

if __name__ == "__main__":
    main()
