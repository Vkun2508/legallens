"""LegalLens: legal clause segmentation, risk classification and simplification."""

from legallens.preprocess import load_bytes, load_document, normalize_text
from legallens.segmentation import Clause, segment

__all__ = ["Clause", "load_bytes", "load_document", "normalize_text", "segment"]
