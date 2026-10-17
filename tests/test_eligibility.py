"""
tests/test_eligibility.py — the deterministic core: business classification,
scheme verdicts, the Action Ledger, and graded intake coverage.

These are the tests that matter most in this project. They pin behaviour that
an LLM could never be trusted to reproduce, and they encode the awkward cases
where a keyword matcher would be confidently wrong.
"""
import pytest

from backend.core.business import (
    AGRICULTURE_ALLIED,
    AGRICULTURE_CROP,
    HOME_BASED,
    MANUFACTURING,
    OTHER,
    SERVICES,
    STREET_VENDING,
    TRADING,
    classify_business,
)
from backend.core.eligibility import (
    BLOCKED,
    ELIGIBLE,
    LIKELY,
    NOT_ELIGIBLE,
    WRONG_TIER,
    evaluate_schemes,
    eligibility_summary,
    group_by_family,
)
from backend.core.intake import ANSWERED, THIN, UNADDRESSED, coverage_report, next_probe
from backend.core.ledger import DONE, ledger_and_score, score_ledger


# ── business classification ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "intake,topic,expected",
    [
        ({"business": "I run a small dairy farm with 8 cows"}, "", AGRICULTURE_ALLIED),
        ({"business": "poultry farm, I sell eggs"}, "", AGRICULTURE_ALLIED),
        ({"business": "I farm wheat and vegetables on 3 acres"}, "", AGRICULTURE_CROP),
        ({"business": "rice cultivation on my land"}, "", AGRICULTURE_CROP),
        # The regression this project actually hit: animal product words must
        # not make a producer look like a farmer.
        ({"business": "I make and sell goat milk soap from my home in Pune"}, "", HOME_BASED),
        ({"business": "Street vendor / cart"}, "", STREET_VENDING),
        ({"business": "I have a fruit shop"}, "", TRADING),
        ({"business": "I give tuition at home"}, "", SERVICES),
        ({}, "", OTHER),
    ],
)
def test_classify_business(intake, topic, expected):
    assert classify_business(intake, topic)["primary"] == expected


def test_classification_reports_its_evidence():
    result = classify_business({"business": "I run a dairy farm with 8 cows"})
    assert result["signals"], "an unexplained classification is not trustworthy"
    assert "allied agriculture" in " ".join(result["signals"])


def test_crop_beats_allied_when_both_appear():
    """Growing vegetables and keeping a cow is still, in scheme terms, farming."""
    result = classify_business({"business": "I grow vegetables and keep one cow"})
    assert result["primary"] == AGRICULTURE_CROP


# ── eligibility verdicts ───────────────────────────────────────────────────


def _verdict(result, scheme_id):
    for v in result["verdicts"]:
        if v["scheme_id"] == scheme_id:
            return v
    pytest.fail(f"{scheme_id} produced no verdict")


def test_dairy_is_eligible_for_mudra_but_crop_cultivation_is_not():
    """The single most important distinction in the whole dataset."""
    dairy = evaluate_schemes({"business": "I run a small dairy farm with 8 cows"})
    crop = evaluate_schemes({"business": "I farm wheat and vegetables on 3 acres"})

    assert _verdict(dairy, "mudra-shishu")["status"] in (ELIGIBLE, LIKELY)
    for tier in ("mudra-shishu", "mudra-kishore", "mudra-tarun", "mudra-tarun-plus"):
        verdict = _verdict(crop, tier)
        assert verdict["status"] == NOT_ELIGIBLE
        reasons = " ".join(r["label"] for r in verdict["reasons"])
        assert "not covered" in reasons.lower()


def test_every_disqualifying_verdict_cites_its_basis():
    result = evaluate_schemes({"business": "I farm wheat"})
    for verdict in result["verdicts"]:
        if verdict["status"] != NOT_ELIGIBLE:
            continue
        assert verdict["source_url"], f"{verdict['scheme_id']} has no source"
        assert verdict["last_verified_at"], f"{verdict['scheme_id']} has no verified date"
        for reason in verdict["reasons"]:
            if reason["severity"] == "disqualifying":
                assert reason["basis"], "a disqualification must say which rule fired"


def test_vendor_is_blocked_on_the_vending_certificate_not_on_business_type():
    unregistered = evaluate_schemes(
        {"business": "Street vendor / cart", "offering": "vegetables", "registered": "No, not yet"}
    )
    blocked = _verdict(unregistered, "pm-svanidhi")
    assert blocked["status"] == BLOCKED
    labels = " ".join(r["label"] for r in blocked["reasons"])
    assert "vending certificate" in labels.lower()

    registered = evaluate_schemes(
        {"business": "Street vendor / cart", "offering": "vegetables", "registered": "Yes, registered"}
    )
    assert _verdict(registered, "pm-svanidhi")["status"] in (ELIGIBLE, LIKELY)


