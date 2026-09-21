REPLACEMENT_CHAR = "\ufffd"
_ALLOWED_WHITESPACE = {"\n", "\t", " "}

REPLACEMENT_CHAR_THRESHOLD = 0.01
NON_PRINTABLE_THRESHOLD = 0.02


def check_text_quality(text: str) -> str | None:
    if not text:
        return "Extracted text is empty"

    length = len(text)

    replacement_count = text.count(REPLACEMENT_CHAR)
    replacement_ratio = replacement_count / length
    if replacement_ratio > REPLACEMENT_CHAR_THRESHOLD:
        return (
            f"Input text contains {replacement_ratio:.1%} replacement characters "
            f"(threshold {REPLACEMENT_CHAR_THRESHOLD:.0%}) — likely an encoding issue"
        )

    non_printable_count = sum(
        1 for ch in text if ch not in _ALLOWED_WHITESPACE and not ch.isprintable()
    )
    non_printable_ratio = non_printable_count / length
    if non_printable_ratio > NON_PRINTABLE_THRESHOLD:
        return (
            f"Input text contains {non_printable_ratio:.1%} non-printable characters "
            f"(threshold {NON_PRINTABLE_THRESHOLD:.0%})"
        )

    return None
