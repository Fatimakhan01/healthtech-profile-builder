"""Conservative pre-provider screening for obviously sensitive FAQ input."""

import re


_SENSITIVE_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b"
    ),
    re.compile(
        r"\b(?:MRN|medical record number|patient id|patient number)\s*[:#-]?\s*[A-Z0-9-]{4,}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:date of birth|DOB)\s*[:#-]?\s*\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:my|i have|i'm|i am|i take|my child|my parent|my spouse|"
        r"my partner|my patient)\b.{0,100}\b(?:diagnos\w*|symptom\w*|"
        r"medication\w*|prescription\w*|dosage|dose|lab results?|test results?|"
        r"condition\w*|allerg\w*|treatment\w*|medical history|health record|"
        r"pregnan\w*)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bpatient\s+(?:named|called|with|whose|#|id\b)",
        re.IGNORECASE,
    ),
)


def appears_sensitive(question: str) -> bool:
    """Detect common patient-specific details; this is not reliable PII detection."""
    return any(pattern.search(question) for pattern in _SENSITIVE_PATTERNS)
