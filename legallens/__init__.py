"""LegalLens: legal clause segmentation, risk classification and simplification."""

from legallens.preprocess import load_document, normalize_text
from legallens.segmentation import Clause, segment

__all__ = ["Clause", "load_document", "normalize_text", "segment"]
