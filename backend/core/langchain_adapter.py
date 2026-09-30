"""
backend/core/langchain_adapter.py — optional LangChain integration.

Design rules (project constraints):
- ALL LLM traffic still flows through ``backend.core.llm_client.call_llm``.
  ``GrameenChatModel`` is a thin LangChain ``BaseChatModel`` wrapper around it,
  so provider priority / fallback / caching / token budgets stay in one place.
- Never raises at import time: if ``langchain-core`` is not installed,
  ``LANGCHAIN_AVAILABLE`` is False and helpers fall back to plain ``call_llm``.
- Every helper has a deterministic heuristic fallback (offline guarantee tier).

Usage:
    from backend.core.langchain_adapter import build_advisory_chain, run_prompt

    chain = build_advisory_chain("You are a business advisor.")
    text = await run_prompt(chain, "How do I price my products?")
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:  # optional dependency — base backend works without it
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import Runnable
    from langchain_core.tools import tool as lc_tool

    LANGCHAIN_AVAILABLE = True
except Exception as e:  # pragma: no cover — import-time fallback
    LANGCHAIN_AVAILABLE = False
    logger.warning(f"[LangChain] langchain-core not installed, running in fallback mode: {e}")


def _run_coro_sync(coro):
    """Run an async coroutine from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop (e.g. Jupyter / worker thread) — isolate on a new loop.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


if LANGCHAIN_AVAILABLE:

    class GrameenChatModel(BaseChatModel):
        """LangChain chat model backed by the project's multi-provider llm_client.

        Parameters
        ----------
        agent_hint : name used for per-agent token budgets + OpenRouter priority
        temperature, max_tokens : forwarded to ``call_llm``
        """

        agent_hint: str = "default"
        temperature: float = 0.7
        max_tokens: int = 500

        @property
        def _llm_type(self) -> str:
            return "grameen-multi-provider"

        def _messages_to_openai(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
            role_map = {HumanMessage: "user", AIMessage: "assistant", SystemMessage: "system"}
            out: List[Dict[str, str]] = []
            for m in messages:
                role = "user"
                for cls, r in role_map.items():
                    if isinstance(m, cls):
                        role = r
                        break
                else:  # generic BaseMessage with .type
                    role = {"human": "user", "ai": "assistant", "system": "system"}.get(
                        getattr(m, "type", "human"), "user"
                    )
                content = m.content if isinstance(m.content, str) else str(m.content)
                out.append({"role": role, "content": content})
            return out

        def _generate(
            self,
            messages: List[BaseMessage],
            stop: Optional[List[str]] = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            from backend.core.llm_client import call_llm

            openai_messages = self._messages_to_openai(messages)
            text = _run_coro_sync(
                call_llm(
                    openai_messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    agent_hint=kwargs.get("agent_hint", self.agent_hint),
                )
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

        async def _agenerate(
            self,
            messages: List[BaseMessage],
            stop: Optional[List[str]] = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            from backend.core.llm_client import call_llm

            openai_messages = self._messages_to_openai(messages)
            text = await call_llm(
                openai_messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                agent_hint=kwargs.get("agent_hint", self.agent_hint),
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    # ── Tools (deterministic, zero LLM cost) ──────────────────────────────

    @lc_tool
    def web_search_tool(query: str) -> str:
        """Search the live web for market context. Input: a short query string."""
        try:
            from backend.core.web_research import web_context

            return _run_coro_sync(web_context(query))[:2000]
        except Exception as e:
            return f"Web search unavailable: {e}"

    @lc_tool
    def loan_ready_score_tool(advisory_json: str) -> str:
        """Compute the deterministic 0-100 loan-readiness score for an advisory JSON string."""
        try:
            import json as _json

            from backend.core.heuristics import compute_loan_ready_score, parse_advisory_json

            data = parse_advisory_json(advisory_json) or _json.loads(advisory_json)
            score = compute_loan_ready_score(data)
            return _json.dumps(score, ensure_ascii=False)
        except Exception as e:
            return f"Could not compute loan-ready score: {e}"

    @lc_tool
    def scheme_match_tool(business_description: str) -> str:
        """Match Indian MSME schemes for a business description. Input: plain text."""
        try:
            import json as _json

            from backend.core.heuristics import extract_topic, match_schemes

            matches = match_schemes(extract_topic(business_description))
            return _json.dumps(matches[:5], ensure_ascii=False)
        except Exception as e:
            return f"Scheme matching unavailable: {e}"

    ADVISORY_TOOLS = [web_search_tool, loan_ready_score_tool, scheme_match_tool]

    def build_advisory_chain(
        system_prompt: str,
        agent_hint: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> Runnable:
        """Build a standard (prompt | model | string-output) advisory chain."""
        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("human", "{input}")]
        )
        llm = GrameenChatModel(
            agent_hint=agent_hint, temperature=temperature, max_tokens=max_tokens
        )
        return prompt | llm | StrOutputParser()

else:  # langchain-core missing — placeholder so imports never break
    ADVISORY_TOOLS: List[Any] = []

    def build_advisory_chain(system_prompt: str, **kwargs: Any) -> None:
        return None


async def run_prompt(
    chain_or_prompt: Any,
    user_input: str,
    *,
    agent_hint: str = "default",
    system_prompt: str = "You are a helpful business advisor for micro-entrepreneurs in India.",
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> str:
    """Run a LangChain chain (or plain prompt) with heuristic fallback. Never raises.

    - If LangChain is installed and a chain is given, ``chain.ainvoke`` is used.
    - Otherwise the call goes straight to ``call_llm``.
    - If the LLM fails, a deterministic heuristic reply is returned.
    """
    from backend.core.llm_client import call_llm

    if LANGCHAIN_AVAILABLE and chain_or_prompt is not None and hasattr(
        chain_or_prompt, "ainvoke"
    ):
        try:
            result = await chain_or_prompt.ainvoke({"input": user_input})
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.warning(f"[LangChain] chain.ainvoke failed, falling back to call_llm: {e}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    try:
        return await call_llm(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            agent_hint=agent_hint,
        )
    except Exception as e:
        logger.warning(f"[LangChain] call_llm failed, heuristic fallback: {e}")
        try:
            from backend.core.heuristics import build_heuristic_advisory

            fallback = build_heuristic_advisory(user_input)
            if isinstance(fallback, str):
                return fallback
            import json as _json

            return _json.dumps(fallback, ensure_ascii=False)
        except Exception:
            return (
                "I could not reach the language model right now. "
                f"Your question was: {user_input[:200]}"
            )
