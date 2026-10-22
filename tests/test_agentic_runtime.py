"""
backend/core/langchain_adapter.py — LangChain integration (required only when available).

Every LLM call flows through ``backend.core.llm_client.call_llm``.
``GrameenChatModel`` is a LangChain ``BaseChatModel`` wrapper around it, so
provider priority / fallback / caching / token budgets stay in one place.

All helpers use LCEL model chaining (``prompt | model | output_parser``) and
never raise — deterministic heuristic fallback is always available.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
    from langchain_core.runnables import Runnable
    from langchain_core.tools import tool as lc_tool
    LANGCHAIN_AVAILABLE = True
except Exception:  # pragma: no cover - dependency may be absent
    BaseChatModel = object  # type: ignore
    AIMessage = HumanMessage = SystemMessage = BaseMessage = object  # type: ignore
    ChatGeneration = ChatResult = None  # type: ignore
    ChatPromptTemplate = None  # type: ignore
    StrOutputParser = JsonOutputParser = None  # type: ignore
    Runnable = object  # type: ignore
    def lc_tool(func):
        return func
    LANGCHAIN_AVAILABLE = False

logger = logging.getLogger(__name__)


def _run_coro_sync(coro):
    """Run an async coroutine from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class GrameenChatModel(BaseChatModel):
    """LangChain chat model backed by the project's multi-provider llm_client."""

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
            else:
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
    output_parser: Optional[Runnable] = None,
) -> Optional[Runnable]:
    """Build an LCEL advisory chain when LangChain is installed."""
    if not LANGCHAIN_AVAILABLE or ChatPromptTemplate is None or StrOutputParser is None:
        return None

    parser = output_parser or StrOutputParser()
    safe_system = system_prompt.replace("{", "{{").replace("}", "}}")
    prompt = ChatPromptTemplate.from_messages(
        [("system", safe_system), ("human", "{input}")]
    )
    llm = GrameenChatModel(
        agent_hint=agent_hint, temperature=temperature, max_tokens=max_tokens
    )
    return prompt | llm | parser


def build_json_advisory_chain(
    system_prompt: str,
    agent_hint: str = "default",
    temperature: float = 0.4,
    max_tokens: int = 600,
) -> Optional[Runnable]:
    if not LANGCHAIN_AVAILABLE:
        return None
    return build_advisory_chain(
        system_prompt,
        agent_hint=agent_hint,
        temperature=temperature,
        max_tokens=max_tokens,
        output_parser=JsonOutputParser(),
    )


async def run_prompt(
    chain_or_prompt: Any,
    user_input: str,
    *,
    agent_hint: str = "default",
    system_prompt: str = "You are a helpful business advisor for micro-entrepreneurs in India.",
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> str:
    """Run a LangChain chain (or plain prompt) with heuristic fallback. Never raises."""
    from backend.core.llm_client import call_llm

    if chain_or_prompt is not None and hasattr(chain_or_prompt, "ainvoke"):
        try:
            result = await chain_or_prompt.ainvoke({"input": user_input})
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.warning("[LangChain] chain.ainvoke failed, falling back to call_llm: %s", e)

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
        logger.warning("[LangChain] call_llm failed, heuristic fallback: %s", e)
        try:
            from backend.core.heuristics import build_heuristic_advisory, extract_topic

            fallback = build_heuristic_advisory(extract_topic(user_input))
            if isinstance(fallback, str):
                return fallback
            import json as _json

            return _json.dumps(fallback, ensure_ascii=False)
        except Exception:
            return (
                "I could not reach the language model right now. "
                f"Your question was: {user_input[:200]}"
            )


def agentic_status() -> Dict[str, Any]:
    """Describe the agentic engine + its tools (never raises)."""
    info: Dict[str, Any] = {
        "langchain_available": LANGCHAIN_AVAILABLE,
        "langgraph_available": False,
        "engine": "native",
        "nodes": [],
        "edges": [],
        "tools": [],
    }
    try:
        from backend.agentic import engine_name
        from backend.agentic.graph import graph_topology
        from backend.agentic.tools import tool_names

        info["langgraph_available"] = True
        info["engine"] = engine_name()
        info["nodes"] = graph_topology().get("nodes", [])
        info["edges"] = graph_topology().get("edges", [])
        info["tools"] = tool_names()
    except Exception as e:
        logger.debug("[LangChain] agentic_status unavailable: %s", e)
    return info
