"""Broken solution used to prove the evaluator actually fails bad code."""


def double(x):
    """Return the wrong answer."""
    return x + 2


def reverse(s):
    """Return the wrong answer."""
    return s


def is_even(x):
    """Return the wrong answer."""
    return False


def palindrome(s):
    """Return the wrong answer."""
    return False


def sum_list(xs):
    """Return the wrong answer."""
    return 0 if not xs else xs[0]


def fibonacci(n):
    """Return the wrong answer."""
    return n


def gcd(a, b):
    """Return the wrong answer."""
    return 1


def fizz_buzz(n):
    """Return the wrong answer."""
    return [str(i) for i in range(1, n + 1)]
