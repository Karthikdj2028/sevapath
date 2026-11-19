"""
Pytest unit tests for SevaPath Regex Validation Engine.

Tests:
- Indian mobile phone syntax, prefixes, separators, ASCII digits, normalization
- Pragmatic email syntax, consecutive dots, domain labels, normalization
- Deferred government identifiers
- Boundary cases: empty, whitespace-only, non-string, oversized inputs
- Unicode digits and invalid character rejection
- Bilingual validation messages
"""

import pytest
from app.core.regex_validator import RegexValidator, ValidationResult, CIVIC_VALIDATION_DISCLAIMER


# --- Phone Number Tests ---

@pytest.mark.parametrize("valid_phone,expected_normalized", [
    ("9876543210", "9876543210"),
    ("8123456789", "8123456789"),
    ("7012345678", "7012345678"),
    ("6987654321", "6987654321"),
    ("+919876543210", "9876543210"),
    ("+91 9876543210", "9876543210"),
    ("+91-98765-43210", "9876543210"),
    ("919876543210", "9876543210"),
    ("91 9876543210", "9876543210"),
    ("09876543210", "9876543210"),
    ("0 9876543210", "9876543210"),
    ("98765 43210", "9876543210"),
    ("98765-43210", "9876543210"),
    ("  9876543210  ", "9876543210"),  # Surrounding whitespace trimmed
])
def test_valid_phone_numbers(valid_phone, expected_normalized):
    """Verifies that all valid Indian mobile numbers are recognized and correctly normalized."""
    res = RegexValidator.validate_phone(valid_phone)
    assert res.is_valid is True
    assert res.cleaned_value == expected_normalized
    assert res.error_message_en is None
    assert res.disclaimer == CIVIC_VALIDATION_DISCLAIMER


@pytest.mark.parametrize("invalid_phone", [
    "5876543210",          # Starts with 5 (invalid Indian mobile series)
    "1234567890",          # Starts with 1
    "987654321",           # Only 9 digits (too short)
    "98765432100",         # 11 digits without prefix (too long)
    "+91 987654321",       # 9 digits with prefix
    "+92 9876543210",      # Wrong country code (+92)
    "98765--43210",        # Duplicate hyphen
    "98765  43210",        # Duplicate space
    "+91-9876543210-",     # Trailing hyphen
    "98765a43210",         # Contains alphabetic character
    "98765#43210",         # Contains symbol
    "phone: 9876543210",   # Arbitrary text prefix
])
def test_invalid_phone_numbers(invalid_phone):
    """Verifies that malformed phone formats are cleanly rejected."""
    res = RegexValidator.validate_phone(invalid_phone)
    assert res.is_valid is False
    assert res.cleaned_value is None
    assert "Invalid Indian mobile number format" in res.error_message_en


def test_phone_unicode_digits_rejected():
    """
    CRITICAL REQUIREMENT:
    ASCII [0-9] digit matching only. Unicode digits must be strictly rejected.
    """
    # Eastern Arabic numerals: ۹۸۷۶۵۴۳۲۱۰
    arabic_digits = "\u0669\u0668\u0667\u0666\u0665\u0664\u0663\u0662\u0661\u0660"
    res = RegexValidator.validate_phone(arabic_digits)
    assert res.is_valid is False

    # Mathematical bold digits: 𝟡𝟠𝟟𝟞𝟝𝟜𝟛𝟚𝟙𝟘
    math_digits = "𝟡𝟠𝟟𝟞𝟝𝟜𝟛𝟚𝟙𝟘"
    res2 = RegexValidator.validate_phone(math_digits)
    assert res2.is_valid is False


def test_phone_empty_and_non_string_inputs():
    """Verifies safe handling of null, empty, whitespace-only, and non-string inputs."""
    assert RegexValidator.validate_phone(None).is_valid is False
    assert RegexValidator.validate_phone("").is_valid is False
    assert RegexValidator.validate_phone("   ").is_valid is False
    assert RegexValidator.validate_phone(9876543210).is_valid is False
    assert RegexValidator.validate_phone(["9876543210"]).is_valid is False


