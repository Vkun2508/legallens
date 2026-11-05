from pathlib import Path

import pytest

from legallens.preprocess import load_bytes, load_document, normalize_text, strip_running_lines
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


def test_page_break_mid_sentence_does_not_split():
    text = "1. You may cancel your subscription 3 days prior to your\n\nnext delivery date."
    assert [c.text for c in segment(text)] == [
        "You may cancel your subscription 3 days prior to your next delivery date."
    ]


def test_lowercase_line_after_abbreviation_continues_sentence():
    text = "Fees apply to purchases made in a currency other than U.S.\n\ndollars) and to cash advances."
    assert len(segment(text)) == 1


def test_list_stays_with_its_intro_across_blank_line():
    text = "You agree that you will not:\n\na. copy the Service; or\nb. resell the Service."
    assert [c.text for c in segment(text)] == [
        "You agree that you will not:\na. copy the Service; or\nb. resell the Service."
    ]


def test_wrapped_all_caps_line_is_not_a_heading():
    text = (
        "LIMITATION OF LIABILITY\n"
        "TO THE MAXIMUM EXTENT PERMITTED BY LAW, THE SERVICE IS PROVIDED AS IS\n"
        "WITHOUT WARRANTY OF ANY KIND, AND WE MAKE NO REPRESENTATION THAT THE\n"
        "SERVICE WILL BE SECURE, THAT IT WILL BE ERROR FREE, OR THAT THE SERVICE\n"
        "\n"
        "WILL NOT INFRINGE THE RIGHTS (INCLUDING, WITHOUT LIMITATION, INTELLECTUAL\n"
        "PROPERTY RIGHTS) OF ANY PERSON OR CAUSE ANY DAMAGE TO YOUR EQUIPMENT.\n"
    )
    clauses = segment(text)
    assert [(c.number, c.heading) for c in clauses] == [(None, "LIMITATION OF LIABILITY")]
    assert "THE SERVICE WILL NOT INFRINGE" in clauses[0].text


def test_short_sentence_final_line_ends_paragraph_without_blank_lines():
    text = "\n".join([
        "We collect your name, email address and payment details when you register for",
        "an account with us.",
        "You must contact us about billing errors in writing, and you must do so:",
        "• Within 60 days after the error appeared on your statement.",
        "• At least 3 business days before a scheduled payment.",
        "You can ask us to delete your account at any time by contacting customer support",
        "through the help centre.",
    ])
    clauses = segment(text)
    assert len(clauses) == 3
    assert clauses[1].text.splitlines() == [
        "You must contact us about billing errors in writing, and you must do so:",
        "• Within 60 days after the error appeared on your statement.",
        "• At least 3 business days before a scheduled payment.",
    ]


def test_run_in_labels_start_clauses():
    text = "\n".join([
        "6. RESEARCH FEE: You agree to pay $3 for each copy of a sales slip you request.",
        "Default: We may close your Account if you fail to pay any amount when it is due.",
        "Use of the Card. You may use the Card to obtain goods and services from merchants.",
        "Calculation of Monthly Periodic Rate:",
        "A. The monthly rate is the annual rate divided by 12.",
    ])
    assert _summary(text) == [
        ("6", None),
        (None, "Default"),
        (None, "Use of the Card"),
        (None, "Calculation of Monthly Periodic Rate"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "ANY KIND. WITHOUT LIMITING THE FOREGOING, WE DISCLAIM ALL WARRANTIES.",
        "Agreed. We will deliver the goods within ten business days.",
        "Please read carefully: These Terms are a binding agreement.",
    ],
)
def test_sentences_are_not_run_in_labels(text):
    assert _summary(text) == [(None, None)]


def test_strip_running_lines_removes_repeated_headers_and_footers():
    bodies = ["We may share data.", "Fees renew monthly.", "You may cancel.", "Disputes go to arbitration."]
    pages = [f"703762.6\n{body}\nAcme Terms - {n}" for n, body in enumerate(bodies, 1)]
    assert strip_running_lines(pages) == bodies


def test_normalize_recovers_from_section_numbers_lost_as_control_characters():
    raw = "\x00\x00. Privacy\nWe never sell your data."
    assert normalize_text(raw) == "Privacy\nWe never sell your data."


def test_load_bytes_matches_load_document():
    assert load_bytes(SAMPLE.read_bytes(), ".TXT") == load_document(SAMPLE)
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_bytes(b"", ".docx")


def test_empty_text():
    assert segment("") == []
    assert segment("\n\n  \n") == []


CONTACT_BLOCK = (
    "Privacy Notice\n\nLast updated: 1 May 2026\n\nComplaints\n\n"
    "If you have a complaint, contact our officer:\n\n"
    "Dhanya Bhatt\n\nAcme Private Limited\n\nReg Office: 12 MG Road, Bengaluru 560001\n\n"
    "DPO\n\nMR. A Kumar\n\nE-mail: dpo@example.in\n"
)


def test_short_lines_that_head_nothing_are_kept_as_text():
    # Contact blocks are short capitalised lines that look like headings; before this fix a run of
    # them, or any at the end of the text, vanished from the clauses (and so from every check).
    clauses = segment(CONTACT_BLOCK)
    assert [c.text for c in clauses] == [
        "If you have a complaint, contact our officer:",
        "Dhanya Bhatt",
        "Reg Office: 12 MG Road, Bengaluru 560001",
        "DPO\nMR. A Kumar\nE-mail: dpo@example.in",
    ]
    block = clauses[-1]
    assert CONTACT_BLOCK[block.start : block.end] == "DPO\n\nMR. A Kumar\n\nE-mail: dpo@example.in"


def test_title_block_before_the_first_clause_stays_headings():
    clauses = segment(CONTACT_BLOCK)
    assert clauses[0].heading == "Complaints"
    assert not any("Privacy Notice" in c.text or "Last updated" in c.text for c in clauses)
