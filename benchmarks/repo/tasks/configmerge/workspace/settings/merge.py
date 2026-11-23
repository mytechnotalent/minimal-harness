"""Merge configuration mappings."""


def deep_merge(base, override):
    """Merge two configuration mappings.

    Parameters
    ----------
    base : dict
        Base configuration.

    override : dict
        Values that take precedence.

    Returns
    -------
    dict
        Merged configuration.
    """
    raise NotImplementedError("deep_merge is not implemented")


def apply_env(config, env, prefix="APP_"):
    """Apply environment overrides to a configuration.

    Parameters
    ----------
    config : dict
        Base configuration.

    env : dict
        Environment mapping.

    prefix : str
        Variable name prefix.

    Returns
    -------
    dict
        Merged configuration.
    """
    raise NotImplementedError("apply_env is not implemented")
