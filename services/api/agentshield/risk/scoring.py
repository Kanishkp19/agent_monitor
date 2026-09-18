"""The composite risk score, and the plain-language explanation of it.

    risk = 0.35*static + 0.40*behavioural + 0.25*ml

Three terms, because each covers the other two's blind spot:

  * **Static** works from the very first event, before any history exists. An
    intern attempting a production deploy scores 95 here whether it is their
    first day or their five hundredth.
  * **Behavioural** catches the person who is doing normal things at abnormal
    volume, in abnormal places, at abnormal hours.
  * **ML** catches the combination nobody wrote a rule for.

**The wording of every explanation lives in this file.** Not in the API layer,
not in the client. `/risk/employees/{id}/explain`, the employee drawer and
`/control/risk` all render the same strings, so the system can never describe
the same factor three different ways to three different people.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from agentshield.domain.enums import Role, Sensitivity
from agentshield.domain.models import RiskFactor

WEIGHTS = {"static": 0.35, "behavioural": 0.40, "ml": 0.25}

# Per-feature weight inside the behavioural term. Reaching for credentials and
# reaching for the outside weigh most, because both are deliberate acts that
# have no accidental version.
FEATURE_WEIGHTS: dict[str, float] = {
    "tokens_z": 1.0,
    "cost_z": 0.8,
    "offhours_frac": 1.2,
    "repo_entropy": 1.0,
    "novel_repo_count": 1.3,
    "secret_attempts": 2.0,
    "prod_attempts": 1.4,
    "block_rate": 1.5,
    "review_rate": 0.6,
    "tool_diversity": 0.5,
    "session_len_z": 0.7,
    "external_attempts": 2.0,
}

# Static sensitivity by role and action class. Deterministic and explainable:
# an operator can read this table and predict the number.
_ROLE_TRUST: dict[Role, float] = {
    Role.CEO: 0.5,
    Role.SENIOR_MANAGER: 0.6,
    Role.MANAGER: 0.6,
    Role.DEVOPS: 0.4,
    Role.SENIOR_ENGINEER: 0.7,
    Role.ENGINEER: 1.0,
    Role.INTERN: 1.5,
}

_SENSITIVITY_BASE: dict[Sensitivity, int] = {
    Sensitivity.LOW: 5,
    Sensitivity.MEDIUM: 25,
    Sensitivity.HIGH: 55,
    Sensitivity.CRITICAL: 85,
}


@dataclass
class CompositeScore:
    score: int
    static: int
    behavioural: int
    ml: int
    confidence: str
    top_factors: list[RiskFactor]


def static_score(
    *, role: Role, sensitivity: Sensitivity, prod_access: str, is_production: bool
) -> int:
    """Role x action sensitivity. Works from the first event.

    An intern attempting a production deploy scores near the ceiling here
    regardless of history, which is the point: some things are wrong on day
    one and waiting for a baseline to say so would be absurd.
    """
    base = _SENSITIVITY_BASE.get(sensitivity, 5)
    trust = _ROLE_TRUST.get(role, 1.0)

    score = base * trust
    if is_production and prod_access == "none":
        score *= 1.4

    return int(max(0, min(100, round(score))))


def behavioural_score(features: dict[str, float]) -> int:
    """Weighted, clipped z-scores through a sigmoid.

        100 * sigmoid( sum(w*clip(z,0,4)) / sum(w) - 1.0 )

    Clipping at 4 stops one extreme feature saturating the term: someone with
    a 40-sigma token spike and nothing else should look suspicious, not
    maximally suspicious.
    """
    if not features:
        return 0

    weighted = 0.0
    total_weight = 0.0

    for name, weight in FEATURE_WEIGHTS.items():
        value = float(features.get(name, 0.0))
        weighted += weight * _clip(_to_z_like(name, value), 0.0, 4.0)
        total_weight += weight

    if total_weight <= 0:
        return 0

    normalised = weighted / total_weight - 1.0
    return int(round(100 / (1 + math.exp(-normalised * 2.2))))


def composite(
    *,
    static: int,
    behavioural: int,
    ml: int,
    features: dict[str, float],
    baseline: dict[str, dict[str, float]],
    is_low_confidence: bool,
) -> CompositeScore:
    blended = WEIGHTS["static"] * static + WEIGHTS["behavioural"] * behavioural + WEIGHTS["ml"] * ml
    score = int(max(0, min(100, round(blended))))

    return CompositeScore(
        score=score,
        static=static,
        behavioural=behavioural,
        ml=ml,
        confidence="low" if is_low_confidence else "normal",
        top_factors=top_factors(features, baseline),
    )


def top_factors(
    features: dict[str, float], baseline: dict[str, dict[str, float]], limit: int = 3
) -> list[RiskFactor]:
    """The three features contributing most, phrased for a human.

    "5.8x his normal token usage" rather than "tokens_z = 3.9". The raw
    feature name is kept on the object for anyone who wants it, but the
    explanation is what every surface renders.
    """
    contributions: list[tuple[str, float, float]] = []
    total = 0.0

    for name, weight in FEATURE_WEIGHTS.items():
        value = float(features.get(name, 0.0))
        z = _to_z_like(name, value)
        contribution = weight * _clip(z, 0.0, 4.0)
        if contribution > 0:
            contributions.append((name, value, contribution))
            total += contribution

    contributions.sort(key=lambda c: -c[2])

    factors: list[RiskFactor] = []
    for name, value, contribution in contributions[:limit]:
        factors.append(
            RiskFactor(
                feature=name,
                value=round(value, 4),
                z=round(_to_z_like(name, value), 2),
                contribution=round(contribution / total, 4) if total else 0.0,
                explanation=explain(name, value, baseline.get(name)),
            )
        )
    return factors


def explain(feature: str, value: float, stats: dict[str, float] | None) -> str:
    """Plain language for one feature. The single source for this wording."""
    mean = float(stats.get("mean", 0.0)) if stats else 0.0

    if feature == "tokens_z":
        multiple = _multiple(value)
        return f"{multiple} their normal token usage" if multiple else "Elevated token usage"

    if feature == "cost_z":
        multiple = _multiple(value)
        return f"{multiple} their normal spend" if multiple else "Elevated spend"

    if feature == "offhours_frac":
        return f"{round(value * 100)}% of activity outside their working hours"

    if feature == "repo_entropy":
        return "Activity spread across unusually many repositories"

    if feature == "novel_repo_count":
        count = int(value)
        noun = "repository" if count == 1 else "repositories"
        return f"Touched {count} {noun} never used before"

    if feature == "secret_attempts":
        count = int(value)
        noun = "attempt" if count == 1 else "attempts"
        return f"{count} blocked secret-file {noun}"

    if feature == "prod_attempts":
        count = int(value)
        return f"{count} action(s) targeting production"

    if feature == "block_rate":
        return f"{round(value * 100)}% of actions were blocked by policy"

    if feature == "review_rate":
        return f"{round(value * 100)}% of actions needed approval"

    if feature == "tool_diversity":
        return "Used an unusually wide range of tools"

    if feature == "session_len_z":
        multiple = _multiple(value)
        return f"Sessions {multiple} their usual length" if multiple else "Long sessions"

    if feature == "external_attempts":
        count = int(value)
        noun = "attempt" if count == 1 else "attempts"
        return f"{count} outbound {noun} to non-allowlisted hosts"

    return f"{feature} at {round(value, 2)} (baseline {round(mean, 2)})"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _to_z_like(name: str, value: float) -> float:
    """Put every feature on a comparable scale.

    The z-scored features already are. Counts and fractions are mapped onto a
    rough equivalent so one weighted sum is meaningful -- a raw count of 4
    secret attempts must not be compared directly against a z of 4.
    """
    if name.endswith("_z"):
        return value
    if name in ("offhours_frac", "block_rate", "review_rate", "tool_diversity"):
        return value * 4.0
    if name == "repo_entropy":
        return value * 1.5
    # Counts: each occurrence is worth roughly one sigma, capped by the clip.
    return value


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _multiple(z: float) -> str | None:
    """Turn a z-score into the phrasing an operator actually uses.

    People say "five times normal", not "three sigma". Below 1.5 sigma there
    is no honest multiple to quote, so the caller falls back to a plain
    phrase.
    """
    if z < 1.5:
        return None
    approx = 1.0 + z * 1.2
    return f"{approx:.1f}x"


def blended_weights(settings: Any) -> dict[str, float]:
    """Read the weights from settings, so the Control Center can show them."""
    return {
        "static": float(getattr(settings, "risk_weight_static", WEIGHTS["static"])),
        "behavioural": float(getattr(settings, "risk_weight_behavioural", WEIGHTS["behavioural"])),
        "ml": float(getattr(settings, "risk_weight_ml", WEIGHTS["ml"])),
    }
