def validate_password_complexity(password: str) -> str:
    if not 8 <= len(password) <= 32:
        raise ValueError("Password must be 8-32 characters long")
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one upper case character")
    if not any(c.islower() for c in password):
        raise ValueError("Password must contain at least one lower case character")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one digit")
    if not any(c for c in password if c in "@$!%*?#&"):
        raise ValueError(
            "Password must contain at least one special character:"
            " @, $, !, %, *, ?, #, &."
        )
    return password
