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
        if qty <= 0 or unit_cents <= 0:
            raise ValueError("qty and unit_cents must be positive")
        self.stock[sku] = self.stock.get(sku, 0) + qty

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
        if sku not in self.stock:
            raise KeyError(sku)
        if qty <= 0 or self.stock[sku] < qty:
            raise ValueError("insufficient stock")
        self.stock[sku] -= qty
