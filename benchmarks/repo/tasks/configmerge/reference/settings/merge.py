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
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


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
    merged = dict(config)
    for key, value in env.items():
        if key.startswith(prefix):
            _assign(merged, key[len(prefix) :].lower().split("__"), value)
    return merged


def _assign(config, path, value):
    """Assign a typed environment value at a nested path.

    Parameters
    ----------
    config : dict
        Configuration being updated.

    path : list[str]
        Nested key path.

    value : str
        Raw environment value.

    Returns
    -------
    None
        The configuration is updated in place.
    """
    node = config
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = _typed(value)


def _typed(value):
    """Convert an environment string to a typed value.

    Parameters
    ----------
    value : str
        Raw value.

    Returns
    -------
    object
        Boolean, integer, or string value.
    """
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if value.strip().isdigit():
        return int(value.strip())
    return value
