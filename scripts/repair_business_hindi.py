"""
One-off repair: rewrite the Hindi half of the classifier regexes in
backend/core/business.py with correct Devanagari.

A PowerShell round-trip earlier re-encoded this file's UTF-8 through latin-1,
and the auto-repair pass dropped conjunct characters (ँ, ु, ॅ), leaving words
like "घ�?मणे". Those matter: they are the terms a Hindi-speaking user actually
types, and the classifier matches on them.
"""
import io
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "backend" / "core" / "business.py"

BLOCK = '''_STREET_RE = re.compile(
    r"street\\s*(vendor|vending|cart)|\\bcart\\b|\\bthela\\b|hawker|pavement|"
    r"mobile\\s*cart|door\\s*to\\s*door|ठेला|ठेले|रेहड़ी|पटरी|फेरी|चलता|घुमणे",
    re.IGNORECASE,
)
_HOME_RE = re.compile(
    r"home[- ]?based|home\\s*business|from\\s*(my|our)?\\s*home|work\\s*from\\s*home|"
    r"in\\s*my\\s*kitchen|\\bkitchen\\b|"
    r"किचन|घर\\s*(पर|में)|अपने\\s*घर|आँगन|आंगन",
    re.IGNORECASE,
)
_MAKE_RE = re.compile(
    r"\\bmak(e|ing)\\b|manufactur|\\bproduce\\b|\\bprocess\\b|bakery|papad|pickle|"
    r"soap|candle|garment|curry|khadi|handicraft|handloom|footwear|jewell|"
    r"furniture|cooker|मुरली|साबुन|बनाना|निर्माण|उत्पादन|कपड़ा|अचार|पापड़|"
    r" tailoring\\s*(work|stitch)|stitching",
    re.IGNORECASE,
)
_CROP_RE = re.compile(
    r"cultivat|\\bcrop\\b|\\bcrops\\b|\\bfarming\\b|\\bwheat\\b|\\brice\\b|paddy|maize|"
    r"\\bcotton\\b|sugarcane|mustard|soybean|\\bvegetable|\\borchard|fruit\\s*farm|"
    r"grow\\w*\\s+(vegetable|fruit|rice|wheat|crop|flower|plant|seed)|"
    r"फसल|खेती|बोई|गेहूँ|गेहूं|धान|कृषि|खेत",
    re.IGNORECASE,
)
_ALLIED_RE = re.compile(
    r"\\bdairy\\b|\\bmilk\\b|\\bcow\\b|\\bcows\\b|cattle|buffalo|\\bgoat\\b|\\bpoultry\\b|"
    r"\\bchicken\\b|\\begg?s?\\b|honey|beekeep|apiary|\\bfish\\b|prawn|sericulture|"
    r"दुग्ध|पशु|गाय|बकरी|मुर्गी|अंडा|मधुमक्खी|मछली",
    re.IGNORECASE,
)
_SERVICE_RE = re.compile(
    r"\\bservice\\b|repair|technician|plumb|electrician|\\btuition\\b|coaching|"
    r"salon|barber|beauty|\\btransport\\b|driver|deliver(y|ies)\\bservice|"
    r"photograph|event\\s*manage|tailor|सेवा|मरम्मत|ट्यूशन|स्कूल|व्यापार|"
    r"मैकेनिक|ब्यूटी",
    re.IGNORECASE,
)
_TRADE_RE = re.compile(
    r"\\bshop\\b|\\bstore\\b|retail|kirana|dukan|\\bmarket\\b|wholesale|supplier|"
    r"boutique|\\boutlet\\b|दुकान|किराना|दुकानदार|थोक",
    re.IGNORECASE,
)
'''


def main() -> None:
    source = PATH.read_text(encoding="utf-8")
    start = source.index("_STREET_RE = re.compile(")
    end = source.index("# Chip labels the frontend stores verbatim")
    repaired = source[:start] + BLOCK + "\n" + source[end:]
    PATH.write_text(repaired, encoding="utf-8", newline="")

    check = PATH.read_text(encoding="utf-8")
    assert "à¤" not in check, "mojibake still present"
    assert "�" not in check, "replacement characters still present"
    print("rewrote classifier regexes with correct Devanagari")


if __name__ == "__main__":
    main()