"""Build a macOS alias app bundle for Minimal Harness."""

from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent

setup(
    name="Minimal Harness",
    app=["scripts/run_desktop.py"],
    options={
        "py2app": {
            "alias": True,
            "argv_emulation": False,
            "iconfile": str(ROOT / "packaging" / "MinimalHarness.icns"),
            "plist": {
                "CFBundleName": "Minimal Harness",
                "CFBundleDisplayName": "Minimal Harness",
                "CFBundleIdentifier": "com.minimalharness.desktop",
                "LSEnvironment": {"HARNESS_HOME": str(ROOT)},
            },
        }
    },
    setup_requires=["py2app"],
)
