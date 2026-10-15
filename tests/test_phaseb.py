"""
tests/test_phaseb.py — the planner/executor layer.

These tests pin the behaviour that separates an *executor* from an agent that
tries: a plan is proposed by the model, validated by the compiler, and its
steps are checked against pre/postconditions. None of this needs an LLM, so it
runs offline like the rest of the suite.

pytest-asyncio is not installed in this environment, so async tests are driven
through a small ``asyncio.run`` wrapper rather than a marker.
"""
import asyncio
import json

import pytest

from backend.agentic.compiler import (
    CompileError,
    best_plan,
    compile_plan,
    default_plan,
)
from backend.agentic.executor import (
    DONE,
    FAILED,
    SKIPPED,
    record_step_result,
    run_plan,
)
from backend.agentic.plan import Plan, parse_plan_json, plan_to_dict


def _plan(*steps: dict) -> str:
    return json.dumps({"goal": "test", "steps": list(steps)})


class _FakeEmitter:
    def __init__(self):
        self.events = []

    async def status(self, message):
        self.events.append(("status", message))

    async def plan(self, topic, steps):
        self.events.append(("plan", steps))


async def _run_with(compiled, state, node_fn, extra_nodes=None):
    """Run a plan with an injected node function instead of the real graph."""
    registry = dict(extra_nodes or {})

    async def dispatch(node_name, st, config):
        fn = registry.get(node_name) or node_fn
        return await fn(st, config)

    original = run_plan.__globals__["_run_node"]
    run_plan.__globals__["_run_node"] = dispatch
    try:
        run = await run_plan(
            compiled,
            state,
            {"configurable": {"emitter": _FakeEmitter()}},
            _FakeEmitter(),
        )
    finally:
        run_plan.__globals__["_run_node"] = original
    return run


# ── plan parsing ────────────────────────────────────────────────────────────


def test_parse_accepts_a_well_formed_plan():
    plan = parse_plan_json(
        _plan(
            {"id": "s1", "node": "research", "tool": "web_search",
             "pre": ["topic"], "post": ["findings"]},
            {"id": "s2", "node": "finalize", "pre": ["draft"],
             "post": ["report", "simplified"]},
        )
    )
    assert plan is not None
    assert plan.step_count == 2
    assert plan.steps[0].id == "s1"


def test_parse_accepts_a_bare_list_of_steps():
    plan = parse_plan_json('[{"id":"s1","node":"research","post":["findings"]}]')
    assert plan is not None and plan.step_count == 1


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not json at all",
        "42",
        "null",
        "[]",
        '[{"node":"research"}]',
        '[{"id":"s1"}]',
        '[{"id":"s1","node":"telepathy"}]',
    ],
)
def test_parse_rejects_unusable_input(raw):
    assert parse_plan_json(raw) is None


def test_parse_caps_runaway_generation():
    steps = [
        {"id": f"s{i}", "node": "research", "post": ["findings"]}
        for i in range(25)
    ]
    plan = parse_plan_json(_plan(*steps))
    assert plan is not None
    assert plan.step_count == 12, "a runaway plan must be capped, not trusted"


def test_parse_drops_malformed_steps_and_keeps_valid_ones():
    plan = parse_plan_json(
        _plan(
            {"id": "good", "node": "research", "post": ["findings"]},
            {"no_id": True},
            {"id": "bad", "node": "nonexistent_node"},
            {"id": "also_good", "node": "writer", "pre": ["findings"],
             "post": ["draft"]},
        )
    )
    assert plan is not None
    assert [s.id for s in plan.steps] == ["good", "also_good"]


# ── compiler ────────────────────────────────────────────────────────────────


def test_compile_rejects_duplicate_step_ids():
    plan = parse_plan_json(
        _plan(
            {"id": "dup", "node": "research", "post": ["findings"]},
            {"id": "dup", "node": "writer", "pre": ["findings"],
             "post": ["draft"]},
        )
    )
    assert compile_plan(plan, {"topic": "x"}) is None


def test_compile_flags_unknown_tool():
    plan = parse_plan_json(
        _plan({"id": "s1", "node": "research", "tool": "telepathy",
               "post": ["findings"]})
    )
    compiled = compile_plan(plan, {"topic": "x"})
    assert compiled is not None
    assert any("telepathy" in w for w in compiled.warnings)


