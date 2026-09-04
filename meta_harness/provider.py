"""Provider and model catalog helpers."""

import json
import urllib.request
from typing import Any


class ProviderCatalog:
    """Discover OpenRouter models without exposing credentials."""

    def list_models(self) -> list[dict[str, Any]]:
        """Return available OpenRouter models.

        Returns
        -------
        list[dict[str, Any]]
            Provider model records, or an empty list on failure.
        """
        try:
            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/models"
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response).get("data", [])
        except Exception:
            return []

    def free_models(self) -> list[dict[str, Any]]:
        """Return models with zero prompt and completion pricing.

        Returns
        -------
        list[dict[str, Any]]
            Free model records.
        """
        return [item for item in self.list_models() if self._is_free(item)]

    def _is_free(self, model: dict[str, Any]) -> bool:
        """Check whether a model reports zero pricing.

        Parameters
        ----------
        model : dict[str, Any]
            Provider model record.

        Returns
        -------
        bool
            Whether both listed prices are zero.
        """
        pricing = model.get("pricing", {})
        return (
            pricing.get("prompt") == "0" and pricing.get("completion") == "0"
        )
