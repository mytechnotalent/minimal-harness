"""Broken solution used to prove the evaluator actually fails bad code."""


def double(x):
    """Return the wrong answer.

    Parameters
    ----------
    x : int or float
        Value that should be doubled.

    Returns
    -------
    int or float
        The wrong value.
    """
    return x + 2


def reverse(s):
    """Return the wrong answer.

    Parameters
    ----------
    s : str
        Text that should be reversed.

    Returns
    -------
    str
        The wrong text.
    """
    return s


def is_even(x):
    """Return the wrong answer.

    Parameters
    ----------
    x : int
        Value that should be tested.

    Returns
    -------
    bool
        The wrong result.
    """
    return False


def palindrome(s):
    """Return the wrong answer.

    Parameters
    ----------
    s : str
        Text that should be tested.

    Returns
    -------
    bool
        The wrong result.
    """
    return False


def sum_list(xs):
    """Return the wrong answer.

    Parameters
    ----------
    xs : list of int or float
        Numbers that should be added.

    Returns
    -------
    int or float
        The wrong sum.
    """
    return 0 if not xs else xs[0]


def fibonacci(n):
    """Return the wrong answer.

    Parameters
    ----------
    n : int
        Index that should be converted.

    Returns
    -------
    int
        The wrong number.
    """
    return n


def gcd(a, b):
    """Return the wrong answer.

    Parameters
    ----------
    a : int
        First non-negative integer.

    b : int
        Second non-negative integer.

    Returns
    -------
    int
        The wrong divisor.
    """
    return 1


def fizz_buzz(n):
    """Return the wrong answer.

    Parameters
    ----------
    n : int
        Last number in the sequence.

    Returns
    -------
    list of str
        The wrong sequence.
    """
    return [str(i) for i in range(1, n + 1)]
