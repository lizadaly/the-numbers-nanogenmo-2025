"""Type stubs for num2words."""

def num2words(
    number: int | float | str,
    ordinal: bool = False,
    lang: str = "en",
    to: str = "cardinal",
    **kwargs: object,
) -> str:
    """Convert a number to its word representation.

    Args:
        number: The number to convert
        ordinal: Whether to return ordinal form (e.g., "first" instead of "one")
        lang: Language code (default: "en")
        to: Type of conversion ("cardinal", "ordinal", "ordinal_num", "year", "currency")
        **kwargs: Additional language-specific options

    Returns:
        String representation of the number
    """
    ...
