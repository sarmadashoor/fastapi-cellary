"""
Password utilities for hashing and migration.
"""

import getpass
import sys

from app.security import hash_password


def generate_password_hash(password: str | None = None) -> str:
    """
    Generate a hashed password. If no password provided, prompts for input.

    Args:
        password: Optional plain text password. If None, prompts user.

    Returns:
        Hashed password string
    """
    if password is None:
        password = getpass.getpass("Enter password to hash: ")

    return hash_password(password)


def main():
    """CLI tool for generating password hashes."""
    if len(sys.argv) > 1:
        # Password provided as argument (not recommended for security)
        password = sys.argv[1]
        print("Warning: Providing password as command line argument is insecure!")
    else:
        # Prompt for password securely
        password = getpass.getpass("Enter password to hash: ")

    hashed = hash_password(password)
    print(f"\nHashed password: {hashed}")
    print("\nTo use this password, set your environment variable to:")
    print(f"ADMIN_PASSWORD='{hashed}'")


if __name__ == "__main__":
    main()
