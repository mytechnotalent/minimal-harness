"""Per-model runtime profiles for the agent and provider."""

from dataclasses import dataclass

DEFAULT_TURNS = 24


@dataclass(frozen=True)
class ModelProfile:
    """Runtime settings tuned for one model family."""

    max_turns: int = DEFAULT_TURNS
    timeout: int = 180
    retries: int = 2
    web: bool = True
    lean: bool = False


DEFAULT_PROFILE = ModelProfile()

PROFILES = {
    "beam-free": ModelProfile(max_turns=12, timeout=180, retries=4, web=True),
    "deepseek-v4.1-flash": ModelProfile(
        max_turns=24, timeout=240, retries=2, web=True
    ),
    "qwen2.5-coder:7b": ModelProfile(
        max_turns=16, timeout=240, retries=2, web=False, lean=True
    ),
}


def profile_for(model: str) -> ModelProfile:
    """Return the runtime profile for a model identifier.

    Parameters
    ----------
    model : str
        Model name, optionally prefixed with a provider.

    Returns
    -------
    ModelProfile
        Matching profile or the default.
    """
    key = model.rsplit("/", 1)[-1]
    return PROFILES.get(key, DEFAULT_PROFILE)


def effective_turns(model: str, requested: int | None) -> int:
    """Return the effective turn budget for a model.

    Parameters
    ----------
    model : str
        Model identifier.
    requested : int or None
        Explicit command-line value, or ``None``.

    Returns
    -------
    int
        Explicit value when present, otherwise the profile value.
    """
    if requested is not None:
        return requested
    return profile_for(model).max_turns
