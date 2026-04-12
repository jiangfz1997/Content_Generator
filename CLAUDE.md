# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A Python async WebSocket server that acts as an AI backend for a Unity game. It receives weapon generation requests from Unity via WebSocket and uses a multi-agent LangGraph pipeline to procedurally generate game weapon data (JSON) using a local Ollama LLM.

## Running the Server

```bash
# Start the WebSocket server (listens on ws://localhost:8080)
python app/websocket/main.py

# Minimal connectivity test (echo PING -> TestEvent)
python test_server.py
```

## Running Tests

```bash
# Pipeline unit test (no server needed, calls LLM directly)
pytest tests/test_forge_pipeline.py -v -s

# WebSocket integration test (requires server running first)
pytest tests/test_websocket_agent.py -v -s
```

## Environment Variables (`.env`)

- `OLLAMA_URL` — Ollama base URL (default: `http://localhost:11434`)
- `OPENAI_API_KEY` — OpenAI-compatible API key (used by `gpt_model`)
- `OPENAI_BASE_URL` — OpenAI-compatible endpoint
- `ONLINE_NANO_MODEL` — Model name for the online fallback

## Architecture

### Request Flow

Unity sends a `NetPacket` JSON envelope `{"msgType": "...", "payload": {...}}` over WebSocket. The server routes by `payload.action`. A `generate_weapon` action invokes `global_graph.ainvoke(...)` and sends back a `WeaponGenerateEvent` packet.

### LangGraph Pipeline (`app/core/workflow.py`)

The `global_graph` is a `StateGraph[GlobalState]` with two gated feedback loops:

```
START → designer → concept_reviewer
                        ↓ (gatekeeper 1: idea failed → back to designer)
                   weapon_designer → tech_auditor
                                          ↓ (gatekeeper 2: tech failed → back to weapon_designer)
                                         END
```

- **Gatekeeper 1** checks `state["is_idea_passed"]` — routes back to `designer` if False.
- **Gatekeeper 2** checks `state["is_final_passed"]` — routes back to `weapon_designer` if False. Strictness relaxes after each retry (`audit_attempts`).

### Agents (each is a singleton in its module)

| Agent | File | Node method | LLM output schema |
|---|---|---|---|
| `designer_agent` | `app/agents/designer/graph.py` | `planning_node` | `DesignBlueprint` |
| `reviewer_agent` | `app/agents/reviewer/graph.py` | `idea_audit_node`, `tech_audit_node` | `IdeaReviewResult`, `TechAuditResult` |
| `weapon_agent` | `app/agents/weapon/graph.py` | `crafting_node` | `WeaponSchema` |
| `summarizer_agent` | `app/agents/summarizer/graph.py` | `summarize_engine()` | `FinalEngineManual` |

All agents use `with_structured_output(PydanticSchema)` for reliable JSON extraction, and attach `AgentConsoleCallback` for streaming console output.

### Shared Services (singletons)

- **`llm_service`** (`app/services/llm_service.py`) — Three models: `model` (full Ollama), `mini_model` (Ollama, token-limited for reviewers), `gpt_model` (OpenAI-compatible fallback). Default model: `qwen2.5-coder:14b`.
- **`engine_docs_manager`** (`app/services/engine_docs_manager.py`) — Loads `app/data/instruction_manual.md` into memory (cached). If missing, calls `summarizer_agent.summarize_engine()` to regenerate it from raw schema files.
- **`primitive_registry`** (`app/services/primitive_registery.py`) — Reads `PrimitivesSchema.md`, `MotionPrimitivesSchema.md`, and all `app/data/payloads/*.json` files.

### Prompts

YAML prompt templates live in `app/core/prompts/`. They are loaded with `langchain_core.prompts.load_prompt()`. The `GLOBAL_DESIGN_CONSTITUTION` string (`app/core/global_prompts.py`) is injected at the front of select prompts via `inject_prompts()`.

### State (`app/core/state.py`)

`GlobalState` is a `TypedDict` threaded through the entire graph. Key fields:
- Input: `biome`, `level`, `materials`, `weapons`, `prompt`
- Mid-pipeline: `design_concept`, `is_idea_passed`, `idea_feedback`
- Output: `final_output` (serialized `WeaponSchema`), `is_final_passed`, `tech_feedback`
- Memory: `generation_history` (list of previously crafted weapon IDs to avoid duplicates)

### Data Files

- `app/data/PrimitivesSchema.md` — Logic primitive definitions (read by `primitive_registry`)
- `app/data/MotionPrimitivesSchema.md` — Motion primitive definitions
- `app/data/payloads/*.json` — One JSON file per payload effect; filename stem = payload ID
- `app/data/instruction_manual.md` — Cached engine manual (auto-generated; safe to delete to force regeneration)

### WebSocket Protocol

All messages use a `NetPacket` envelope: `{"msgType": str, "payload": dict}`. The only implemented action is `generate_weapon`. A `ping` action returns a `Pong` response.

## Key Design Patterns

- **All agent instances are module-level singletons** — instantiated at import time. Import errors (e.g., missing prompt YAML) will crash at startup.
- **CoT via leading Pydantic fields** — Schemas place `analysis`/`reasoning` fields first so the LLM "thinks before answering" within structured output.
- **`pyrootutils`** is used in `app/core/config.py` to anchor all paths to the `.git` root — always run from the project root.
