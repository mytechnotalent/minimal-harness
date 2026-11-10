"""Reference solution that passes every starter task."""


def double(x):
    """Return x multiplied by two.

    Parameters
    ----------
    x : int or float
        Value to double.

    Returns
    -------
    int or float
        The doubled value.
    """
    return x * 2


def reverse(s):
    """Return the reverse of a string.

    Parameters
    ----------
    s : str
        Text to reverse.

    Returns
    -------
    str
        The reversed text.
    """
    return s[::-1]


def is_even(x):
    """Return True when x is an even integer.

    Parameters
    ----------
    x : int
        Value to test.

    Returns
    -------
    bool
        True when the value is even.
    """
    return x % 2 == 0


def palindrome(s):
    """Return True when s reads the same forward and backward.

    Parameters
    ----------
    s : str
        Text to test.

    Returns
    -------
    bool
        True when the text is a palindrome.
    """
    return s == s[::-1]


def sum_list(xs):
    """Return the sum of a list of numbers.

    Parameters
    ----------
    xs : list of int or float
        Numbers to add.

    Returns
    -------
    int or float
        Sum of the numbers.
    """
    return sum(xs)


def fibonacci(n):
    """Return the nth Fibonacci number.

    Parameters
    ----------
    n : int
        Index in the Fibonacci sequence.

    Returns
    -------
    int
        The nth Fibonacci number.
    """
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def gcd(a, b):
    """Return the greatest common divisor of two non-negative integers.

    Parameters
    ----------
    a : int
        First non-negative integer.

    b : int
        Second non-negative integer.

    Returns
    -------
    int
        Greatest common divisor of the two values.
    """
    while b:
        a, b = b, a % b
    return a


def fizz_buzz(n):
    """Return the classic FizzBuzz sequence for 1..n.

    Parameters
    ----------
    n : int
        Last number in the sequence.

    Returns
    -------
    list of str
        FizzBuzz words for the numbers 1 through n.
    """
    return [_fizz_buzz_word(i) for i in range(1, n + 1)]


def _fizz_buzz_word(i):
    """Return the FizzBuzz word for one number.

    Parameters
    ----------
    i : int
        Number to convert.

    Returns
    -------
    str
        FizzBuzz word or the number as text.
    """
    if i % 15 == 0:
        return "FizzBuzz"
    if i % 3 == 0:
        return "Fizz"
    if i % 5 == 0:
        return "Buzz"
    return str(i)
