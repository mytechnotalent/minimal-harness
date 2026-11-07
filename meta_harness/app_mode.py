"""Select the desktop interface mode from environment settings."""

import os

CYBER = "cyber"
HAL = "hal"
CLASSIC = "classic"
_CYBER_ALIASES = ("cyber", "neon", "dark")
_HAL_ALIASES = ("hal", "hal9000", "minimal")


def ui_mode() -> str:
    """Return the configured desktop interface mode.

    Returns
    -------
    str
        ``"cyber"`` when opted in, otherwise ``"classic"``.
    """
    value = os.getenv("HARNESS_UI_MODE", "").strip().lower()
    if value in _HAL_ALIASES:
        return HAL
    return CYBER if value in _CYBER_ALIASES else CLASSIC


def voice_enabled() -> bool:
    """Return whether the voice interface is enabled.

    Returns
    -------
    bool
        ``True`` only in cyber mode.
    """
    return ui_mode() in (CYBER, HAL)
