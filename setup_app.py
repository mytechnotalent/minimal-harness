"""Build a macOS app bundle for SavrenAI."""

import os
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent
RELEASE = os.getenv("SAVRENAI_RELEASE") == "1"
ENVIRONMENT = {} if RELEASE else {"HARNESS_HOME": str(ROOT)}

setup(
    name="SavrenAI",
    app=["scripts/run_desktop.py"],
    options={
        "py2app": {
            "alias": not RELEASE,
            "argv_emulation": False,
            "iconfile": str(ROOT / "packaging" / "SavrenAI.icns"),
            "plist": {
                "CFBundleName": "SavrenAI",
                "CFBundleDisplayName": "SavrenAI",
                "CFBundleIdentifier": "com.savrenai.desktop",
                "LSEnvironment": ENVIRONMENT,
            },
        }
    },
    setup_requires=["py2app"],
)
