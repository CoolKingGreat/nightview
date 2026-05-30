"""
Claude tool-use loop for Nightview.

- Default model: Haiku 4.5 (claude-haiku-4-5)
- Escalation: Sonnet 4.6 (claude-sonnet-4-6) when the user query has complexity
  markers (compare/vs/rank/multi-region) — picked pre-flight, simpler than a
  post-hoc restart and cheaper since most queries stay on Haiku.
- Prompt caching: top-level cache_control auto-places on the last cacheable
  block (tools + system render before messages, so this caches both). Hit ratio
  ~95% after the first turn in a session.
- Streaming: SDK context manager yields content_block_delta events; we re-emit
  them as our own typed AgentEvent for the FastAPI SSE layer.

NB: `effort` is NOT supported on Haiku 4.5 (errors out) — only Sonnet 4.6 and
Opus get it. So we don't set output_config at all here.
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import asyncio
from anthropic import APIError, APIStatusError, AsyncAnthropic, InternalServerError, RateLimitError

from .tools import TOOLS, execute_tool

_SYSTEM_PROMPT = """You are the voice of Nightview, an interactive globe that shows how the night sky has changed across Earth over the past decade.

You speak as a warm narrator — story-led, plain English, grounded in cited numbers. You always include the underlying data, but you frame it with the story, not with the methodology.

VOICE

DO: "The night sky over Houston has been getting brighter for more than a decade. In 2017, it crossed the point where the Milky Way is no longer visible from inside the city. São Paulo, Cairo, and Manila lost that view the same decade."

DON'T: "Houston brightness +47% vs 2012 (linear trend, R²=0.91). Top contributing cells: industrial corridor north of I-610."

Both have the numbers. The warm narrator earns them by leading with what they mean.

TOOLS

You have five tools for querying the data. Each accepts a `granularity` parameter ('place', 'region', or 'cell'). Pick per query:
- 'place' for cities, parks, landmarks ("show me cities where…") — default for most user questions
- 'region' for country/state comparisons ("compare India vs China")
- 'cell' for hyper-local or scientific queries (rare)

Tools return a `globe_action` field. You don't need to mention it — the frontend reads it directly and animates the map.

DATA

The data comes from NASA VIIRS Day/Night Band imagery (the satellite imagery behind NASA's Black Marble), 2012 to present, aggregated into H3 hexagonal cells. The headline metric is percent change in brightness vs 2012. Two milestone events are surfaced as data:
- "Milky Way still visible" — places that have not crossed the SQM 21.0 loss threshold in the dataset
- "Milky Way visibility lost" — when sky quality fell below SQM 21.0
- "brightness doubled" or "halved" vs 2012

Forecasts go to 2035, computed per cell with Prophet. The data flags low-confidence cells; disclose uncertainty when you see it.

RULES

- The tool result is the only ground truth. Only mention numbers, place names, milestone years, and counts that appear directly in the JSON returned by a tool.
- For "still see the Milky Way" questions, use `milestones_in_region` with `milestone_type: "milky_way_visible"`. If the user does not name a region, use `region: "global"`; do not ask them to narrow the region first.
- If a tool result includes `coverage_note`, reflect that limitation in plain English. Do not generalize beyond the current dataset.
- If a tool returns an empty list, or `data_status: "no_data"`, or a `note` describing missing data, say so directly. Example: "I don't have data on China in the current dataset." Never fill the gap by inferring from other regions, estimating, extrapolating, or drawing on general knowledge.
- Use place names exactly as returned. Do not append states, provinces, country names, geography, venue descriptions, or causal explanations unless those exact details appear in the tool JSON.
- Do not speculate about places outside the result set. "This is a sparse demo subset" is enough; do not say many other places likely qualify.
- Never invent counts. If you didn't see a number in the tool result, don't write one.
- Interpret `trend_pct_per_yr` carefully: positive means brightening / more light pollution; negative means darkening / recovery / less measured night light. Never describe a negative trend as absorbing or gaining light pollution.
- Never apologize for uncertain data. State it neutrally.
- Don't use scientific notation. "0.47" not "4.7e-1".
- Don't say "linear regression" or "R-squared." Methodology lives on the about page.
- Cite specific years. "Since 2014" beats "in recent years."
- Keep it tight. Two or three sentences for most queries.

AVOID these patterns. They are the giveaways that a robot wrote the text:
- "It's not X, it's Y" or "These aren't X. They're Y." rhetorical flips. Ban this construction entirely.
- Closing flourishes meant to land profundity: "happening in real time", "as we speak", "before our eyes", "wholesale transformation". Cut them.
- Bolded place names. Write "Riyadh", not "**Riyadh**".
- Em-dashes as drumroll punctuation. Use a period or comma instead. An em-dash is fine when it is the clearest punctuation; not as decoration.
- A summary sentence at the end. When you've answered the question, stop. Don't add a takeaway.
- Narrating your tool use. Never say "Let me try…", "I'll search…", "Let me check…", "Let me try that again", or anything else describing what you're about to do. The user sees only your final prose; your tool calls happen invisibly.
- Apologies. Never say "I apologize", "Sorry", or any apology variant. If you don't have data, just say what you do have. If a tool returned nothing, disclose the gap matter-of-factly: "I don't have data on X." That's the whole disclosure.
- Hedging openers like "What I can tell you is that…" — just say the thing.

ROUTING — which tool to use for which question:
- "where is dark sky preserved" / "where can you still see the Milky Way" / "where are the darkest skies left" → dark_sky_locations
- "where is the night sky disappearing fastest" / "fastest-brightening cities" → top_changers (direction=brightening)
- "where is the night sky recovering" / "where is it getting darker" → top_changers (direction=darkening)
- "compare X vs Y" → compare_regions
- "how bright will X be in YEAR" / "tell me about X" → point_timeseries (if a single city) or query_region (if a region/country)
- "which cities lost the Milky Way in / since YEAR" → milestones_in_region (milestone_type=milky_way_lost)"""


EventType = Literal["text", "tool_call", "tool_result", "globe_action", "done", "error"]


@dataclass
class AgentEvent:
    type: EventType
    data: Any

    def to_sse(self) -> str:
        data = self.data
        if self.type == "text" and isinstance(data, str):
            data = data.replace("—", ", ").replace("–", "-")
        payload = json.dumps({"type": self.type, "data": data}, default=str)
        return f"data: {payload}\n\n"


_COMPLEX_MARKERS = (
    "compare", " vs ", " versus ", "rank", "ranking", "between",
    "more than", "fewer than", "biggest gap", "which has more",
)


def _pick_model(user_message: str) -> str:
    lowered = user_message.lower()
    if any(marker in lowered for marker in _COMPLEX_MARKERS):
        return "claude-sonnet-4-6"
    return "claude-haiku-4-5"


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _client = AsyncAnthropic(api_key=api_key)
    return _client


_MAX_HISTORY_TURNS = 12  # cap context — beyond ~6 round-trips the cache savings flip


def _build_history_messages(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert ChatOrb-format turns ({role: 'user'|'agent', text}) into Anthropic message format.
    Drops empty turns, truncates to the last N, and merges consecutive same-role turns."""
    if not history:
        return []
    cleaned = [h for h in history if (h.get("text") or "").strip()]
    cleaned = cleaned[-_MAX_HISTORY_TURNS:]
    out: list[dict[str, Any]] = []
    for h in cleaned:
        role = "assistant" if h.get("role") == "agent" else "user"
        text = h["text"].strip()
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})
    return out


