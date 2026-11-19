"""
SevaPath Reusable Regular Expression Validation Engine.

Provides strict, secure syntax and format validation for civic inputs:
- Indian mobile phone numbers (ASCII digit [0-9] matching, TRAI 6-9 series, standardized prefixes)
- Pragmatic email syntax validation (RFC-aligned structure, no consecutive dots)

DISCLAIMER:
Syntax and format verification only. SevaPath does not verify government database
existence, document authenticity or citizen eligibility.
"""

import re
from typing import Optional, Dict, Any


CIVIC_VALIDATION_DISCLAIMER = (
    "Syntax and format verification only. SevaPath does not verify government "
    "database existence, document authenticity or citizen eligibility."
)


class ValidationResult:
    """Represents the structured result of a regular expression validation check."""

    def __init__(
        self,
        is_valid: bool,
        field_type: str,
        cleaned_value: Optional[str] = None,
        error_message_en: Optional[str] = None,
        error_message_ta: Optional[str] = None,
        rule_description: str = "",
        disclaimer: str = CIVIC_VALIDATION_DISCLAIMER
    ):
        self.is_valid = is_valid
        self.field_type = field_type
        self.cleaned_value = cleaned_value
        self.error_message_en = error_message_en
        self.error_message_ta = error_message_ta
        self.rule_description = rule_description
        self.disclaimer = disclaimer

    def to_dict(self, lang: str = "en") -> Dict[str, Any]:
        """Serializes result to a dictionary suitable for API responses."""
        error_msg = self.error_message_ta if lang == "ta" else self.error_message_en
        return {
            "is_valid": self.is_valid,
            "field_type": self.field_type,
            "cleaned_value": self.cleaned_value,
            "error_message": error_msg,
            "rule_description": self.rule_description,
            "disclaimer": self.disclaimer,
        }