def test_compile_flags_unknown_state_key():
    """A typo in a key would otherwise make a precondition *always* pass."""
    plan = parse_plan_json(
        _plan({"id": "s1", "node": "research", "pre": ["topc"],
               "post": ["finding"]})
    )
    compiled = compile_plan(plan, {"topic": "x"})
    assert compiled is not None
    assert any("topc" in w for w in compiled.warnings)
    assert any("finding" in w for w in compiled.warnings)


def test_compile_flags_unreachable_precondition():
    plan = parse_plan_json(
        _plan({"id": "s1", "node": "writer", "pre": ["findings"],
               "post": ["draft"]})
    )
    compiled = compile_plan(plan, {"topic": "x"})
    assert compiled is not None
    assert any("findings" in w for w in compiled.warnings)


def test_compile_records_dependency_order():
    plan = parse_plan_json(
        _plan(
            {"id": "s1", "node": "research", "pre": ["topic"],
             "post": ["findings"]},
            {"id": "s2", "node": "writer", "pre": ["findings"],
             "post": ["draft"]},
            {"id": "s3", "node": "finalize", "pre": ["draft"],
             "post": ["report"]},
        )
    )
    compiled = compile_plan(plan, {"topic": "x"})
    assert compiled is not None
    assert compiled.step_count == 3
    assert compiled.steps[1].depends_on == ["s1"]
    assert compiled.steps[2].depends_on == ["s2"]


def test_a_step_s_own_postcondition_satisfies_itself():
    """Without this, every self-producing step would be flagged."""
    plan = parse_plan_json(
        _plan({"id": "s1", "node": "research", "pre": ["topic"],
               "post": ["findings"]})
    )
    compiled = compile_plan(plan, {"topic": "x"})
    assert compiled is not None
    assert compiled.warnings == []


def test_default_plan_always_compiles():
    for max_steps in (1, 3, 4, 6):
        compiled = compile_plan(default_plan("tea stall", max_steps), {"topic": "t"})
        assert compiled is not None, f"max_steps={max_steps}"
        assert compiled.warnings == []


def test_best_plan_prefers_the_candidate_and_falls_back():
    good = parse_plan_json(
        _plan({"id": "s1", "node": "research", "pre": ["topic"],
               "post": ["findings"]})
    )
    assert best_plan(good, {"topic": "x"}, "x", 4).step_count == 1

    # No candidate → default topology, never None, never raises.
    fallback = best_plan(None, {"topic": "x"}, "x", 4)
    assert fallback.step_count >= 3
    assert fallback.warnings == []


def test_best_plan_falls_back_when_the_candidate_is_unusable():
    bad = parse_plan_json(
        '[{"id":"s1","node":"research","tool":"telepathy","post":["findings"]},'
        '{"id":"s1","node":"writer","pre":["findings"],"post":["draft"]}]'
    )
    # duplicate ids → candidate rejected → default topology
    result = best_plan(bad, {"topic": "x"}, "x", 4)
    assert result.step_count >= 3


def test_compile_plan_never_raises():
    """
    A compiler that raises would take the run down. It must not — a malformed
    plan is a normal outcome of asking a language model to plan.
    """
    assert compile_plan(None, {}) is None
    assert compile_plan(Plan(), {}) is None
    assert compile_plan(default_plan("x", 3), None) is not None


def test_compile_error_is_descriptive():
    err = CompileError("bad plan", code="test_code")
    assert str(err) == "bad plan"
    assert err.code == "test_code"


# ── executor ────────────────────────────────────────────────────────────────


def test_executor_runs_steps_in_order_and_records_success():
    async def scenario():
        plan = parse_plan_json(
            _plan(
                {"id": "s1", "node": "research", "pre": ["topic"],
                 "post": ["findings"]},
                {"id": "s2", "node": "writer", "pre": ["findings"],
                 "post": ["draft"]},
            )
        )
        compiled = compile_plan(plan, {"topic": "x"})
        assert compiled is not None

        async def fake_node(state, config):
            return {"findings": ["f1"], "draft": "d"}

        state = {"topic": "x"}
        run = await _run_with(compiled, state, fake_node)
        assert run.ok
        assert [r.status for r in run.results] == [DONE, DONE]
        assert state["plan_run"]["ok"] is True

    asyncio.run(scenario())


