"""Hidden tests for the config merge task."""

import unittest

from settings.merge import apply_env
from settings.merge import deep_merge

_ENV = {
    "APP_DB__HOST": "db.internal",
    "APP_WORKERS": "4",
    "APP_DEBUG": "true",
    "APP_NAME": "svc",
    "OTHER_DB__HOST": "ignored",
}


class ConfigMergeTests(unittest.TestCase):
    """Verify recursive merging and environment overrides."""

    def test_deep_merge_recurses_without_mutating(self) -> None:
        """Nested dicts merge and the base stays unchanged.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        base = {"db": {"host": "localhost", "port": 5432}, "debug": False}
        override = {"db": {"port": 6000}, "debug": True}
        merged = deep_merge(base, override)
        self.assertEqual(merged["db"], {"host": "localhost", "port": 6000})
        self.assertTrue(merged["debug"])
        self.assertEqual(base["db"]["port"], 5432)

    def test_apply_env_nested_and_typed(self) -> None:
        """Double underscores nest keys and values are typed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        config = {"db": {"host": "localhost"}, "workers": 1}
        self._assert_merged(apply_env(config, _ENV))

    def _assert_merged(self, merged) -> None:
        """Verify nested, typed, and filtered values.

        Parameters
        ----------
        merged : dict
            Merged configuration.

        Returns
        -------
        None
        """
        self.assertEqual(merged["db"]["host"], "db.internal")
        self.assertEqual(merged["workers"], 4)
        self.assertTrue(merged["debug"])
        self.assertEqual(merged["name"], "svc")
        self.assertNotIn("other", merged)

    def test_custom_prefix(self) -> None:
        """A custom prefix selects variables.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        merged = apply_env({}, {"SVC_A": "x", "APP_B": "y"}, prefix="SVC_")
        self.assertEqual(merged, {"a": "x"})


if __name__ == "__main__":
    unittest.main()
