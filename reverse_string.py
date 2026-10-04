"""Reverse a string.

Usage:
    python reverse_string.py hello      -> olleh
    echo hello | python reverse_string.py

Reading of the task: reverse the string's characters (not its words).
Input comes from the command-line arguments, or from stdin if none are given.
"""

import sys


def reverse_string(s: str) -> str:
    return s[::-1]


def main() -> None:
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read().rstrip("\n")
    print(reverse_string(text))


if __name__ == "__main__":
    main()
