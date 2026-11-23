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
    if total_units >= 50:
        return 0.10
    if total_units >= 10:
        return 0.05
    return 0.0


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
    units = sum(qty for qty, _ in order.values())
    subtotal = sum(qty * price for qty, price in order.values())
    rate = int(round(discount_rate(units) * 10000))
    discounted = _half_up(subtotal * (10000 - rate), 10000)
    return discounted + _half_up(discounted * tax_bp, 10000)


def _half_up(value, divisor):
    """Round a ratio half up.

    Parameters
    ----------
    value : int
        Numerator.

    divisor : int
        Denominator.

    Returns
    -------
    int
        Rounded integer.
    """
    return (value + divisor // 2) // divisor
