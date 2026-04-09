# app/utils/callbacks.py
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

from app.core.config import settings

# Graph node names we want to track — everything else (LLM chains, lambdas) is ignored
_TRACKED_NODES = {
    "db_retrieval", "designer", "concept_reviewer",
    "weapon_designer", "weapon_patcher", "tech_auditor",
    "payload_factory", "projectile_factory",
    "artist", "payload_validator", "power_budget",
}

_PROMPT_LOG_BASE = settings.BASE_DIR / "logs" / "prompts"


class AgentConsoleCallback(BaseCallbackHandler):
    def __init__(self, agent_name: str = "Agent"):
        self.agent_name = agent_name

    def on_llm_start(self, serialized, prompts, **kwargs):
        print(f"\n🧠 [{self.agent_name}] start design...")
        print(f"[{self.agent_name}] output: ", end="", flush=True)

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], **kwargs):
        print(f"\n🧠 [{self.agent_name}] start design")
        print(f"[{self.agent_name}] output: ", end="", flush=True)

    def on_llm_new_token(self, token: str, **kwargs):
        sys.stdout.write(token)
        sys.stdout.flush()

    def on_llm_end(self, response, **kwargs):
        print(f"\n✅ [{self.agent_name}] Design phase done！\n")

    def on_llm_error(self, error, **kwargs):
        print(f"\n❌ [{self.agent_name}] Severe Error: {error}\n")


class PromptLogCallback(BaseCallbackHandler):
    """Writes the exact prompt sent to the model to logs/prompts/{session_id}/{ts}_{agent}.txt"""

    def __init__(self, agent_name: str = "Agent", session_id: str = "default"):
        self.agent_name = agent_name
        self.session_id = session_id

    def _write(self, content: str):
        log_dir = _PROMPT_LOG_BASE / self.session_id
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        path = log_dir / f"{ts}_{self.agent_name}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], **kwargs):
        parts = []
        for msg_list in messages:
            for msg in msg_list:
                role = msg.type.upper()
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                parts.append(f"[{role}]\n{content}")
        self._write("\n\n" + ("=" * 60) + "\n\n".join(parts))

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._write("\n\n".join(prompts))


class TimingCallback(BaseCallbackHandler):
    """
    Passed to the top-level graph.ainvoke() to record per-node wall-clock time.
    LangGraph fires on_chain_start/end for each node execution.
    """
    def __init__(self):
        self._runs: Dict[str, tuple] = {}   # run_id -> (node_name, start_time)
        self.timings: Dict[str, float] = {} # node_name -> total seconds (accumulates retries)

    def on_chain_start(self, serialized, inputs, *, run_id, **kwargs):
        name = kwargs.get("name") or (serialized or {}).get("name", "")
        if name in _TRACKED_NODES:
            self._runs[str(run_id)] = (name, time.perf_counter())

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        entry = self._runs.pop(str(run_id), None)
        if entry:
            name, t0 = entry
            elapsed = round(time.perf_counter() - t0, 2)
            self.timings[name] = round(self.timings.get(name, 0.0) + elapsed, 2)

    def on_chain_error(self, error, *, run_id, **kwargs):
        self._runs.pop(str(run_id), None)

    def get_timings(self) -> Dict[str, float]:
        return dict(self.timings)


# ── WebSocket progress streaming ──────────────────────────────────────────────

_SANITIZE_SKIP_KEYS = frozenset({"engine_manual", "reference_weapons", "similar_weapons", "generated_icon_b64"})
_MAX_STR_LEN = 400
_MAX_LIST_LEN = 5


def _sanitize(data: Any, depth: int = 0) -> Any:
    """Recursively trim state data so it's safe to JSON-serialize and send over WebSocket."""
    if depth > 4:
        return "…"
    if isinstance(data, str):
        return data[:_MAX_STR_LEN] + "…" if len(data) > _MAX_STR_LEN else data
    if isinstance(data, bytes):
        return f"<bytes len={len(data)}>"
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if k in _SANITIZE_SKIP_KEYS or v is None:
                continue
            out[k] = _sanitize(v, depth + 1)
        return out
    if isinstance(data, list):
        trimmed = data[:_MAX_LIST_LEN]
        result = [_sanitize(x, depth + 1) for x in trimmed]
        if len(data) > _MAX_LIST_LEN:
            result.append(f"…+{len(data) - _MAX_LIST_LEN} more")
        return result
    if isinstance(data, (int, float, bool)) or data is None:
        return data
    # Fallback for LangChain objects / other types
    return str(data)[:_MAX_STR_LEN]


