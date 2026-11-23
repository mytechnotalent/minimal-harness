"""Pricing rules for orders."""


def discount_rate(total_units):
    """Return the discount rate for an order size.

    Parameters
    ----------
    total_units : int
        Total units in the order.

    Returns
    -------
    float
        Discount rate between zero and one.
    """
    raise NotImplementedError("discount_rate is not implemented")


def total_cents(order, tax_bp):
    """Return the discounted, taxed order total in cents.

    Parameters
    ----------
    order : dict
        Mapping of sku to ``(qty, unit_cents)`` pairs.

    tax_bp : int
        Tax in basis points.

    Returns
    -------
    int
        Total charge in cents.
    """
    raise NotImplementedError("total_cents is not implemented")
