"""L4: Semantic similarity evaluator using sentence-transformers (optional).

Uses a lightweight multilingual MiniLM model to compute cosine similarity
between reference text and converted Markdown.  The model is lazily loaded
on first use to avoid pulling in heavy dependencies when L4 is disabled.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from eval.metrics.normalize import clamp_100

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_MD_TAG_RE = re.compile(r"[#*`_~\[\]()>|-]")


def _strip_markup(text: str) -> str:
    """Strip HTML tags and Markdown markup to get plain text."""
    text = _TAG_RE.sub("", text)
    text = _MD_TAG_RE.sub("", text)
    return text.strip()


class L4SemanticEvaluator:
    """Evaluate semantic similarity using sentence-transformers.

    :param model_name: HuggingFace model name for sentence embeddings.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self._model_name = model_name
        self._model: Any = None

    def _ensure_model(self) -> None:
        """Lazily load the sentence-transformers model."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.error(
                "sentence-transformers is not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise

        logger.info("Loading sentence-transformers model: %s", self._model_name)
        self._model = SentenceTransformer(self._model_name)

    def evaluate(self, reference_text: str, converted_md: str) -> float:
        """Compute semantic similarity score.

        :param reference_text: Reference text (may contain HTML/Markdown).
        :param converted_md: Converted Markdown output.
        :return: Similarity score (0-100, higher is better).
        """
        if not reference_text.strip() or not converted_md.strip():
            return 0.0

        self._ensure_model()

        ref_plain = _strip_markup(reference_text)
        conv_plain = _strip_markup(converted_md)

        if not ref_plain or not conv_plain:
            return 0.0

        import numpy as np

        embeddings = self._model.encode([ref_plain, conv_plain])
        sim = float(
            np.dot(embeddings[0], embeddings[1])
            / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]))
        )

        return clamp_100(sim * 100.0)