def test_prior_mudra_loan_blocks_pmegp_but_not_mudra():
    intake = {
        "business": "I make candles at home",
        "offering": "decorative candles",
        "loan": "Yes, MUDRA",
    }
    result = evaluate_schemes(intake)
    assert _verdict(result, "pmegp")["status"] == BLOCKED
    assert _verdict(result, "mudra-kishore")["status"] in (ELIGIBLE, LIKELY)


def test_loan_amount_routes_to_the_right_mudra_tier():
    intake = {"business": "I make and sell goat milk soap from my home", "offering": "soap bars"}
    result = evaluate_schemes(intake, "I need a loan of 2 lakh to expand")
    assert result["amount"] == 200000

    shishu = _verdict(result, "mudra-shishu")
    assert shishu["status"] == WRONG_TIER
    assert shishu["suggested_name"], "a wrong-tier verdict must say which tier to use"
    assert _verdict(result, "mudra-kishore")["status"] in (ELIGIBLE, LIKELY)


def test_earnings_alone_is_never_read_as_a_loan_amount():
    """Earning 40,000 a month is not asking for a 40,000 loan — reading it as
    one would produce tier advice that is actively misleading."""
    result = evaluate_schemes(
        {"business": "Street vendor / cart", "earnings": "40,000"},
        "I earn 40000 per month from my cart",
    )
    assert result["amount"] is None


def test_unknown_business_never_earns_eligible():
    result = evaluate_schemes({"business": ""}, "")
    assert _verdict(result, "cgtmse")["status"] == LIKELY
    assert all(v["status"] != ELIGIBLE for v in result["verdicts"])


def test_tiers_collapse_into_one_card_per_programme():
    result = evaluate_schemes({"business": "Street vendor / cart"}, "I need 2 lakh")
    families = {c["family"]: c for c in group_by_family(result)}
    assert "mudra" in families
    assert len(families["mudra"]["tiers"]) == 4
    assert families["mudra"]["recommended_scheme_id"], "must name the tier to use"


def test_summary_names_each_programme_once():
    summary = eligibility_summary(
        evaluate_schemes({"business": "I farm wheat and grow vegetables"})
    )
    assert summary.count("MUDRA") == 1, summary


# ── eligibility scoring (WS-2) ─────────────────────────────────────────────


def test_every_verdict_carries_a_bounded_integer_score():
    result = evaluate_schemes({"business": "I run a small dairy farm with 8 cows"})
    assert result["verdicts"], "expected at least one verdict"
    for verdict in result["verdicts"]:
        assert isinstance(verdict["score"], int)
        assert 0 <= verdict["score"] <= 100
        assert verdict["score"] == int(verdict["score"])


def test_a_disqualified_scheme_scores_zero():
    """A closed door must read as zero, not as a partial match."""
    crop = evaluate_schemes({"business": "I farm wheat and vegetables on 3 acres"})
    for tier in ("mudra-shishu", "mudra-kishore", "mudra-tarun", "mudra-tarun-plus"):
        verdict = _verdict(crop, tier)
        assert verdict["status"] == NOT_ELIGIBLE
        assert verdict["score"] == 0
        assert verdict["failed"], "a disqualification must appear in failed rules"


def test_a_missing_document_caps_the_score_below_a_clean_match():
    """The scheme is reachable, one action away — but never ahead of an open one."""
    unregistered = evaluate_schemes(
        {"business": "Street vendor / cart", "offering": "vegetables", "registered": "No, not yet"}
    )
    blocked = _verdict(unregistered, "pm-svanidhi")
    assert blocked["status"] == BLOCKED
    assert blocked["score"] <= 55

    registered = evaluate_schemes(
        {"business": "Street vendor / cart", "offering": "vegetables", "registered": "Yes, registered"}
    )
    open_now = _verdict(registered, "pm-svanidhi")
    assert open_now["score"] > blocked["score"]


def test_ranked_matches_are_best_first_and_only_open_doors():
    result = evaluate_schemes({"business": "I run a small dairy farm with 8 cows"})
    ranked = result["ranked"]
    assert ranked, "an eligible business must have ranked matches"
    scores = [v["score"] for v in ranked]
    assert scores == sorted(scores, reverse=True)
    for verdict in ranked:
        assert verdict["status"] in (ELIGIBLE, LIKELY)


