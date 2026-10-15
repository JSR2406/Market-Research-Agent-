"""
One-off migration: add machine-readable eligibility predicates + numeric amount
bands to backend/data/schemes.json.

Every rule added here is transcribed from the scheme's OWN `eligibility_rules`
/ `exclusions` text already in the file, and keeps a `basis` string quoting
that source line. Nothing is invented, and `source_url` / `last_verified_at`
are untouched — this is what makes the eligibility engine auditable.
"""
import json
from pathlib import Path

SCHEMES = Path(__file__).resolve().parents[1] / "backend" / "data" / "schemes.json"

# min/max are the scheme's own published band, in whole rupees.
BANDS = {
    "cgtmse": (None, None),
    "mudra-shishu": (None, 150000),
    "mudra-kishore": (150001, 1500000),
    "mudra-tarun": (1500001, 11000000),
    "mudra-tarun-plus": (11000001, 20000000),
    "pmegp": (None, 2000000),
    "pm-svanidhi": (10000, 50000),
}

MUDRA_NON_FARM = {
    "id": "no_crop_cultivation",
    "type": "business_class_not_in",
    "values": ["agriculture_crop"],
    "severity": "disqualifying",
    "label": "Crop cultivation is not covered by this scheme",
    "basis": "exclusions: Corporate/farm cultivation activities",
}
MUDRA_ALLIED_OK = {
    "id": "allied_agriculture_ok",
    "type": "business_class_in",
    "values": ["agriculture_allied"],
    "severity": "qualifying",
    "label": "Allied agriculture (dairy, poultry, beekeeping) is covered",
    "basis": "eligibility_rules: activities allied to agriculture such as poultry, dairy, beekeeping",
}

CHECKS = {
    "cgtmse": [
        {
            "id": "mse_collateral_free",
            "type": "collateral_note",
            "severity": "qualifying",
            "label": "Guarantee covers collateral-free MSME loans",
            "basis": "collateral_requirement: None — the guarantee covers 85% of the loan up to Rs 15 lakh",
        },
        {
            "id": "udyam_recommended",
            "type": "registration_preferred",
            "severity": "advisory",
            "label": "Udyam registration is recommended to prove MSE status",
            "basis": "eligibility_rules: Udyam registration recommended (not strictly mandatory)",
        },
    ],
    "mudra-shishu": [
        MUDRA_NON_FARM,
        MUDRA_ALLIED_OK,
        {
            "id": "non_corporate",
            "type": "advisory",
            "severity": "advisory",
            "label": "For individuals, proprietorships and partnerships (not companies)",
            "basis": "eligibility_rules: Available to individuals, proprietorship concerns, partnership firms",
        },
    ],
    "mudra-kishore": [MUDRA_NON_FARM, MUDRA_ALLIED_OK],
    "mudra-tarun": [MUDRA_NON_FARM, MUDRA_ALLIED_OK],
    "mudra-tarun-plus": [MUDRA_NON_FARM, MUDRA_ALLIED_OK],
    "pmegp": [
        {
            "id": "no_crop_cultivation",
            "type": "business_class_not_in",
            "values": ["agriculture_crop"],
            "severity": "disqualifying",
            "label": "Crop cultivation is outside PMEGP (non-farm sector only)",
            "basis": "exclusions: Activities in the negative list / eligibility_rules: non-farm",
        },
        {
            "id": "mfse_only",
            "type": "business_class_in",
            "values": ["manufacturing", "services", "home_based"],
            "severity": "qualifying",
            "label": "Manufacturing or service sector micro unit",
            "basis": "eligibility_rules: New micro-enterprise in manufacturing or business/service sector (non-farm)",
        },
        {
            "id": "no_prior_government_loan",
            "type": "loan_history_not",
            "values": ["mudra", "pmegp", "regp"],
            "severity": "blocking",
            "label": "One unit per family — a second unit needs the first loan repaid",
            "basis": "exclusions: Units already financed under PMEGP / REGP / MUDRA in the same family",
        },
        {
            "id": "rural_margin_subsidy",
            "type": "advisory",
            "severity": "advisory",
            "label": "Margin money subsidy is higher (25-35%) for rural units than urban (15-25%)",
            "basis": "eligibility_rules: Margin money subsidy 25-35% rural, 15-25% urban",
        },
    ],
    "pm-svanidhi": [
        {
            "id": "street_vendor_only",
            "type": "business_class_in",
            "values": ["street_vending"],
            "severity": "disqualifying",
            "label": "Only for street vendors — other businesses are not covered",
            "basis": "exclusions: Non-vending businesses",
        },
        {
            "id": "vending_certificate",
            "type": "requires_document",
            "severity": "blocking",
            "label": "Needs a vending certificate / ULB identification letter",
            "basis": "eligibility_rules: Holds a valid vending certificate / ULB identification letter",
        },
        {
            "id": "urban_or_town",
            "type": "advisory",
            "severity": "advisory",
            "label": "Vending in a covered city or town (scheme extended to 31.03.2030)",
            "basis": "eligibility_rules: Street vendor vending in a covered city/town",
        },
    ],
}

# Tiers that only differ by amount — used to redirect a user to the right tier.
MUDRA_TIERS = ["mudra-shishu", "mudra-kishore", "mudra-tarun", "mudra-tarun-plus"]

raw = SCHEMES.read_text(encoding="utf-8")
schemes = json.loads(raw)

for scheme in schemes:
    sid = scheme["id"]
    if sid not in CHECKS:
        raise SystemExit(f"no checks defined for {sid} — refusing to write a partial dataset")
    lo, hi = BANDS[sid]
    # Insert amount band + checks right after loan_ceiling so the JSON reads in
    # the same order the UI shows it.
    rebuilt = {}
    for key, value in scheme.items():
        rebuilt[key] = value
        if key == "loan_ceiling":
            rebuilt["min_amount"] = lo
            rebuilt["max_amount"] = hi
            rebuilt["amount_band_note"] = (
                "No published ceiling" if hi is None else f"Up to Rs {hi:,}"
            )
            rebuilt["checks"] = CHECKS[sid]
            rebuilt["tier_group"] = "mudra" if sid in MUDRA_TIERS else sid
    if "checks" not in rebuilt:
        rebuilt["checks"] = CHECKS[sid]
        rebuilt["min_amount"] = lo
        rebuilt["max_amount"] = hi
        rebuilt["amount_band_note"] = "No published ceiling" if hi is None else f"Up to Rs {hi:,}"
        rebuilt["tier_group"] = "mudra" if sid in MUDRA_TIERS else sid
    scheme.clear()
    scheme.update(rebuilt)

SCHEMES.write_text(
    json.dumps(schemes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(f"updated {len(schemes)} schemes")
for s in schemes:
    print(f"  {s['id']:<16} band={s['min_amount']}-{s['max_amount']} checks={len(s['checks'])}")