class RegexValidator:
    """
    Reusable, production-grade Regular Expression validation engine.
    
    Design principles:
    - Independent of DFA engine.
    - Explicit ASCII digit matching [0-9] (prevents non-ASCII / Unicode digit acceptance).
    - Hard length boundaries checked before regex evaluation (ReDoS protection).
    - Never silently removes arbitrary invalid characters.
    - Sanitizes error output to avoid echoing raw sensitive inputs.
    """

    # Maximum length limits to prevent ReDoS on oversized payloads
    MAX_PHONE_INPUT_LENGTH = 25
    MAX_EMAIL_INPUT_LENGTH = 254

    # Precompiled Regular Expressions using ASCII [0-9]
    # Phone: Optional prefix (+91, 91, or 0) followed by optional single space/hyphen,
    # then 10 digits starting with 6-9, with an optional single space/hyphen after the 5th digit.
    # Note: Separators must not be duplicated or arbitrary.
    _PHONE_PATTERN = re.compile(
        r"^(?:(?:\+91|91|0)[ -]?)?[6-9][0-9]{4}[ -]?[0-9]{5}$"
    )

    # Email: Standard pragmatic web syntax (RFC 5321/5322 pragmatic aligned).
    # Disallows consecutive dots in local part or domain. Requires valid TLD >= 2 chars.
    _EMAIL_LOCAL_PART = r"[a-zA-Z0-9_+-]+(?:\.[a-zA-Z0-9_+-]+)*"
    _EMAIL_DOMAIN_LABEL = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?"
    _EMAIL_PATTERN = re.compile(
        r"^" + _EMAIL_LOCAL_PART + r"@" + r"(?:" + _EMAIL_DOMAIN_LABEL + r"\.)+" + r"[a-zA-Z]{2,}$"
    )

    @classmethod
    def validate_phone(cls, value: Any) -> ValidationResult:
        """
        Validates an Indian mobile phone number.
        
        Rules:
        - Must be a non-empty string of at most 25 characters.
        - Must start with valid Indian mobile prefix digit (6, 7, 8, or 9).
        - May have optional leading prefix: '+91', '91', or '0'.
        - Allows at most one standard space or hyphen delimiter after prefix and/or 5th digit.
        - Exactly 10 ASCII numeric digits [0-9]. Unicode digits are rejected.
        
        Normalization:
        - If valid, normalized to canonical 10-digit string: e.g. '9876543210'.
        """
        rule_desc = "Indian 10-digit mobile number starting with 6-9, with optional +91, 91, or 0 prefix."

        if value is None:
            return ValidationResult(
                is_valid=False,
                field_type="phone",
                error_message_en="Phone number cannot be null or empty.",
                error_message_ta="தொலைபேசி எண் காலியாக இருக்கக்கூடாது.",
                rule_description=rule_desc
            )

        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                field_type="phone",
                error_message_en="Phone number must be a string.",
                error_message_ta="தொலைபேசி எண் எழுத்து வடிவில் இருக்க வேண்டும்.",
                rule_description=rule_desc
            )

        trimmed = value.strip()
        if not trimmed:
            return ValidationResult(
                is_valid=False,
                field_type="phone",
                error_message_en="Phone number cannot be empty.",
                error_message_ta="தொலைபேசி எண் காலியாக இருக்கக்கூடாது.",
                rule_description=rule_desc
            )

        if len(trimmed) > cls.MAX_PHONE_INPUT_LENGTH:
            return ValidationResult(
                is_valid=False,
                field_type="phone",
                error_message_en=f"Phone number exceeds maximum length of {cls.MAX_PHONE_INPUT_LENGTH} characters.",
                error_message_ta=f"தொலைபேசி எண் அதிகபட்ச நீளமான {cls.MAX_PHONE_INPUT_LENGTH} எழுத்துக்களை விட அதிகமாக உள்ளது.",
                rule_description=rule_desc
            )

        # Match strictly against precompiled ASCII pattern
        if not cls._PHONE_PATTERN.match(trimmed):
            return ValidationResult(
                is_valid=False,
                field_type="phone",
                error_message_en="Invalid Indian mobile number format. Expected 10 digits starting with 6-9 (optional +91/91/0 prefix).",
                error_message_ta="தவறான இந்திய கைபேசி எண். 6-9 இல் தொடங்கும் 10 இலக்க எண்ணாக இருக்க வேண்டும் (விருப்பத் தேர்வு +91/91/0 முன்னொட்டு).",
                rule_description=rule_desc
            )

        # Normalization: Extract only the 10 core ASCII digits
        # Since pattern matched, stripping non-digit prefix characters gives exact trailing 10 digits.
        digits_only = "".join(c for c in trimmed if "0" <= c <= "9")
        normalized = digits_only[-10:]

        return ValidationResult(
            is_valid=True,
            field_type="phone",
            cleaned_value=normalized,
            rule_description=rule_desc
        )

    @classmethod
    def validate_email(cls, value: Any) -> ValidationResult:
        """
        Validates an email address syntax.
        
        Rules:
        - Must be a non-empty string of at most 254 characters (RFC 5321 limit).
        - Local part allows letters, numbers, and ., _, +, - (no consecutive dots).
        - Domain requires valid labels and a minimum 2-character TLD.
        - Does NOT claim to verify mailbox existence.
        
        Normalization:
        - If valid, lowercased and stripped of leading/trailing whitespace.
        """
        rule_desc = "Standard email format (username@domain.tld, max 254 characters)."

        if value is None:
            return ValidationResult(
                is_valid=False,
                field_type="email",
                error_message_en="Email address cannot be null or empty.",
                error_message_ta="மின்னஞ்சல் முகவரி காலியாக இருக்கக்கூடாது.",
                rule_description=rule_desc
            )

        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                field_type="email",
                error_message_en="Email address must be a string.",
                error_message_ta="மின்னஞ்சல் முகவரி எழுத்து வடிவில் இருக்க வேண்டும்.",
                rule_description=rule_desc
            )

        trimmed = value.strip()
        if not trimmed:
            return ValidationResult(
                is_valid=False,
                field_type="email",
                error_message_en="Email address cannot be empty.",
                error_message_ta="மின்னஞ்சல் முகவரி காலியாக இருக்கக்கூடாது.",
                rule_description=rule_desc
            )

        if len(trimmed) > cls.MAX_EMAIL_INPUT_LENGTH:
            return ValidationResult(
                is_valid=False,
                field_type="email",
                error_message_en=f"Email address exceeds maximum length of {cls.MAX_EMAIL_INPUT_LENGTH} characters.",
                error_message_ta=f"மின்னஞ்சல் அதிகபட்ச நீளமான {cls.MAX_EMAIL_INPUT_LENGTH} எழுத்துக்களை விட அதிகமாக உள்ளது.",
                rule_description=rule_desc
            )

        # Match strictly against precompiled pattern
        if not cls._EMAIL_PATTERN.match(trimmed):
            return ValidationResult(
                is_valid=False,
                field_type="email",
                error_message_en="Invalid email address syntax (e.g. citizen@example.com).",
                error_message_ta="தவறான மின்னஞ்சல் முகவரி வடிவம் (எ.கா: citizen@example.com).",
                rule_description=rule_desc
            )

        normalized = trimmed.lower()

        return ValidationResult(
            is_valid=True,
            field_type="email",
            cleaned_value=normalized,
            rule_description=rule_desc
        )

    @classmethod
    def validate_format(cls, field_type: str, value: Any) -> ValidationResult:
        """
        Dispatches validation by field_type string.
        
        Supported types: 'phone', 'email'
        Deferred types (e.g. CAN, ration card) are safely rejected with explicit explanation.
        """
        if field_type == "phone":
            return cls.validate_phone(value)
        elif field_type == "email":
            return cls.validate_email(value)
        elif field_type in ("can_number", "ration_card", "acknowledgment_number"):
            return ValidationResult(
                is_valid=False,
                field_type=field_type,
                error_message_en=f"Validation for '{field_type}' is deferred pending official government format documentation.",
                error_message_ta=f"'{field_type}' சரிபார்ப்பு அதிகாரப்பூர்வ அரசு ஆவண விவரக்குறிப்பு வரும் வரை நிறுத்தி வைக்கப்பட்டுள்ளது.",
                rule_description=f"Deferred identifier: {field_type}"
            )
        else:
            return ValidationResult(
                is_valid=False,
                field_type=str(field_type),
                error_message_en=f"Unsupported validation field type: '{field_type}'. Supported types: 'phone', 'email'.",
                error_message_ta=f"ஆதரிக்கப்படாத சரிபார்ப்பு புலம்: '{field_type}'. ஆதரிக்கப்படும் புலங்கள்: 'phone', 'email'.",
                rule_description="Supported types: 'phone', 'email'."
            )
