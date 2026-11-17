"""Everyday Vietnamese amounts ('3 củ', '3tr', '4tr5', '500k') written the way policies write them."""
import re
from decimal import Decimal

_AMOUNT_SCALES = {"tỷ": 10**9, "tỉ": 10**9, "triệu": 10**6, "tr": 10**6, "củ": 10**6,
                  "nghìn": 10**3, "ngàn": 10**3, "k": 10**3}
_AMOUNT = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(tỷ|tỉ|triệu|tr|củ|nghìn|ngàn|k)(\d)?(?!\w)", re.IGNORECASE)


def normalize_amounts(query: str) -> str:
    """Write everyday amounts the way policies do: '3 củ' / '3tr' -> '3.000.000 VND', '4tr5' -> '4.500.000 VND'.

    The translator read '3 củ' as '3 bulbs' and '7 củ' as '70 million'; search also matches the policy's own form.
    shortcut: '<number> củ' is always money here (a policy assistant); revisit if produce/inventory items are asked by count.
    """
    def expand(match):
        number, unit, tail = match.groups()
        scale = _AMOUNT_SCALES[unit.lower()]
        value = Decimal(number.replace(",", ".")) * scale + (Decimal(tail) * scale / 10 if tail else 0)
        if value != value.to_integral_value():
            return match.group(0)
        return f"{int(value):,}".replace(",", ".") + " VND"
    return _AMOUNT.sub(expand, query)


def annotate_amounts(question: str) -> str:
    """Keep the user's words and add the written amount: 'mua 3 củ' -> 'mua 3 củ (3.000.000 VND)'."""
    return _AMOUNT.sub(lambda m: m.group(0) if normalize_amounts(m.group(0)) == m.group(0)
                       else f"{m.group(0)} ({normalize_amounts(m.group(0))})", question)