class WebSocketProgressCallback(BaseCallbackHandler):
    """
    Streams per-node pipeline progress events to a connected debug WebSocket client.
    Errors are caught internally — pipeline execution is never interrupted.
    """

    def __init__(self, send_fn, session_id: str):
        """
        send_fn: async callable (dict) -> None that broadcasts the payload to all subscribers.
        Captured at construction time from async context so thread-pool callbacks can schedule it.
        """
        self._send_fn = send_fn
        self._session_id = session_id
        # run_id -> (node_name, perf_counter_start)  — tracked chains
        self._runs: Dict[str, tuple] = {}
        self._active_node: str | None = None
        # llm_run_id -> node_name  — maps each LLM call back to its parent node (parallel-safe)
        self._llm_run_to_node: Dict[str, str] = {}
        # Per-node trace: node_name -> {inputs, outputs, duration_secs}
        self._trace: Dict[str, dict] = {}
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def _schedule(self, payload: dict):
        """Thread-safe fire-and-forget: schedule a broadcast on the main event loop."""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send(payload), self._loop)
        except Exception as e:
            print(f"[ProgressCB] schedule failed: {e}")

    async def _send(self, payload: dict):
        try:
            await self._send_fn(payload)
            print(f"[ProgressCB] sent: {payload.get('type')} node={payload.get('node', '-')}")
        except Exception as e:
            print(f"[ProgressCB] send error: {e}")

    def on_chain_start(self, serialized, inputs, *, run_id, **kwargs):
        name = kwargs.get("name") or (serialized or {}).get("name", "")
        if name not in _TRACKED_NODES:
            return
        self._runs[str(run_id)] = (name, time.perf_counter())
        self._active_node = name
        sanitized_inputs = _sanitize(inputs)
        self._trace[name] = {"inputs": sanitized_inputs, "outputs": None, "duration_secs": None}
        self._schedule({
            "type": "node_start",
            "node": name,
            "session_id": self._session_id,
            "inputs": sanitized_inputs,
        })

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        """Record node mapping for non-chat models (e.g. Ollama)."""
        if self._active_node:
            self._llm_run_to_node[str(run_id)] = self._active_node

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        """Record which node this LLM call belongs to (parallel-safe via run_id)."""
        if self._active_node:
            self._llm_run_to_node[str(run_id)] = self._active_node

    def on_chat_model_end(self, response, *, run_id, **kwargs):
        """Chat models (Gemini, OpenAI) fire this instead of on_llm_end."""
        self.on_llm_end(response, run_id=run_id, **kwargs)

    def on_llm_end(self, response, *, run_id, **kwargs):
        """Capture token usage and attribute to the correct node via run_id mapping."""
        node = self._llm_run_to_node.pop(str(run_id), None) or self._active_node
        if not node:
            return
        prompt = completion = total = 0
        lo = response.llm_output or {}

        # 1. OpenAI-style: llm_output["token_usage"]
        tu = lo.get("token_usage") or lo.get("usage_metadata") or lo.get("usage") or {}
        if tu:
            prompt     = tu.get("prompt_tokens",     tu.get("input_tokens",  0)) or 0
            completion = tu.get("completion_tokens", tu.get("output_tokens", 0)) or 0
            total      = tu.get("total_tokens", 0) or (prompt + completion)

        # 2. Gemini / LangChain ≥0.2: usage_metadata on the AIMessage object
        if not total and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", gen)
                    um  = getattr(msg, "usage_metadata", None)
                    if um:
                        prompt     = um.get("input_tokens",  0) or 0
                        completion = um.get("output_tokens", 0) or 0
                        total      = um.get("total_tokens",  prompt + completion) or (prompt + completion)
                        break
                    gi = getattr(gen, "generation_info", None) or {}
                    if gi.get("eval_count"):
                        prompt     = gi.get("prompt_eval_count", 0) or 0
                        completion = gi.get("eval_count", 0) or 0
                        total      = prompt + completion
                        break
                if total:
                    break

        if not total:
            print(f"[TokenCB] {node}: no token data (llm_output keys={list(lo.keys())})")
            return
        print(f"[TokenCB] {node}: prompt={prompt} completion={completion} total={total}")
        if node not in self._trace:
            self._trace[node] = {"inputs": None, "outputs": None, "duration_secs": None}
        prev = self._trace[node].get("tokens") or {"prompt": 0, "completion": 0, "total": 0}
        self._trace[node]["tokens"] = {
            "prompt":     prev["prompt"]     + prompt,
            "completion": prev["completion"] + completion,
            "total":      prev["total"]      + total,
        }

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        entry = self._runs.pop(str(run_id), None)
        if not entry:
            return
        name, t0 = entry
        duration = round(time.perf_counter() - t0, 2)
        if self._active_node == name:
            self._active_node = None
        sanitized_outputs = _sanitize(outputs)
        if name not in self._trace:
            self._trace[name] = {"inputs": None, "outputs": None, "duration_secs": None}
        self._trace[name]["outputs"] = sanitized_outputs
        self._trace[name]["duration_secs"] = duration
        self._schedule({
            "type": "node_end",
            "node": name,
            "session_id": self._session_id,
            "outputs": sanitized_outputs,
            "duration_secs": duration,
        })

    def on_chain_error(self, error, *, run_id, **kwargs):
        entry = self._runs.pop(str(run_id), None)
        if not entry:
            return
        name, t0 = entry
        duration = round(time.perf_counter() - t0, 2)
        if self._active_node == name:
            self._active_node = None
        if name in self._trace:
            self._trace[name]["duration_secs"] = duration
        self._schedule({
            "type": "node_error",
            "node": name,
            "session_id": self._session_id,
            "error": str(error),
            "duration_secs": duration,
        })

    def on_llm_new_token(self, token: str, **kwargs):
        if not token or not self._active_node:
            return
        self._schedule({
            "type": "token",
            "node": self._active_node,
            "session_id": self._session_id,
            "token": token,
        })

    def get_trace(self) -> Dict[str, dict]:
        """Return accumulated per-node trace after pipeline completes."""
        return dict(self._trace)


def make_callbacks(agent_name: str, session_id: str = "default",
                   parent_config: dict | None = None) -> list:
    """Return callbacks for an agent, merging inherited parent callbacks (e.g. TimingCallback,
    WebSocketProgressCallback) so token/timing tracking propagates into each LLM call."""
    local = [
        AgentConsoleCallback(agent_name=agent_name),
        PromptLogCallback(agent_name=agent_name, session_id=session_id),
    ]
    raw = (parent_config or {}).get("callbacks")
    # LangGraph passes an AsyncCallbackManager, not a plain list — extract its handlers
    if hasattr(raw, "handlers"):
        inherited = raw.handlers
    elif isinstance(raw, list):
        inherited = raw
    else:
        inherited = []
    local_types = {type(c) for c in local}
    extra = [c for c in inherited if type(c) not in local_types]
    return local + extra