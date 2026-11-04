import unicodedata


def valid_person_name(value):
    """Letters, combining marks and ordinary spaces; exclude digits in all scripts."""
    return bool(value.strip()) and any(c.isalpha() for c in value) and all(
        c == ' ' or unicodedata.category(c).startswith(('L', 'M')) for c in value)
