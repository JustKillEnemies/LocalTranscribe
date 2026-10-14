"""Exact reference-based metrics; never use corrected MANUAL text as hypothesis."""

import unicodedata
from collections.abc import Sequence

NORMALIZATION = "nfc-casefold-whitespace-v1"


def normalize(text: str) -> str:
    """NFC, casefold and collapsed whitespace; retain punctuation, digits and ё."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def edit_distance(reference: Sequence, hypothesis: Sequence, *, max_cells: int = 25_000_000) -> int:
    """Levenshtein distance with bounded workspace and explicit compute budget."""
    start = 0
    while start < min(len(reference), len(hypothesis)) and reference[start] == hypothesis[start]:
        start += 1
    reference, hypothesis = reference[start:], hypothesis[start:]
    end = 0
    while (
        end < min(len(reference), len(hypothesis)) and reference[-1 - end] == hypothesis[-1 - end]
    ):
        end += 1
    if end:
        reference, hypothesis = reference[:-end], hypothesis[:-end]
    if len(reference) * len(hypothesis) > max_cells:
        raise ValueError(
            "Quality comparison exceeds compute budget; use aligned smaller references"
        )
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(hypothesis, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != actual))
            )
        previous = current
    return previous[-1]


def quality_metrics(reference: str, hypothesis: str) -> dict[str, float | int | str]:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        raise ValueError("A nonempty human reference is required for WER/CER")
    words = ref.split()
    word_errors = edit_distance(words, hyp.split())
    character_errors = edit_distance(ref, hyp)
    return {
        "normalization": NORMALIZATION,
        "reference_words": len(words),
        "reference_characters": len(ref),
        "word_errors": word_errors,
        "character_errors": character_errors,
        "wer": word_errors / len(words),
        "cer": character_errors / len(ref),
    }