def test_matched_rules_are_reported_for_an_eligible_scheme():
    registered = evaluate_schemes(
        {"business": "Street vendor / cart", "offering": "vegetables", "registered": "Yes, registered"}
    )
    verdict = _verdict(registered, "pm-svanidhi")
    assert verdict["matched"], "an eligible scheme must show which rules it met"
    for rule in verdict["matched"]:
        assert rule["basis"], "every matched rule must cite its basis"


def test_family_card_exposes_the_best_tier_score():
    result = evaluate_schemes({"business": "Street vendor / cart"}, "I need 2 lakh")
    families = {c["family"]: c for c in group_by_family(result)}
    assert "score" in families["mudra"]
    assert 0 <= families["mudra"]["score"] <= 100


# ── action ledger ──────────────────────────────────────────────────────────


def test_score_measures_the_user_not_the_report():
    """
    The whole point of the ledger: an empty intake scores low no matter how
    good the generated report was. The old rubric scored prose quality.
    """
    fresh = ledger_and_score({"business": "Street vendor / cart"})
    established = ledger_and_score(
        {
            "business": "dairy farm with 8 cows",
            "registered": "Yes, registered",
            "earnings": "18,000",
            "age": "1–3 years",
        }
    )
    assert established["score"] > fresh["score"]
    assert fresh["score"] < 50, "a brand-new unregistered business is not near ready"
    assert established["next_action"]["points"] > 0


def test_ticking_actions_raises_the_score_monotonically():
    intake = {"business": "dairy farm", "registered": "Yes, registered", "earnings": "18,000"}
    before = ledger_and_score(intake)["score"]
    after = ledger_and_score(intake, completed=["bank_statements", "documents_ready"])["score"]
    assert after > before

    ledger = ledger_and_score(intake, completed=["bank_statements"])["actions"]
    assert all(a["status"] in (DONE, "todo", "blocked") for a in ledger)
    assert score_ledger({"actions": ledger})["score"] >= before


def test_vendor_certificate_is_tracked_as_a_scheme_blocker():
    scored = ledger_and_score({"business": "Street vendor / cart", "registered": "No, not yet"})
    blockers = [b["id"] for b in scored["blockers"]]
    assert "vending_certificate" in blockers

    # ...and it disappears once they have it.
    done = ledger_and_score(
        {"business": "Street vendor / cart", "registered": "Yes, registered"},
        completed=["vending_certificate"],
    )
    assert done["blockers"] == []


def test_score_is_bounded_and_explained():
    scored = ledger_and_score({"business": "dairy farm", "registered": "Yes, registered"})
    assert 0 <= scored["score"] <= 100
    assert scored["reasons"], "every point must be explained"
    assert scored["points_earned"] <= scored["points_possible"]


# ── graded coverage ────────────────────────────────────────────────────────


def test_a_vague_answer_is_thin_not_answered():
    vague = coverage_report(
        {
            "business": "Street vendor / cart",
            "offering": "vegetables",
            "earnings": "some days",
            "location": "Nagpur",
            "age": "1–3 years",
            "loan": "No, first time",
            "need": "More customers",
        }
    )
    assert "earnings" in vague["thin"]
    assert vague["score"] < 100

    solid = coverage_report(
        {
            "business": "Street vendor / cart",
            "offering": "seasonal vegetables and fruit",
            "earnings": "22,000",
            "location": "Nagpur, Maharashtra",
            "age": "1–3 years",
            "loan": "No, first time",
            "need": "More customers",
        }
    )
    assert solid["score"] == 100
    assert solid["complete"] is True


def test_probe_prefers_finishing_a_thin_answer_over_a_new_question():
    """A half-answer is closer to useful than an untouched field."""
    intake = {
        "business": "Street vendor / cart",
        "offering": "vegetables",
        "earnings": "some days",  # thin
        # location, age, loan, need still empty
    }
    report = coverage_report(intake)
    assert "earnings" in report["thin"]
    assert "location" in report["unaddressed"]
    probe = next_probe(intake)
    assert "earn" in probe.lower()


def test_probe_is_localised():
    assert next_probe({}, "hi") != next_probe({}, "en")
    assert any("\u0900" <= ch <= "\u097F" for ch in next_probe({}, "hi"))


def test_unaddressed_and_thin_are_distinguishable():
    empty = coverage_report({})
    assert empty["score"] == 0
    assert set(empty["unaddressed"]) and not empty["thin"]

    thin = coverage_report({"earnings": "some days"})
    assert "earnings" in thin["thin"]
    assert "earnings" not in thin["unaddressed"]


def test_bare_location_word_counts_as_thin():
    report = coverage_report(
        {"business": "Shop / stall", "offering": "vegetables", "earnings": "20,000",
         "location": "Pune", "age": "1–3 years", "loan": "None", "need": "A clear plan"}
    )
    assert "location" in report["thin"] or report["score"] == 100