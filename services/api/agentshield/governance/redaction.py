"""Secret detection and masking.

Seven detectors, applied to every prompt before it reaches a model and before
anything is persisted. The guarantee this file is responsible for:

    A raw secret value never appears in an event payload, never in a log
    line, never in a structured log field, and never on the wire to the
    frontend.

The original prompt goes to the blob store under `raw/{task_id}/prompt.json`,
and every read of that key emits `audit.raw_access`. That is the only place a
raw value exists after Gate 1.

The mask is `<<REDACTED:aws_access_key:a3f9>>`, where the suffix is the first
four hex of the value's SHA-256. Enough to correlate repeats -- the same key
pasted twice produces the same suffix, which is how you spot a leaked
credential circulating -- without revealing anything about the value itself.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from re import Pattern

from agentshield.domain.models import SensitiveFinding


@dataclass(frozen=True)
class Detector:
    name: str
    pattern: Pattern[str]
    risk_bump: int = 0
    """Added to the static risk term when this detector fires.

    Only the private-key block carries one. Pasting a private key into a
    prompt is categorically different from pasting an API token: there is no
    innocent version of it.
    """


# `docs/DESIGN.md` section 5.3. Order matters only for overlapping matches --
# the longest match at a given offset wins, handled in `scan()`.
DETECTORS: tuple[Detector, ...] = (
    Detector("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    Detector(
        "aws_secret_key",
        re.compile(r"(?i)aws_secret[^\n]{0,20}[A-Za-z0-9/+=]{40}"),
    ),
    Detector(
        "private_key",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
        risk_bump=25,
    ),
    Detector(
        "api_token",
        re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    ),
    Detector(
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    Detector("password_assignment", re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{6,}")),
    Detector(
        "connection_string",
        re.compile(r"(?i)(postgres|mysql|mongodb|redis)(\+srv)?://[^\s]+:[^\s]+@"),
    ),
)


def fingerprint(value: str) -> str:
    """First four hex of SHA-256. Correlates repeats, reveals nothing."""
    return hashlib.sha256(value.encode()).hexdigest()[:4]


def mask_for(detector: str, value: str) -> str:
    return f"<<REDACTED:{detector}:{fingerprint(value)}>>"


@dataclass
class ScanResult:
    findings: list[SensitiveFinding]
    redacted_text: str
    risk_bump: int = 0

    @property
    def clean(self) -> bool:
        return not self.findings


def scan(text: str, *, enabled: bool = True) -> ScanResult:
    """Find and mask every secret in a prompt.

    Offsets on the returned findings refer to the **original** text, so an
    audit can line a finding up against the blob-stored original. The
    redacted text is rebuilt in one pass, back to front, so earlier offsets
    stay valid while later ones are replaced.
    """
    if not enabled or not text:
        return ScanResult(findings=[], redacted_text=text)

    spans: list[tuple[int, int, str, str]] = []
    for detector in DETECTORS:
        for match in detector.pattern.finditer(text):
            spans.append((match.start(), match.end(), detector.name, match.group(0)))

    if not spans:
        return ScanResult(findings=[], redacted_text=text)

    # Overlapping detectors are common -- a connection string contains a
    # password assignment. Keep the widest match at each start offset and drop
    # anything it swallows, so a value is masked once rather than nested.
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    kept: list[tuple[int, int, str, str]] = []
    cursor = -1
    for start, end, name, value in spans:
        if start >= cursor:
            kept.append((start, end, name, value))
            cursor = end

    findings = [
        SensitiveFinding(
            detector=name,
            masked=mask_for(name, value),
            offset=start,
            length=end - start,
        )
        for start, end, name, value in kept
    ]

    out = text
    for start, end, name, value in reversed(kept):
        out = out[:start] + mask_for(name, value) + out[end:]

    bumps = {d.name: d.risk_bump for d in DETECTORS}
    risk_bump = sum(bumps.get(f.detector, 0) for f in findings)

    return ScanResult(findings=findings, redacted_text=out, risk_bump=risk_bump)


def to_event_findings(findings: list[SensitiveFinding]) -> list[dict[str, str]]:
    """The only shape a finding may take in an event payload.

    Detector name and mask. No offset, no length, no value -- an offset plus
    a length is a decent start on reconstructing what was there.
    """
    return [{"detector": f.detector, "masked": f.masked} for f in findings]


def raw_prompt_key(task_id: str) -> str:
    return f"raw/{task_id}/prompt.json"
