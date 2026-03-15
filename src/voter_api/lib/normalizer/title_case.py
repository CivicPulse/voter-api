"""Smart title case conversion for election and candidate data.

Handles the many edge cases found in Georgia SOS data: ALL CAPS names,
generational suffixes (Jr, Sr, III), Scottish prefixes (Mc, Mac),
Irish O' prefixes, hyphenated names, and lowercase articles.
"""

from __future__ import annotations

# Generational suffixes that stay uppercase
UPPERCASE_SUFFIXES: frozenset[str] = frozenset({"III", "II", "IV"})

# Suffixes that are title-cased (not fully uppercase)
TITLE_SUFFIXES: frozenset[str] = frozenset({"Jr", "Sr"})

# Lowercase words in running text (not first word, not after hyphen)
LOWERCASE_WORDS: frozenset[str] = frozenset(
    {"of", "the", "and", "in", "for", "at", "by", "to", "de", "la", "von", "van", "a", "an"}
)

# Occupation acronyms that should remain all-caps
OCCUPATION_ACRONYMS: frozenset[str] = frozenset(
    {
        "CEO",
        "CFO",
        "CTO",
        "COO",
        "CPA",
        "LLC",
        "LLP",
        "CNC",
        "RN",
        "MD",
        "DDS",
        "JD",
        "PhD",
        "VP",
        "HR",
        "IT",
        "PC",
    }
)

# Lowercase conjunction/preposition words in occupation titles
OCCUPATION_LOWERCASE: frozenset[str] = frozenset({"and", "or", "of", "the", "in", "for", "at", "by", "to", "a", "an"})


def _apply_mc_mac_prefix(word: str) -> str:
    """Apply Scottish Mc/Mac prefix capitalisation.

    Args:
        word: A single word that may start with Mc or Mac.

    Returns:
        Word with Mc/Mac prefix and capitalised remainder.
    """
    upper = word.upper()
    if upper.startswith("MC") and len(word) > 2:
        return "Mc" + word[2:].capitalize()
    if upper.startswith("MAC") and len(word) > 3:
        # Only apply Mac capitalisation when the remainder is alphabetic
        remainder = word[3:]
        if remainder.isalpha():
            return "Mac" + remainder.capitalize()
    return word


def _title_word(word: str, *, is_occupation: bool = False) -> str:
    """Convert a single word to title case with special-case handling.

    Does NOT handle position (first word, lowercase articles). The caller
    is responsible for enforcing first-word capitalisation.

    Args:
        word: A single word (no spaces, may contain apostrophe).
        is_occupation: If True, apply occupation acronym rules.

    Returns:
        The word in appropriate case.
    """
    if not word:
        return word

    upper = word.upper()

    # Uppercase generational suffixes
    if upper in {s.upper() for s in UPPERCASE_SUFFIXES}:
        return upper

    # Title-cased suffixes (Jr, Sr)
    if upper in {s.upper() for s in TITLE_SUFFIXES}:
        return upper[0] + upper[1:].lower()

    # Occupation acronyms
    if is_occupation and upper in OCCUPATION_ACRONYMS:
        return upper

    # O' prefix (Irish)
    if upper.startswith("O'") and len(word) > 2:
        return "O'" + word[2:].capitalize()

    # Mc/Mac prefix -- only in name mode (not occupation mode)
    # Require at least 4 chars after "MC" or 4 chars after "MAC" to distinguish
    # from common words like "MACHINIST", "MACHINE", "MATCH", etc.
    if not is_occupation:
        upper = word.upper()
        if upper.startswith("MC") and len(word) > 2:
            return "Mc" + word[2:].capitalize()
        if upper.startswith("MAC") and len(word) > 4 and word[3:].isalpha():
            return "Mac" + word[3:].capitalize()

    return word.capitalize()


def smart_title_case(text: str, *, is_occupation: bool = False) -> str:
    """Convert text to title case with intelligent edge case handling.

    Handles the edge cases found in Georgia SOS data:
    - ALL CAPS names with generational suffixes (Jr, Sr, III, II, IV)
    - Scottish name prefixes (Mc, Mac)
    - Irish O' prefixes
    - Hyphenated names (each part is independently title-cased)
    - Lowercase articles and prepositions in multi-word titles
    - Single-letter middle initials (get a period appended)
    - Occupation mode: preserves known acronyms (CEO, CPA, RN, CNC, etc.)

    The function is idempotent: calling it on already-normalised text
    returns the same text unchanged.

    Args:
        text: The input text to normalise. May be ALL CAPS, mixed case,
            or already correct.
        is_occupation: If True, apply occupation-specific rules including
            acronym preservation and occupation-appropriate lowercase words.

    Returns:
        The normalised title-case text.
    """
    if not text:
        return text

    words = text.split()
    result: list[str] = []

    for i, word in enumerate(words):
        is_first = i == 0

        # Handle hyphenated words
        if "-" in word and word not in {"--", "\u2014"}:
            parts = word.split("-")
            titled_parts = [_title_word(p, is_occupation=is_occupation) for p in parts]
            result.append("-".join(titled_parts))
            continue

        upper_word = word.upper()

        # Single-letter middle initial: add period (check before lowercase words)
        if len(word) == 1 and word.isalpha() and not is_first:
            result.append(word.upper() + ".")
            continue

        # Check if this is a lowercase article/preposition (not first word)
        if not is_first:
            lowercase_set = OCCUPATION_LOWERCASE if is_occupation else LOWERCASE_WORDS
            if upper_word in {w.upper() for w in lowercase_set}:
                result.append(word.lower())
                continue

        titled = _title_word(word, is_occupation=is_occupation)

        # First word must always be capitalised
        if is_first and titled:
            titled = titled[0].upper() + titled[1:]

        result.append(titled)

    return " ".join(result)
