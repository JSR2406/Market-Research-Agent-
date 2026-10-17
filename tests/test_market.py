"""
tests/test_market.py — live reference data and its freshness contract (WS-8).

The one thing that must never regress: a value is never shown without the date
it refers to. A mandi price three days old must be labelled three days old, and
when the upstream cannot be reached the answer must say so — or, if we still
hold an earlier copy, hand it back as *stale* with its true date — instead of
quietly serving yesterday's price as today's.

Everything here runs with no network: the single HTTP door (``httpx.get``) is
either monkeypatched or never reached because no key is configured.
"""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.core import market

TODAY = date(2026, 10, 18)
NOW = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Point the cache at a throwaway dir and make sure no key is configured."""
    monkeypatch.setattr(market, "MARKET_DIR", str(tmp_path))
    monkeypatch.setattr(market, "CACHE_FILE", str(tmp_path / "cache.json"))
    monkeypatch.delenv("DATAGOV_API_KEY", raising=False)
    return tmp_path


def _record(days_ago: int = 0, modal: int = 2000) -> dict:
    when = TODAY - timedelta(days=days_ago)
    return {
        "state": "Maharashtra",
        "district": "Nashik",
        "market": "Lasalgaon",
        "commodity": "Onion",
        "variety": "Other",
        "grade": "FAQ",
        "arrival_date": when.strftime("%d/%m/%Y"),
        "min_price": "1200",
        "max_price": "2400",
        "modal_price": str(modal),
    }


def _feed(*records):
    """A monkeypatch target for the OGD fetch: always succeeds with these rows."""
    def _fetch(dataset, params):
        return True, list(records), ""
    return _fetch


def _failing(error: str = "transport_error"):
    def _fetch(dataset, params):
        return False, [], error
    return _fetch


# ── shape and honesty of the response ─────────────────────────────────────────


def test_unknown_dataset_is_reported_not_raised(store):
    result = market.lookup("no-such-dataset")
    assert result["available"] is False
    assert result["reason"] == "unknown_dataset"
    assert result["records"] == []


def test_missing_key_says_so_and_links_the_official_portal(store):
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["available"] is False
    assert result["reason"] == "missing_key"
    assert result["official_url"].startswith("https://")
    assert result["source_url"].startswith("https://")
    # Nothing is invented to fill the gap.
    assert result["records"] == [] and result["as_of"] is None


def test_no_network_call_is_made_when_no_key_is_configured(store, monkeypatch):
    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("a network call was attempted without a key")

    monkeypatch.setattr(market.httpx, "get", _explode)
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["reason"] == "missing_key"


def test_every_dataset_without_a_key_answers_offline(store, monkeypatch):
    monkeypatch.setattr(market, "_fetch_json", lambda url, params=None: (False, None, "transport_error"))
    assert market.lookup("pincode", {"pincode": "440001"}, now=NOW)["available"] is False
    # IFSC needs no key, so it reaches the network door — which here is refused.
    result = market.lookup("ifsc", {"ifsc": "HDFC0000001"}, now=NOW)
    assert result["available"] is False
    assert result["reason"] == "transport_error"


# ── validation ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["", "12345", "1234567", "abcdef", "4400 1"])
def test_pincode_must_be_six_digits(store, value):
    result = market.lookup("pincode", {"pincode": value}, now=NOW)
    assert result["available"] is False
    assert result["reason"] == "pincode_must_be_6_digits"


@pytest.mark.parametrize("value", ["", "HDFC000001", "HDFC00000012", "ABCDE000001"])
def test_ifsc_must_be_a_valid_code(store, value):
    result = market.lookup("ifsc", {"ifsc": value}, now=NOW)
    assert result["available"] is False
    assert result["reason"] == "ifsc_looks_invalid"


def test_ifsc_is_uppercased_before_lookup(store, monkeypatch):
    seen = {}

    def _fetch(url, params=None):
        seen["url"] = url
        return False, None, "upstream_404"

    monkeypatch.setattr(market, "_fetch_json", _fetch)
    market.lookup("ifsc", {"ifsc": "hdfc0000001"}, now=NOW)
    assert seen["url"].endswith("/HDFC0000001")


def test_mandi_needs_a_commodity(store):
    result = market.lookup("mandi_price", {"market": "Lasalgaon"}, now=NOW)
    assert result["reason"] == "commodity_required"


def test_lookup_never_raises_on_junk_input(store):
    for params in [None, {}, {"commodity": None}, {"commodity": 5}, {"pincode": 440001}]:
        market.lookup("mandi_price", params, now=NOW)
        market.lookup("pincode", params, now=NOW)


# ── freshness: the whole point ────────────────────────────────────────────────


def test_fresh_fetch_reports_the_data_date_and_its_lag(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=2)))

    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)

    assert result["available"] is True and result["live"] is True and result["stale"] is False
    assert result["as_of"] == "2026-10-16"       # the data's own date,
    assert result["lag_days"] == 2               # ...not the fetch date.
    assert result["fetched_at"].startswith("2026-10-18")
    assert "2 days old" in result["freshness_label"]["en"]
    assert result["records"][0]["modal_price"] == 2000
    assert result["source_url"].startswith("https://")


def test_as_of_is_the_data_date_not_today_even_when_the_feed_lags_a_week(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=7)))

    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["as_of"] == "2026-10-11"
    assert result["lag_days"] == 7
    # It is still *live* (we just fetched it) — but visibly a week behind.
    assert result["live"] is True
    assert result["as_of"] != NOW.date().isoformat()


def test_same_day_data_reads_as_today(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=0)))
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["lag_days"] == 0
    assert "(today)" in result["freshness_label"]["en"]


def test_an_unparseable_date_is_admitted_not_guessed(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    bad = dict(_record())
    bad["arrival_date"] = "not a date"
    monkeypatch.setattr(market, "_fetch_ogd", _feed(bad))

    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["as_of"] is None
    assert result["as_of_known"] is False
    assert result["lag_days"] is None
    assert "usable date" in result["freshness_label"]["en"]
    # The record is still shown — we simply do not claim a date for it.
    assert result["count"] == 1 and result["records"][0]["date"] == ""


def test_reference_feeds_without_a_date_say_so(store, monkeypatch):
    monkeypatch.setattr(
        market, "_fetch_json",
        lambda url, params=None: (True, {"BANK": "HDFC Bank", "BRANCH": "Fort", "IFSC": "HDFC0000001"}, ""),
    )
    result = market.lookup("ifsc", {"ifsc": "HDFC0000001"}, now=NOW)
    assert result["available"] is True
    assert result["as_of"] is None and result["as_of_known"] is True
    assert "no date of its own" in result["freshness_label"]["en"]
    assert result["records"][0]["bank"] == "HDFC Bank"


def test_freshness_labels_are_translated(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=3)))
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert "दिन पुराना" in result["freshness_label"]["hi"] or "लाइव" in result["freshness_label"]["hi"]
    assert result["disclaimer"]


# ── cache behaviour ───────────────────────────────────────────────────────────


def test_a_copy_inside_its_ttl_is_served_without_a_second_fetch(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    calls = {"n": 0}

    def _fetch(dataset, params):
        calls["n"] += 1
        return True, [_record()], ""

    monkeypatch.setattr(market, "_fetch_ogd", _fetch)
    first = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    second = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW + timedelta(hours=1))

    assert calls["n"] == 1
    assert second["cached"] is True and second["live"] is True and second["stale"] is False
    assert second["as_of"] == first["as_of"]
    # A cached answer must be as complete as a fresh one — no lost rows, no
    # count that disagrees with the rows next to it.
    assert second["count"] == first["count"] == 1
    assert second["records"] == first["records"]


def test_a_copy_past_its_ttl_is_reported_as_stale_with_its_real_date(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=1)))
    market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)

    # The upstream goes down; the copy we hold is now well past its TTL.
    monkeypatch.setattr(market, "_fetch_ogd", _failing("transport_error"))
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW + timedelta(days=3))

    assert result["available"] is True          # we do have something to show,
    assert result["stale"] is True              # ...but it is not current,
    assert result["live"] is False
    assert result["as_of"] == "2026-10-17"      # and it keeps its true date.
    assert result["lag_days"] == 1
    assert result["reason"].startswith("showing_last_copy")
    assert "Not live" in result["freshness_label"]["en"]
    # The note must state the fetch date readably, not dump a raw timestamp.
    label = result["freshness_label"]["en"]
    assert "(fetched 2026-10-18)" in label
    assert "T" not in label.split("It is")[0].split("fetched")[1]
    assert result["count"] == len(result["records"]) >= 1


def test_upstream_failure_with_nothing_cached_is_honest(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _failing("upstream_500"))
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["available"] is False
    assert result["reason"] == "upstream_500"
    assert result["records"] == []
    assert result["freshness_label"]["en"]


def test_cache_persists_to_disk_and_survives_a_reload(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=1)))
    market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)

    assert (store / "cache.json").exists()
    on_disk = json.loads((store / "cache.json").read_text(encoding="utf-8"))
    assert any("mandi_price" in key for key in on_disk)


def test_cache_is_capped(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record()))
    for i in range(market.MAX_CACHE_ENTRIES + 12):
        market.lookup("mandi_price", {"commodity": f"Crop{i}"}, now=NOW)
    cache = json.loads((store / "cache.json").read_text(encoding="utf-8"))
    assert len(cache) <= market.MAX_CACHE_ENTRIES


def test_clear_cache_removes_the_file(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record()))
    market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert (store / "cache.json").exists()
    market.clear_cache()
    assert not (store / "cache.json").exists()


# ── upstream parsing quirks ───────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, text="", json_data=None, content_type="application/json", status=200):
        self.text = text
        self.status_code = status
        self.headers = {"content-type": content_type}
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


def test_a_csv_upstream_is_parsed_too(store, monkeypatch):
    csv_text = (
        "state,district,market,commodity,arrival_date,min_price,max_price,modal_price\n"
        "Maharashtra,Nashik,Lasalgaon,Onion,17/10/2026,1200,2400,2000\n"
    )
    monkeypatch.setattr(
        market.httpx, "get",
        lambda *a, **k: _FakeResponse(text=csv_text, content_type="text/csv"),
    )
    ok, payload, error = market._fetch_json("https://example.invalid/resource")
    assert ok is True and error == ""
    assert isinstance(payload, list) and payload[0]["commodity"] == "Onion"


def test_a_non_200_upstream_is_an_error_not_a_value(store, monkeypatch):
    monkeypatch.setattr(
        market.httpx, "get",
        lambda *a, **k: _FakeResponse(text="nope", content_type="text/plain", status=403),
    )
    ok, payload, error = market._fetch_json("https://example.invalid/resource")
    assert ok is False and payload is None
    assert error == "upstream_403"


def test_transport_failure_is_caught_not_raised(store, monkeypatch):
    def _boom(*a, **k):
        raise market.httpx.ConnectError("no route")

    monkeypatch.setattr(market.httpx, "get", _boom)
    ok, payload, error = market._fetch_json("https://example.invalid/resource")
    assert ok is False and error == "transport_error"


def test_ifsc_404_means_not_found_rather_than_a_failure(store, monkeypatch):
    monkeypatch.setattr(market, "_fetch_json", lambda url, params=None: (False, None, "upstream_404"))
    ok, records, error = market._fetch_ifsc("HDFC0000001")
    assert ok is False and records == []
    assert error == "not_found"


def test_records_are_capped(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(*[_record() for _ in range(120)]))
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["count"] <= market._MAX_RECORDS


def test_field_names_are_read_case_insensitively(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    shouty = {
        "Commodity": "Onion", "Market": "Lasalgaon", "Modal_Price": "2100",
        "Arrival_Date": "18/10/2026", "Min_Price": "1500", "Max_Price": "2600",
    }
    monkeypatch.setattr(market, "_fetch_ogd", _feed(shouty))
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert result["records"][0]["modal_price"] == 2100
    assert result["as_of"] == "2026-10-18"


def test_a_case_mismatched_filter_is_retried_once(store, monkeypatch):
    """Filter names are case-sensitive upstream; an empty result may just mean
    we guessed the case wrong, so the other spelling is tried before giving up."""
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    seen = []

    def _fetch(url, params=None):
        filters = {k: v for k, v in (params or []) if str(k).startswith("filters[")}
        seen.append(filters)
        if "filters[Commodity]" in filters:
            return True, {"records": [_record()]}, ""
        return True, {"records": []}, ""

    monkeypatch.setattr(market, "_fetch_json", _fetch)
    result = market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)

    assert result["count"] == 1
    assert len(seen) == 2
    assert "filters[commodity]" in seen[0]
    assert "filters[Commodity]" in seen[1]


def test_no_retry_when_the_first_filter_already_found_rows(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    calls = {"n": 0}

    def _fetch(url, params=None):
        calls["n"] += 1
        return True, {"records": [_record()]}, ""

    monkeypatch.setattr(market, "_fetch_json", _fetch)
    market.lookup("mandi_price", {"commodity": "Onion"}, now=NOW)
    assert calls["n"] == 1


# ── reading a query out of the user's own words ───────────────────────────────


@pytest.mark.parametrize(
    "topic,expected",
    [
        ("I grow onions and want a better price", "Onion"),
        ("Onion farming in Maharashtra", "Onion"),
        ("I sell tomatoes near the bus stand in Nagpur", "Tomato"),
        ("potato cold storage business", "Potato"),
    ],
)
def test_extract_query_finds_a_commodity(topic, expected):
    assert market.extract_query(topic)["commodity"] == expected


def test_extract_query_finds_a_state():
    assert market.extract_query("onion farming in Maharashtra")["state"] == "Maharashtra"


def test_extract_query_finds_a_named_market():
    found = market.extract_query("onion prices at the Lasalgaon mandi in Nashik")
    assert found["market"] == "Lasalgaon"


def test_extract_query_says_nothing_when_nothing_matches():
    found = market.extract_query("I run a tailoring shop and need a loan")
    assert found["commodity"] == ""
    # ...and no live figure is quoted on a guess.
    assert market.live_context("I run a tailoring shop and need a loan") == ""


# ── the block handed to the research prompt ───────────────────────────────────


def test_live_context_is_empty_without_a_key(store):
    assert market.live_context("I grow onions and want to sell them") == ""


def test_live_context_quotes_the_price_with_its_date(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=1, modal=2450)))

    note = market.live_context("I grow onions in Maharashtra and want a better price")

    assert "Live mandi price" in note
    assert "2450" in note
    assert "as of 2026-10-17" in note
    assert "Prefer this over a web-search estimate" in note


def test_live_context_is_empty_when_the_feed_has_nothing(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _failing())
    assert market.live_context("I grow onions") == ""


def test_live_context_never_raises(store, monkeypatch):
    monkeypatch.setattr(market, "lookup", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert market.live_context("I grow onions") == ""


# ── status ────────────────────────────────────────────────────────────────────


def test_status_lists_every_dataset_and_marks_configured_ones(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    info = market.status(now=NOW)
    by_id = {row["id"]: row for row in info["datasets"]}
    assert set(by_id) == {"mandi_price", "pincode", "ifsc"}
    assert by_id["mandi_price"]["configured"] is True
    assert by_id["ifsc"]["configured"] is True          # needs no key
    assert by_id["mandi_price"]["key_env"] == "DATAGOV_API_KEY"
    assert all(row["source_url"].startswith("https://") for row in info["datasets"])


def test_status_reports_unconfigured_feeds(store):
    by_id = {row["id"]: row for row in market.status(now=NOW)["datasets"]}
    assert by_id["mandi_price"]["configured"] is False
    assert by_id["pincode"]["configured"] is False


def test_status_does_not_leak_the_key(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "super-secret-value")
    assert "super-secret-value" not in json.dumps(market.status(now=NOW))


# ── REST surface ──────────────────────────────────────────────────────────────


@pytest.fixture()
def client(store, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_market_endpoint_answers_offline_and_explains_itself(client):
    body = client.get("/api/market?dataset=mandi_price&commodity=Onion").json()
    assert body["available"] is False
    assert body["reason"] == "missing_key"
    assert body["error"]                      # a human sentence, not a stack
    assert body["note"]
    assert body["official_url"].startswith("https://")
    assert body["records"] == []


def test_market_endpoint_validates_the_pincode(client):
    body = client.get("/api/market?dataset=pincode&pincode=123").json()
    assert body["available"] is False
    assert "6 digits" in body["error"]


def test_market_endpoint_rejects_an_unknown_dataset(client):
    assert client.get("/api/market?dataset=nope").json()["reason"] == "unknown_dataset"


def test_market_endpoint_accepts_the_documented_key_shorthand(client):
    """`GET /api/market?dataset=mandi_price&key=Onion` must behave like commodity=Onion."""
    body = client.get("/api/market?dataset=mandi_price&key=Onion").json()
    assert body["reason"] == "missing_key"          # parsed fine; no feed configured
    pincode = client.get("/api/market?dataset=pincode&key=123").json()
    assert "6 digits" in pincode["error"]


def test_market_endpoint_translates_the_disclaimer(client):
    en = client.get("/api/market?dataset=mandi_price&commodity=Onion&lang=en").json()
    hi = client.get("/api/market?dataset=mandi_price&commodity=Onion&lang=hi").json()
    assert en["disclaimer"] != hi["disclaimer"]
    assert "लाइव" in hi["disclaimer"] or "सरकारी" in hi["disclaimer"]


def test_market_endpoint_falls_back_to_english_for_an_unknown_lang(client):
    body = client.get("/api/market?dataset=mandi_price&commodity=Onion&lang=xx").json()
    assert body["disclaimer"] == market.DISCLAIMER["en"]


def test_market_status_endpoint(client):
    body = client.get("/api/market/status").json()
    ids = {row["id"] for row in body["datasets"]}
    assert {"mandi_price", "pincode", "ifsc"} <= ids
    assert body["server_time"]
    assert body["disclaimer"]


def test_market_endpoint_reports_a_live_value_with_as_of_and_lag(client, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=2)))
    body = client.get("/api/market?dataset=mandi_price&commodity=Onion&state=Maharashtra").json()
    assert body["available"] is True
    assert body["as_of"] == "2026-10-16"
    assert isinstance(body["lag_days"], int)   # real elapsed days vs. the data date
    assert body["count"] == 1
    assert "as of 2026-10-16" in body["note"]


# ── wiring into the agentic engine and the research prompt ────────────────────


def test_the_agentic_tool_reports_the_same_freshness(store, monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=1, modal=2450)))
    from backend.agentic import tools as tools_mod

    payload = json.loads(tools_mod.TOOLS["market_price"].run("I grow onions in Maharashtra"))
    assert payload["available"] is True
    assert payload["as_of"] == "2026-10-17"
    assert "as of 2026-10-17" in payload["freshness_label"]["en"]


def test_the_agentic_tool_accepts_json_input_and_says_nothing_when_unknown(store, monkeypatch):
    from backend.agentic import tools as tools_mod

    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record()))
    ok = json.loads(tools_mod.TOOLS["market_price"].run('{"commodity": "Onion"}'))
    assert ok["count"] == 1

    # A topic with no recognisable commodity must not reach the feed at all.
    monkeypatch.setattr(market, "_fetch_ogd", _failing("should_not_be_called"))
    payload = json.loads(tools_mod.TOOLS["market_price"].run("I run a tailoring shop"))
    assert payload["available"] is False
    assert payload["reason"] == "commodity_required"
    assert payload["records"] == []


def test_the_research_agent_prefers_the_live_figure(store, monkeypatch):
    """The whole WS-8 promise: the published number goes into the prompt with
    its date, so the writer can prefer it over a web-search guess."""
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    monkeypatch.setattr(market, "_fetch_ogd", _feed(_record(days_ago=1, modal=2450)))

    from backend.agents import research as research_mod

    captured: dict = {}

    async def _fake_llm(messages, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(research_mod, "call_llm", _fake_llm)
    monkeypatch.setattr(research_mod, "WEB_SEARCH_ENABLED", False)

    out = asyncio.run(research_mod.research_agent("I grow onions in Maharashtra and want a better price"))

    assert out == "ok"
    blob = captured["messages"][1]["content"]
    assert "Published market data" in blob
    assert "2450" in blob
    assert "as of 2026-10-17" in blob
    assert "prefer this over any web-search estimate" in blob


def test_the_research_agent_is_unchanged_without_a_feed(store, monkeypatch):
    from backend.agents import research as research_mod

    async def _fake_llm(messages, **kwargs):
        return "ok"

    monkeypatch.setattr(research_mod, "call_llm", _fake_llm)
    monkeypatch.setattr(research_mod, "WEB_SEARCH_ENABLED", False)

    assert asyncio.run(research_mod.research_agent("I run a tailoring shop")) == "ok"


def test_heuristic_research_carries_the_market_note():
    from backend.agents.research import heuristic_research

    out = heuristic_research("I grow onions", market_note="Live mandi price: Rs 2450")
    assert "Live mandi price: Rs 2450" in out
