"""
Pytest unit tests for SevaPath Regex Validation Engine.

Tests:
- Indian mobile phone syntax, prefixes, separators, ASCII digits, normalization
- Pragmatic email syntax, local-part length (64), domain-label length (63), total length (254)
- Email local-part case preservation and domain lowercasing
- Email whitespace policy (leading/trailing stripped, internal rejected)
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
    # Local part case must be preserved; domain must be lowercased
    ("Citizen.Name@TamilNadu.gov.in", "Citizen.Name@tamilnadu.gov.in"),
    ("User+Tag@Domain.CO.IN", "User+Tag@domain.co.in"),
    ("first_last@dept.sub.gov.in", "first_last@dept.sub.gov.in"),
    ("  citizen@tnesevai.tn.gov.in  ", "citizen@tnesevai.tn.gov.in"),
])
def test_valid_emails(valid_email, expected_normalized):
    """Verifies valid email syntax and case preservation."""
    res = RegexValidator.validate_email(valid_email)
    assert res.is_valid is True
    assert res.cleaned_value == expected_normalized
    assert res.error_message_en is None


def test_email_case_preservation_and_domain_lowercased():
    """
    CRITICAL REQUIREMENT 3:
    Preserve local part case, lowercase only the domain.
    """
    res = RegexValidator.validate_email("MyCustomUserName@SubDomain.Example.COM")
    assert res.is_valid is True
    assert res.cleaned_value == "MyCustomUserName@subdomain.example.com"


def test_email_local_part_length_boundaries():
    """
    CRITICAL REQUIREMENT 3:
    Local part length <= 64 (valid), > 64 (invalid).
    """
    # 64-char local part
    valid_local = "a" * 64 + "@example.com"
    res_valid = RegexValidator.validate_email(valid_local)
    assert res_valid.is_valid is True

    # 65-char local part
    invalid_local = "a" * 65 + "@example.com"
    res_invalid = RegexValidator.validate_email(invalid_local)
    assert res_invalid.is_valid is False
    assert "local part exceeds maximum length" in res_invalid.error_message_en


def test_email_domain_label_length_boundaries():
    """
    CRITICAL REQUIREMENT 3:
    Domain label length <= 63 (valid), > 63 (invalid).
    """
    # 63-char domain label
    valid_label = "user@" + ("a" * 63) + ".com"
    res_valid = RegexValidator.validate_email(valid_label)
    assert res_valid.is_valid is True

    # 64-char domain label
    invalid_label = "user@" + ("a" * 64) + ".com"
    res_invalid = RegexValidator.validate_email(invalid_label)
    assert res_invalid.is_valid is False
    assert "domain label exceeds maximum length" in res_invalid.error_message_en


def test_email_total_length_boundary():
    """
    CRITICAL REQUIREMENT 3:
    Total email length <= 254 (valid), > 254 (invalid).
    Each sub-part is within limits (local <= 64, labels <= 63), but total length is 260 > 254.
    """
    oversized = ("a" * 64) + "@" + ("b" * 63) + "." + ("c" * 63) + "." + ("d" * 63) + ".com"
    assert len(oversized) > 254
    res = RegexValidator.validate_email(oversized)
    assert res.is_valid is False
    assert "exceeds maximum length" in res.error_message_en


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


def test_email_whitespace_handling():
    """
    CRITICAL REQUIREMENT 3:
    Consistent whitespace policy: leading/trailing whitespace stripped and valid;
    internal whitespace rejected.
    """
    # Leading and trailing whitespace stripped cleanly
    res_clean = RegexValidator.validate_email("   citizen@example.com   ")
    assert res_clean.is_valid is True
    assert res_clean.cleaned_value == "citizen@example.com"

    # Internal whitespace rejected
    res_internal = RegexValidator.validate_email("citizen @example.com")
    assert res_internal.is_valid is False

    res_internal2 = RegexValidator.validate_email("citizen@ example.com")
    assert res_internal2.is_valid is False


def test_email_empty_and_non_string_inputs():
    """Verifies safe handling of null, empty, and non-string email inputs."""
    assert RegexValidator.validate_email(None).is_valid is False
    assert RegexValidator.validate_email("").is_valid is False
    assert RegexValidator.validate_email("   ").is_valid is False
    assert RegexValidator.validate_email(12345).is_valid is False


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