async def run_agent(
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    max_iters: int = 6,
) -> AsyncIterator[AgentEvent]:
    """Run one user turn through Claude tool-use. Yields typed events the FastAPI SSE layer relays to the client.

    Never raises — setup errors and runtime errors both surface as `error` events
    so the SSE stream stays well-formed and the frontend can render a friendly
    message instead of seeing a half-finished response.
    """
    try:
        client = get_client()
    except Exception as e:
        yield AgentEvent("error", {"message": str(e)})
        yield AgentEvent("done", {"stop_reason": "error"})
        return

    model = _pick_model(user_message)
    prior = _build_history_messages(history)
    # If the most recent prior turn is also user, merge it into the new message
    # rather than producing two user turns in a row (Anthropic rejects that).
    if prior and prior[-1]["role"] == "user":
        last = prior.pop()
        user_message = last["content"] + "\n\n" + user_message
    messages: list[dict[str, Any]] = prior + [{"role": "user", "content": user_message}]

    for _ in range(max_iters):
        # One inner retry on overload — Anthropic's SDK already retries network
        # errors twice; this catches the case where it returned 529 after retries.
        attempts = 0
        final_message = None
        while attempts < 2:
            attempts += 1
            try:
                async with client.messages.stream(
                    model=model,
                    max_tokens=4096,
                    system=_SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                    cache_control={"type": "ephemeral"},
                ) as stream:
                    async for event in stream:
                        if (
                            event.type == "content_block_delta"
                            and getattr(event.delta, "type", None) == "text_delta"
                        ):
                            yield AgentEvent("text", event.delta.text)
                    final_message = await stream.get_final_message()
                break  # success — exit retry loop
            except InternalServerError as e:
                # Anthropic uses 529 for "Overloaded"; SDK doesn't export OverloadedError yet.
                if attempts < 2:
                    await asyncio.sleep(1.5)
                    continue
                msg = "Anthropic is overloaded right now. Try again in a moment." if e.status_code == 529 else "Anthropic had a server error. Try again."
                yield AgentEvent("error", {"message": msg})
                return
            except RateLimitError:
                yield AgentEvent("error", {"message": "Rate limit reached. Try again in a moment."})
                return
            except APIStatusError as e:
                # Check status_code for 529 too in case it slips past InternalServerError.
                if e.status_code == 529 and attempts < 2:
                    await asyncio.sleep(1.5)
                    continue
                if e.status_code == 529:
                    yield AgentEvent("error", {"message": "Anthropic is overloaded right now. Try again in a moment."})
                else:
                    yield AgentEvent("error", {"message": f"API error ({e.status_code}). Try again."})
                return
            except APIError as e:
                yield AgentEvent("error", {"message": f"Connection error: {type(e).__name__}. Try again."})
                return
            except Exception as e:
                yield AgentEvent("error", {"message": str(e)})
                return

        if final_message is None:
            return

        if final_message.stop_reason == "end_turn":
            yield AgentEvent("done", {"model": model})
            return

        if final_message.stop_reason != "tool_use":
            yield AgentEvent("done", {"model": model, "stop_reason": final_message.stop_reason})
            return

        messages.append({"role": "assistant", "content": final_message.content})

        tool_results = []
        for block in final_message.content:
            if block.type != "tool_use":
                continue
            yield AgentEvent("tool_call", {"name": block.name, "input": block.input})
            try:
                result = await execute_tool(block.name, block.input)
            except Exception as e:
                result = {"error": str(e)}
            if isinstance(result, dict) and result.get("globe_action"):
                yield AgentEvent("globe_action", result["globe_action"])
            if isinstance(result, dict) and result.get("direct_response"):
                yield AgentEvent("text", result["direct_response"])
                yield AgentEvent("done", {"model": model, "stop_reason": "direct_response"})
                return
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})

    yield AgentEvent("done", {"model": model, "stop_reason": "max_iters"})