def test_executor_skips_a_step_whose_precondition_is_unmet():
    async def scenario():
        plan = parse_plan_json(
            _plan({"id": "s1", "node": "writer", "pre": ["findings"],
                   "post": ["draft"]})
        )
        compiled = compile_plan(plan, {"topic": "x"})
        assert compiled is not None

        async def fail_node(state, config):  # pragma: no cover — must not run
            raise AssertionError("step with unmet precondition must not run")

        state = {"topic": "x"}
        run = await _run_with(compiled, state, fail_node)
        assert run.results[0].status == SKIPPED
        assert run.results[0].pre_unmet == ["findings"]

    asyncio.run(scenario())


def test_executor_marks_a_step_failed_when_nothing_is_produced():
    async def scenario():
        plan = parse_plan_json(
            _plan({"id": "s1", "node": "research", "pre": ["topic"],
                   "post": ["findings"]})
        )
        compiled = compile_plan(plan, {"topic": "x"})
        assert compiled is not None

        async def empty_node(state, config):
            return {}

        state = {"topic": "x"}
        run = await _run_with(compiled, state, empty_node)
        assert run.results[0].status == FAILED
        assert run.results[0].post_unmet == ["findings"]
        assert run.failed == ["s1"]

    asyncio.run(scenario())


def test_executor_never_raises_on_node_failure():
    async def scenario():
        plan = parse_plan_json(
            _plan(
                {"id": "s1", "node": "research", "pre": ["topic"],
                 "post": ["findings"]},
                {"id": "s2", "node": "finalize", "pre": ["draft"],
                 "post": ["report"]},
            )
        )
        compiled = compile_plan(plan, {"topic": "x"})
        assert compiled is not None

        async def boom(state, config):
            raise RuntimeError("LLM down (test)")

        state = {"topic": "x"}
        run = await _run_with(compiled, state, boom)
        assert run.results[0].status == FAILED
        assert "RuntimeError" in run.results[0].reason
        # The run survived and recorded the failure instead of crashing.
        assert state["plan_run"]["ok"] is False

    asyncio.run(scenario())


def test_executor_runs_fallback_when_postcondition_fails():
    async def scenario():
        plan = parse_plan_json(
            _plan(
                {"id": "s1", "node": "research", "pre": ["topic"],
                 "post": ["findings"], "fallback": "supervisor"},
            )
        )
        compiled = compile_plan(plan, {"topic": "x"})
        assert compiled is not None

        async def empty_node(state, config):
            return {}

        async def supervisor_node(state, config):
            return {"findings": ["recovered"]}

        state = {"topic": "x"}
        run = await _run_with(
            compiled, state, empty_node, extra_nodes={"supervisor": supervisor_node}
        )
        assert run.results[0].status == "fallback_used"
        assert state.get("findings") == ["recovered"]

    asyncio.run(scenario())


def test_executor_caps_the_step_count():
    async def scenario():
        steps = [
            {"id": f"s{i}", "node": "research", "pre": ["topic"],
             "post": ["findings"]}
            for i in range(6)
        ]
        plan = parse_plan_json(_plan(*steps))
        compiled = compile_plan(plan, {"topic": "x"}, max_steps=2)
        assert compiled is not None
        assert compiled.step_count == 2

    asyncio.run(scenario())


# ── postcondition bookkeeping ───────────────────────────────────────────────


def test_record_step_result_tracks_failures():
    state = {}
    record_step_result(
        state, step_id="s1", node="research", status=DONE, post_met=["findings"],
    )
    record_step_result(
        state, step_id="s2", node="writer", status=FAILED,
        post_unmet=["draft"], reason="nothing produced",
    )
    run = state["plan_run"]
    assert run["ok"] is False
    assert run["results"][0]["status"] == DONE
    assert run["results"][1]["reason"] == "nothing produced"


