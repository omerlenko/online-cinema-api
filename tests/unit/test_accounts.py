import pytest

from src.accounts.validators import validate_password_complexity


@pytest.mark.parametrize(
    "password, expected_error_msg",
    [
        ("Short1!", "Password must be 8-32 characters long"),
        ("A" * 30 + "a1!", "Password must be 8-32 characters long"),
        ("lowercase1!", "Password must contain at least one upper case character"),
        ("UPPERCASE1!", "Password must contain at least one lower case character"),
        ("NoDigits!", "Password must contain at least one digit"),
        ("NoSpecial1", "Password must contain at least one special character"),
    ],
)
def test_complexity_validator_raises_invalid_passwords(
    password: str, expected_error_msg: str
):
    with pytest.raises(ValueError, match=expected_error_msg):
        validate_password_complexity(password)


@pytest.mark.parametrize(
    "valid_password",
    [
        "ValidPass123!",
        "LongerPassword987$",
        "aB1@cDe2#fG3$",
        "PassWord_456!",
        "A" * 5 + "a1!",
        "A" * 29 + "a1!",
    ],
)
def test_complexity_validator_with_valid_passwords(valid_password: str):
    result = validate_password_complexity(valid_password)
    assert result == valid_password
