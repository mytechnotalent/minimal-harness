"""In-memory inventory store."""


class Inventory:
    """Track stock quantities by SKU."""

    def __init__(self) -> None:
        """Create an empty store.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The store starts empty.
        """
        self.stock: dict[str, int] = {}

    def add(self, sku, qty, unit_cents):
        """Add stock for one SKU.

        Parameters
        ----------
        sku : str
            Stock keeping unit.

        qty : int
            Positive quantity to add.

        unit_cents : int
            Positive unit price in cents.

        Returns
        -------
        None
            Stock is updated in place.
        """
        raise NotImplementedError("add is not implemented")

    def remove(self, sku, qty):
        """Remove stock for one SKU.

        Parameters
        ----------
        sku : str
            Stock keeping unit.

        qty : int
            Positive quantity to remove.

        Returns
        -------
        None
            Stock is updated in place.
        """
        raise NotImplementedError("remove is not implemented")