def test_plan_drive_path_end_to_end(monkeypatch):
    """
    A compiled plan must actually change routing: the supervisor follows the
    plan's step order instead of inventing its own.

    This is the integration seam for the whole feature — if the planner emits a
    plan but the supervisor ignores it, nothing has changed.
    """
    from backend.agentic import nodes as nodes_mod
    from backend.agentic import runner as runner_mod
    from backend.agentic.supervisor import decide as real_decide

    state = {"topic": "I sell fruit from a cart", "max_steps": 4}

    async def fake_structured(topic, previous_context=""):
        return json.dumps(
            {
                "goal": "test",
                "steps": [
                    {"id": "p1", "node": "research", "pre": ["topic"],
                     "post": ["findings"], "fallback": "supervisor"},
                    {"id": "p2", "node": "finalize", "pre": ["findings"],
                     "post": ["report", "simplified"]},
                ],
            }
        )

    async def fake_node(node_name):
        async def fn(st, cfg):
            if node_name == "research":
                return {"findings": [{"step": "r", "agent": "a", "output": "o"}]}
            if node_name == "finalize":
                return {
                    "report": json.dumps({"business_summary": "ok"}),
                    "simplified": "plain",
                    "loan_ready_score": {"score": 10},
                }
            return {}

        return fn


async def _build_wrapped_registry():
    return {nid: await fake_node(nid) for nid in ("research", "finalize")}

    # The supervisor must NOT run its heuristic when a plan exists.
    async def forbidden_decide(st):  # pragma: no cover
        raise AssertionError("supervisor used heuristics despite a compiled plan")

    monkeypatch.setattr(nodes_mod, "structured_plan_agent", fake_structured)
    monkeypatch.setattr(
        nodes_mod, "_decide_with_plan", nodes_mod._decide_with_plan
    )
    monkeypatch.setattr(
        runner_mod, "POSTCONDITION_FUNCS", await _build_wrapped_registry()
    )

    async def scenario():
        em = _FakeEmitter()
        config = {"configurable": {"emitter": em, "thread_id": "test"}}
        final, status = await runner_mod.run_agentic_workflow(
            state["topic"], 4, em, session_context="", profile="",
            eligibility_note="", output_lang="en",
        )
        return final, status

    final, status = asyncio.run(scenario())

    assert status == "done"
    assert final.get("compiled_plan") is not None, "planner must emit a plan"
    visited = final.get("visited") or []
    assert "research" in visited and "finalize" in visited
    # The supervisor followed the plan rather than the heuristic order.
    assert visited.index("research") < visited.index("finalize")
    assert final.get("plan_run", {}).get("ok") is True


def test_postcondition_wrapper_records_a_missing_output():
    """
    A node that claims success but produced nothing must be recorded as failed
    in the trace — that is the whole point of postconditions.
    """
    from backend.agentic import nodes as nodes_mod
    from backend.agentic.executor import with_postconditions

    async def lying_node(state, config):
        # Returns nothing, while its plan step claims it produces "findings".
        return {}

    # A node name of "nothing_real" matches no step, so nothing is recorded.
    compiled = {
        "steps": [
            {"id": "p1", "node": "research", "pre": ["topic"],
             "post": ["findings"], "fallback": "supervisor"},
        ]
    }
    state = {"topic": "x", "compiled_plan": compiled}

    async def scenario():
        wrapped = with_postconditions(lying_node, "research")
        await wrapped(state, {"configurable": {"emitter": _FakeEmitter()}})
        return state["plan_run"]

    run = asyncio.run(scenario())
    assert run["results"][0]["status"] == FAILED
    assert run["results"][0]["post_unmet"] == ["findings"]
    assert run["ok"] is False


def test_plan_to_dict_round_trips():
    plan = parse_plan_json(
        _plan({"id": "s1", "node": "research", "reason": "why",
               "tool": "web_search", "pre": ["topic"], "post": ["findings"],
               "fallback": "supervisor"})
    )
    assert plan is not None
    data = plan_to_dict(plan)
    assert data["steps"][0]["id"] == "s1"
    assert data["steps"][0]["pre"] == ["topic"]
    assert data["steps"][0]["fallback"] == "supervisor"