def test_phone_oversized_payload_rejected():
    """Verifies immediate rejection of strings exceeding MAX_PHONE_INPUT_LENGTH."""
    oversized = "9876543210" * 5  # 50 chars
    res = RegexValidator.validate_phone(oversized)
    assert res.is_valid is False
    assert "exceeds maximum length" in res.error_message_en


# --- Email Address Tests ---

@pytest.mark.parametrize("valid_email,expected_normalized", [
    ("citizen@example.com", "citizen@example.com"),
    ("Citizen.Name@TamilNadu.gov.in", "citizen.name@tamilnadu.gov.in"),
    ("user+tag@domain.co.in", "user+tag@domain.co.in"),
    ("first_last@dept.sub.gov.in", "first_last@dept.sub.gov.in"),
    ("  citizen@tnesevai.tn.gov.in  ", "citizen@tnesevai.tn.gov.in"),
])
def test_valid_emails(valid_email, expected_normalized):
    """Verifies valid email syntax and normalization."""
    res = RegexValidator.validate_email(valid_email)
    assert res.is_valid is True
    assert res.cleaned_value == expected_normalized
    assert res.error_message_en is None


@pytest.mark.parametrize("invalid_email", [
    "citizen",                     # Missing @ and domain
    "citizen@",                    # Missing domain
    "@domain.com",                 # Missing local part
    "citizen@domain",              # Missing TLD
    "citizen@domain.c",            # TLD too short (< 2 chars)
    "citizen..name@domain.com",    # Consecutive dots in local part
    "citizen@domain..com",         # Consecutive dots in domain
    "citizen@domain.com.",         # Trailing dot
    ".citizen@domain.com",         # Leading dot in local part
    "citi zen@domain.com",         # Space inside
    "citizen@exämple.com",         # Non-ASCII character
    "citizen@@domain.com",         # Multiple @
])
def test_invalid_emails(invalid_email):
    """Verifies malformed email addresses are rejected."""
    res = RegexValidator.validate_email(invalid_email)
    assert res.is_valid is False
    assert res.cleaned_value is None
    assert "Invalid email address syntax" in res.error_message_en


def test_email_empty_and_non_string_inputs():
    """Verifies safe handling of null, empty, and non-string email inputs."""
    assert RegexValidator.validate_email(None).is_valid is False
    assert RegexValidator.validate_email("").is_valid is False
    assert RegexValidator.validate_email("   ").is_valid is False
    assert RegexValidator.validate_email(12345).is_valid is False


def test_email_oversized_payload_rejected():
    """Verifies that emails > 254 characters are rejected immediately."""
    oversized = ("a" * 245) + "@example.com"
    res = RegexValidator.validate_email(oversized)
    assert res.is_valid is False
    assert "exceeds maximum length" in res.error_message_en


# --- Deferred Government Identifiers & Bilingual Output Tests ---

def test_deferred_government_identifiers():
    """
    CRITICAL REQUIREMENT:
    CAN, ration card, and acknowledgment numbers are deferred until authoritative
    format evidence is documented.
    """
    for field in ["can_number", "ration_card", "acknowledgment_number"]:
        res = RegexValidator.validate_format(field, "1234567890123")
        assert res.is_valid is False
        assert "deferred" in res.error_message_en.lower()
        assert "நிறுத்தி வைக்கப்பட்டுள்ளது" in res.error_message_ta


def test_bilingual_dictionary_output():
    """Verifies that to_dict(lang='ta') outputs Tamil error messages."""
    res = RegexValidator.validate_phone("invalid")
    en_dict = res.to_dict(lang="en")
    ta_dict = res.to_dict(lang="ta")

    assert "Invalid Indian mobile number" in en_dict["error_message"]
    assert "தவறான இந்திய கைபேசி எண்" in ta_dict["error_message"]
