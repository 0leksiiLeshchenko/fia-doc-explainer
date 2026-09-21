from fia_doc_explainer.quality import (
    NON_PRINTABLE_THRESHOLD,
    REPLACEMENT_CHAR,
    REPLACEMENT_CHAR_THRESHOLD,
    check_text_quality,
)

# 100-char base so that k bad chars give an exact ratio of k / 100.
BASE_LENGTH = 100


def test_empty_text_is_flagged():
    reason = check_text_quality("")

    assert reason == "Extracted text is empty"


def test_clean_text_passes():
    text = "FIA Formula One World Championship\n\tDecision of the Stewards\n" * 5

    assert check_text_quality(text) is None


def test_replacement_ratio_above_threshold_is_flagged():
    bad = int(REPLACEMENT_CHAR_THRESHOLD * BASE_LENGTH) + 1
    text = REPLACEMENT_CHAR * bad + "a" * (BASE_LENGTH - bad)

    reason = check_text_quality(text)

    assert reason is not None
    assert "replacement characters" in reason


def test_non_printable_ratio_above_threshold_is_flagged():
    bad = int(NON_PRINTABLE_THRESHOLD * BASE_LENGTH) + 1
    text = "\x00" * bad + "a" * (BASE_LENGTH - bad)

    reason = check_text_quality(text)

    assert reason is not None
    assert "non-printable characters" in reason


def test_replacement_ratio_exactly_at_threshold_passes():
    # Comparison must be strict (>), so a ratio equal to the threshold is fine.
    bad = int(REPLACEMENT_CHAR_THRESHOLD * BASE_LENGTH)
    text = REPLACEMENT_CHAR * bad + "a" * (BASE_LENGTH - bad)
    assert bad / len(text) == REPLACEMENT_CHAR_THRESHOLD

    assert check_text_quality(text) is None


def test_non_printable_ratio_exactly_at_threshold_passes():
    # Comparison must be strict (>), so a ratio equal to the threshold is fine.
    bad = int(NON_PRINTABLE_THRESHOLD * BASE_LENGTH)
    text = "\x00" * bad + "a" * (BASE_LENGTH - bad)
    assert bad / len(text) == NON_PRINTABLE_THRESHOLD

    assert check_text_quality(text) is None


# extract_text joins pages with "\n\n", so real documents always carry plenty of
# newlines and tabs. Both are non-printable per str.isprintable() and are kept
# off the non-printable count only by _ALLOWED_WHITESPACE.
def test_allowed_whitespace_is_not_counted_as_non_printable() -> None:
    page = "Decision\tDocument 42\nCar 16\tPenalty: 5 seconds"
    text = "\n\n".join([page] * 4)

    ws = sum(1 for ch in text if ch in {"\n", "\t"})
    assert ws / len(text) > NON_PRINTABLE_THRESHOLD

    assert check_text_quality(text) is None
