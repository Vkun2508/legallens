from pathlib import Path

import pytest

from legallens.preprocess import load_document, normalize_text
from legallens.segmentation import segment

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "samples" / "sample_tos.txt"


def _summary(text):
    return [(c.number, c.heading) for c in segment(text)]


def test_sample_document_structure():
    clauses = segment(load_document(SAMPLE))
    assert [(c.number, c.heading) for c in clauses] == [
        # Known baseline weakness: the date line is taken as the preamble's heading.
        (None, "Last updated: 1 March 2026"),
        ("1.1", "Definitions"),
        ("1.2", "Definitions"),
        ("2.1", "Fees and Automatic Renewal"),
        ("2.2", "Fees and Automatic Renewal"),
        ("3", "Data Sharing"),
        ("4", "Limitation of Liability"),
        (None, "DISPUTE RESOLUTION"),
        (None, "DISPUTE RESOLUTION"),
    ]


def test_wrapped_lines_are_joined_and_number_prefix_removed():
    clauses = segment(load_document(SAMPLE))
    renewal = clauses[3]
    assert renewal.text.startswith("Your Subscription renews automatically at the end of each billing")
    assert "\n" not in renewal.text


def test_wrapped_line_starting_with_number_is_not_a_clause():
    # "30 days before" in clause 2.2 starts a line but must not split it.
    clauses = segment(load_document(SAMPLE))
    assert "notified by email 30 days before they apply." in clauses[4].text


def test_subitems_stay_in_parent_on_separate_lines():
    data_sharing = segment(load_document(SAMPLE))[5]
    assert data_sharing.text.splitlines()[1:4] == [
        "(a) advertising partners, to show you relevant offers;",
        "(b) analytics providers; and",
        "(c) any successor company in the event of a merger.",
    ]
    assert data_sharing.text.endswith("in your account settings.")


def test_offsets_cover_clause_span():
    text = normalize_text(SAMPLE.read_text(encoding="utf-8"))
    clause = segment(text)[1]
    assert text[clause.start : clause.end].startswith('1.1 "Service" means')
    assert text[clause.start : clause.end].endswith("related content.")


@pytest.mark.parametrize(
    "line, number",
    [
        ("Section 4 Termination of the Service by either party is allowed.", "4"),
        ("Article IV. The Company may assign this Agreement.", "IV"),
        ("§ 5 The Customer must pay all invoices.", "5"),
        ("7) The Customer must pay all invoices.", "7"),
        ("3.2.1 The Customer must pay all invoices.", "3.2.1"),
    ],
)
def test_numbering_styles(line, number):
    assert _summary(line) == [(number, None)]


def test_numbers_inside_sentences_do_not_split():
    text = "Your account may hold up to\n2.5 million records. Fees are\n12. Thousand words is plenty."
    assert len(segment(text)) == 1  # second break follows "are", not a sentence end


def test_section_keyword_mid_sentence_is_text():
    text = "1. The rules in\nSection 4 of this Agreement apply."
    assert _summary(text) == [("1", None)]


def test_bare_number_line_takes_title_from_next_line():
    text = "Section 4\nTermination\n\nEither party may end this Agreement with notice."
    assert _summary(text) == [("4", "Termination")]


def test_top_level_clause_resets_unrelated_heading():
    text = "1. Fees\n1.1 You pay monthly.\n2. You may cancel at any time by contacting us."
    assert _summary(text) == [("1.1", "Fees"), ("2", None)]


def test_unnumbered_paragraphs_are_separate_clauses():
    text = "We collect your email address.\n\nWe never sell your data."
    assert [c.text for c in segment(text)] == [
        "We collect your email address.",
        "We never sell your data.",
    ]


def test_one_paragraph_per_line_without_blank_lines():
    long_a = "We collect your name, email address and payment details when you register " * 2
    long_b = "We may share aggregated usage statistics with our partners for analytics purposes " * 2
    assert len(segment(f"{long_a.strip()}.\n{long_b.strip()}.")) == 2


def test_normalize_removes_page_numbers_and_rejoins_hyphenated_words():
    raw = "1. You must accept the agree-\nment terms.\nPage 3 of 10\n\r\n\n\n2. Next clause."
    assert normalize_text(raw) == "1. You must accept the agreement terms.\n\n2. Next clause."


def test_empty_text():
    assert segment("") == []
    assert segment("\n\n  \n") == []
