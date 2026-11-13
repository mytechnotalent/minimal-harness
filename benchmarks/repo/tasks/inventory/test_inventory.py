"""Hidden tests for the inventory task."""

import unittest

from inventory.pricing import discount_rate
from inventory.pricing import total_cents
from inventory.store import Inventory


class InventoryTests(unittest.TestCase):
    """Verify stock, discounts, and totals."""

    def test_discount_tiers(self) -> None:
        """Discount tiers change at ten and fifty units.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(discount_rate(9), 0.0)
        self.assertEqual(discount_rate(10), 0.05)
        self.assertEqual(discount_rate(49), 0.05)
        self.assertEqual(discount_rate(50), 0.10)

    def test_store_roundtrip(self) -> None:
        """Stock updates and validation work.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        store = Inventory()
        store.add("a", 5, 100)
        self.assertEqual(store.stock["a"], 5)
        store.remove("a", 2)
        self.assertEqual(store.stock["a"], 3)

    def test_store_validation(self) -> None:
        """Invalid stock operations raise errors.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        store = Inventory()
        store.add("a", 5, 100)
        with self.assertRaises(ValueError):
            store.add("b", 0, 100)
        with self.assertRaises(KeyError):
            store.remove("missing", 1)
        with self.assertRaises(ValueError):
            store.remove("a", 99)

    def test_total_with_discount_and_tax(self) -> None:
        """Totals apply the tier discount then half-up tax.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        order = {"a": (10, 100), "b": (5, 200)}
        self.assertEqual(total_cents(order, 825), 2057)


if __name__ == "__main__":
    unittest.main()
