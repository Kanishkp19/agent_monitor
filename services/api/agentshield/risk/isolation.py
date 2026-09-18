"""IsolationForest over the session vector.

Unsupervised, by design and not by convenience. `docs/01-PRD.md` is explicit:
training on the adversarial label would make every precision and recall number
meaningless, because the model would have been told the answer. Labels exist
for evaluation only, and this module has no path to them -- it reads sessions
through `RiskScopedDocStore` like everything else in `risk/`.

Raw IsolationForest scores are unbounded and unintuitive. They are converted
to 0-100 by percentile rank within the training distribution, so "82" means
"more anomalous than 82% of observed sessions" rather than an arbitrary
decision-function value.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import numpy.typing as npt

from agentshield.risk.features import FEATURE_NAMES

logger = logging.getLogger(__name__)

MIN_TRAINING_SESSIONS = 50


class AnomalyDetector:
    """Trained per simulated day on the trailing window."""

    def __init__(
        self,
        *,
        n_estimators: int = 200,
        contamination: float = 0.03,
        seed: int = 20260918,
    ) -> None:
        self._n_estimators = n_estimators
        self._contamination = contamination
        self._seed = seed
        self._model: Any = None
        self._scaler: Any = None
        self._training_scores: npt.NDArray[np.float64] | None = None

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def train(self, vectors: list[list[float]]) -> dict[str, Any]:
        """Fit on observed sessions. Seeded, so two runs agree.

        Below `MIN_TRAINING_SESSIONS` it declines to fit rather than producing
        a model that would confidently score noise -- the composite simply
        runs on its other two terms until there is enough history.
        """
        if len(vectors) < MIN_TRAINING_SESSIONS:
            logger.info(
                "not enough sessions to train",
                extra={"have": len(vectors), "need": MIN_TRAINING_SESSIONS},
            )
            return {"trained": False, "sessions": len(vectors)}

        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

        data = np.asarray(vectors, dtype=float)

        self._scaler = StandardScaler()
        scaled = self._scaler.fit_transform(data)

        self._model = IsolationForest(
            n_estimators=self._n_estimators,
            contamination=self._contamination,
            random_state=self._seed,
            n_jobs=-1,
        )
        self._model.fit(scaled)

        # Keep the training distribution so scores can be percentile-ranked
        # against it rather than reported as raw decision-function values.
        self._training_scores = np.sort(self._model.score_samples(scaled))

        return {
            "trained": True,
            "sessions": len(vectors),
            "features": len(FEATURE_NAMES),
            "estimators": self._n_estimators,
            "contamination": self._contamination,
        }

    def score(self, vector: list[float]) -> int:
        """0-100, where higher is more anomalous.

        Percentile rank within the training distribution. `score_samples`
        returns *higher* for more normal, so the rank is inverted.
        """
        if not self.is_trained or self._training_scores is None:
            return 0

        scaled = self._scaler.transform(np.asarray([vector], dtype=float))
        raw = float(self._model.score_samples(scaled)[0])

        position = int(np.searchsorted(self._training_scores, raw))
        percentile = position / max(1, len(self._training_scores))
        return int(round((1.0 - percentile) * 100))

    def score_many(self, vectors: list[list[float]]) -> list[int]:
        if not self.is_trained or self._training_scores is None:
            return [0] * len(vectors)

        scaled = self._scaler.transform(np.asarray(vectors, dtype=float))
        raw = self._model.score_samples(scaled)
        positions = np.searchsorted(self._training_scores, raw)
        percentiles = positions / max(1, len(self._training_scores))
        return [int(round((1.0 - p) * 100)) for p in percentiles]

    def feature_contributions(self, vector: list[float]) -> dict[str, float]:
        """How far each feature sits from the training mean, in sigmas.

        Not a true Shapley attribution -- it is a cheap, honest proxy used
        only to order features for display. The authoritative explanation
        comes from `scoring.top_factors`, which is rule-based and therefore
        actually explainable.
        """
        if self._scaler is None:
            return {}
        scaled = self._scaler.transform(np.asarray([vector], dtype=float))[0]
        return {
            name: round(float(abs(value)), 4)
            for name, value in zip(FEATURE_NAMES, scaled, strict=False)
        }
