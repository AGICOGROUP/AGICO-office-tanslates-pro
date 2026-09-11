"""Shared deterministic technical-value checks; no model or network dependency."""
from collections import Counter
import re
import unicodedata

PROTECTED_TOKEN = re.compile(
    r"https?://\S+|www\.\S+|\b\d+(?:[.,]\d+)?\s*(?:%|°C|℃|kW|MW|V|kV|A|mA|Pa|kPa|MPa|"
    r"mm|cm|m|km|kg|t|t/h|m[³3]/h|Nm[³3]/min|rpm|r/min)(?![A-Za-z0-9])|\b[A-Z][A-Z0-9._/-]*\d[A-Z0-9._/-]*\b",
    re.IGNORECASE,
)

def normalize_protected_tokens(tokens: list[str]) -> set[str]:
    return {
        re.sub(r"(?<=\d)Kv$", "kV", re.sub(r"\s+", "", token)
               .replace("℃", "°C").replace(",", "."))
        for token in tokens
    }


def canonical_parameters(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("℃", "°C").replace("−", "-")
    # Only known unit spellings; do not infer conversions or rewrite model codes.
    aliases = {"吨/日": "t/d", "吨/天": "t/d", "吨/小时": "t/h",
               "千瓦": "kW", "毫米": "mm", "厘米": "cm", "千克": "kg",
               "公斤": "kg", "吨": "t"}
    for source, target in aliases.items():
        text = re.sub(r"(?<=\d)\s*" + re.escape(source), target, text)
    text = re.sub(r"/\s*days?\b", "/d", text, flags=re.IGNORECASE)
    text = re.sub(r"/\s*hours?\b", "/h", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    return text


def parameter_mismatch(source: str, target: str) -> bool:
    if source == target:
        return False
    source, target = canonical_parameters(source), canonical_parameters(target)
    # Include bare values and multiplicity; translating a Chinese chapter label
    # may legitimately add a numeral, but must never remove a source value.
    numbers = re.compile(r"(?<![\d.])[-+±]?\d+(?:[.,]\d+)?")
    source_numbers = Counter(value.replace(",", ".") for value in numbers.findall(source))
    target_numbers = Counter(value.replace(",", ".") for value in numbers.findall(target))
    if source_numbers - target_numbers:
        return True
    # Prefer a complete unit expression over the legacy regex's shorter match.
    technical = re.compile(
        r"\d+(?:[.,]\d+)?\s*"
        r"(?:[mMk]?W|[mMk]?Pa|[kM]?V|mA|A|[kcm]?m|kg|t|kcal|mg|Nm|%|°C|Hz|rpm|r/min)"
        r"(?:[23])?(?:\s*/\s*(?:[kcm]?m[23]?|kg|h|d|min|s))?(?![A-Za-z0-9])"
        r"|" + PROTECTED_TOKEN.pattern,
        re.IGNORECASE,
    )
    source = re.sub(r"[\u3400-\u9fff]", " ", source)
    expected = Counter(next(iter(normalize_protected_tokens([match.group()])))
                       for match in technical.finditer(source))
    # Normalize only the documented legacy spelling, not SI prefixes or models.
    target = re.sub(r"(?<=\d)\s*Kv\b", " kV", target)
    for token, count in expected.items():
        left = r"(?<![A-Za-z0-9.])" if token[:1].isdigit() else r"(?<![A-Za-z])"
        pattern = re.escape(token).replace("/", r"\s*/\s*")
        pattern = re.sub(r"(?<=\d)(?=[A-Za-z%°])", lambda _: r"\s*", pattern)
        if len(re.findall(left + pattern + r"(?![A-Za-z0-9]|\.\d)", target)) < count:
            return True
    return False


