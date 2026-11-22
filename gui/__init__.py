"""Native desktop shell for the Minimal Harness agent."""

import importlib

__all__ = ["AgentWorker", "QuestionBridge"]


def __getattr__(name: str):
    """Load a worker class on first use.

    Parameters
    ----------
    name : str
        Requested attribute.

    Returns
    -------
    type
        Worker class.

    Raises
    ------
    AttributeError
        When the requested attribute is unknown.
    """
    if name not in __all__:
        raise AttributeError(name)
    module = importlib.import_module(".worker", __name__)
    return getattr(module, name)
