"""Reference solution that passes every starter task."""


def double(x):
    """Return x multiplied by two."""
    return x * 2


def reverse(s):
    """Return the reverse of a string."""
    return s[::-1]


def is_even(x):
    """Return True when x is an even integer."""
    return x % 2 == 0


def palindrome(s):
    """Return True when s reads the same forward and backward."""
    return s == s[::-1]


def sum_list(xs):
    """Return the sum of a list of numbers."""
    return sum(xs)


def fibonacci(n):
    """Return the nth Fibonacci number."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def gcd(a, b):
    """Return the greatest common divisor of two non-negative integers."""
    while b:
        a, b = b, a % b
    return a


def fizz_buzz(n):
    """Return the classic FizzBuzz sequence for 1..n."""
    return [_fizz_buzz_word(i) for i in range(1, n + 1)]


def _fizz_buzz_word(i):
    """Return the FizzBuzz word for one number."""
    if i % 15 == 0:
        return "FizzBuzz"
    if i % 3 == 0:
        return "Fizz"
    if i % 5 == 0:
        return "Buzz"
    return str(i)
