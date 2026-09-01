"""Provider-agnostic LLM client for root-cause analysis.

Only ever receives pre-correlated, structured evidence — never a raw data
dump. Returns a structured RCAResult with cause, confidence, evidence, and
playbook fields. (SKILLS.md: structured LLM prompting requirement.)

Supported providers (set via LLM_PROVIDER env var):
  mock       — deterministic, no network; for tests and offline demo
  openai     — OpenAI Chat Completions, JSON mode (requires LLM_API_KEY)
  anthropic  — Anthropic Messages API (requires LLM_API_KEY)

Use create_llm_client() to get the right implementation at startup.
"""

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests


# ---------------------------------------------------------------------------
# Output data model
# ---------------------------------------------------------------------------

@dataclass
class RCAResult:
    """Structured root-cause analysis result.

    Fields mirror the ARCHITECTURE.md LLM contract:
      cause      — one-sentence description of the root cause
      confidence — float in [0.0, 1.0]
      evidence   — list of human-readable evidence strings drawn from the
                   correlated payload; must contain ≥1 item
      playbook   — ordered list of remediation steps

    id is assigned at creation and carried through the approval flow (task 6.1).
    """

    cause: str
    confidence: float
    evidence: List[str]
    playbook: List[str]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if not self.evidence:
            raise ValueError("evidence must contain at least one item")
        if not self.cause:
            raise ValueError("cause must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cause": self.cause,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "playbook": self.playbook,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RCAResult":
        """Deserialise from a dict (e.g. parsed LLM JSON response)."""
        return cls(
            cause=str(data["cause"]),
            confidence=float(data["confidence"]),
            evidence=[str(e) for e in data["evidence"]],
            playbook=[str(s) for s in data.get("playbook", [])],
            id=str(data.get("id") or str(uuid.uuid4())),
        )


# ---------------------------------------------------------------------------
# Prompt builder — shared across all real providers
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior site reliability engineer performing root-cause analysis on \
a production incident. You will be given pre-correlated telemetry evidence \
(traces, logs, metrics) from an OpenTelemetry-instrumented system. Your job \
is to identify the single most likely root cause and produce a remediation \
playbook.

Respond with a JSON object — no markdown fences, no extra keys — matching \
this exact schema:
{
  "cause": "<one-sentence root cause>",
  "confidence": <float 0.0–1.0>,
  "evidence": ["<evidence string>", ...],
  "playbook": ["<step 1>", "<step 2>", ...]
}

Rules:
- confidence reflects how certain you are given the evidence (0.9+ means \
  unambiguous; 0.5–0.8 means plausible but incomplete; <0.5 means uncertain).
- evidence must contain only observations drawn from the provided telemetry — \
  never invent data not present in the input.
- playbook steps must be concrete and ordered; generic advice is not acceptable.
"""


def _build_user_message(correlation_dict: Dict[str, Any]) -> str:
    """Serialize the correlation payload into a compact, structured prompt.

    Deliberately limits what goes into the prompt to what is actually useful
    for RCA: error traces, impacted services, representative metrics. This
    keeps token usage bounded and prevents the LLM from hallucinating over
    noise.
    """
    lines: List[str] = []

    tw = correlation_dict.get("time_window", {})
    lines.append(f"Time window: {tw.get('start')} – {tw.get('end')} (Unix epoch seconds)")

    impacted = correlation_dict.get("services_impacted", [])
    lines.append(f"Services impacted: {', '.join(impacted) if impacted else 'none identified'}")

    total = correlation_dict.get("total_traces", 0)
    errors = correlation_dict.get("error_traces", 0)
    lines.append(f"Traces observed: {total} total, {errors} with errors")

    # Include only error traces (up to 5) to keep prompt size bounded
    error_traces = [
        t for t in correlation_dict.get("correlated_traces", [])
        if t.get("has_errors")
    ][:5]

    if error_traces:
        lines.append("\nError traces (sampled):")
        for tr in error_traces:
            lines.append(f"  trace_id={tr.get('trace_id')} root_service={tr.get('root_service')}")
            lines.append(f"  services_involved={tr.get('services_involved')}")
            for sp in tr.get("spans", [])[:10]:
                if sp.get("status_code") == "Error":
                    lines.append(
                        f"    SPAN {sp.get('service_name')}/{sp.get('span_name')} "
                        f"status={sp.get('status_code')} "
                        f"msg={sp.get('status_message', '')[:120]}"
                    )
            for lg in tr.get("logs", [])[:5]:
                if lg.get("severity", "").upper() in ("ERROR", "FATAL"):
                    lines.append(
                        f"    LOG  {lg.get('service_name')} [{lg.get('severity')}] "
                        f"{str(lg.get('body', ''))[:120]}"
                    )

    metrics = correlation_dict.get("metrics", [])
    if metrics:
        lines.append("\nKey metrics (sampled — last value per series):")
        for m in metrics[:5]:
            for series in m.get("series", [])[:3]:
                samples = series.get("samples", [])
                if samples:
                    last = samples[-1]
                    lines.append(
                        f"  {m.get('metric_name')} labels={series.get('labels')} "
                        f"last_value={last.get('value')} at t={last.get('timestamp')}"
                    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMClient(ABC):
    """Abstract LLM client. All implementations must return a validated RCAResult."""

    @abstractmethod
    def generate(self, correlation_dict: Dict[str, Any]) -> RCAResult:
        """Given a CorrelationPayload dict, return a structured RCAResult."""
        ...


# ---------------------------------------------------------------------------
# Mock provider — deterministic, no network
# ---------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """Deterministic mock for tests and offline demos.

    Optionally accepts a pre-baked response dict to return; otherwise builds
    a plausible result from whatever is in the correlation payload.
    """

    def __init__(self, fixed_response: Optional[Dict[str, Any]] = None) -> None:
        self._fixed = fixed_response

    def generate(self, correlation_dict: Dict[str, Any]) -> RCAResult:
        if self._fixed is not None:
            return RCAResult.from_dict(self._fixed)

        impacted = correlation_dict.get("services_impacted", ["unknown-service"])
        root = impacted[0] if impacted else "unknown-service"
        errors = correlation_dict.get("error_traces", 0)
        total = correlation_dict.get("total_traces", 1) or 1
        error_rate = round(errors / total, 2)

        # Harvest one real error message from the payload if present
        evidence_msgs: List[str] = []
        for tr in correlation_dict.get("correlated_traces", []):
            if tr.get("has_errors"):
                for sp in tr.get("spans", []):
                    if sp.get("status_code") == "Error" and sp.get("status_message"):
                        evidence_msgs.append(
                            f"{sp['service_name']}/{sp['span_name']}: {sp['status_message'][:100]}"
                        )
                for lg in tr.get("logs", []):
                    if lg.get("severity", "").upper() in ("ERROR", "FATAL"):
                        evidence_msgs.append(
                            f"{lg['service_name']} [{lg['severity']}]: {str(lg.get('body', ''))[:100]}"
                        )
            if len(evidence_msgs) >= 3:
                break

        if not evidence_msgs:
            evidence_msgs = [f"Elevated error rate detected on {root} ({error_rate * 100:.0f}% of traces)"]

        return RCAResult(
            cause=f"Root cause identified in {root}: elevated error rate ({error_rate * 100:.0f}% of sampled traces show failures)",
            confidence=min(0.5 + error_rate * 0.4, 0.95),
            evidence=evidence_msgs[:5],
            playbook=[
                f"1. Check recent deployments or config changes to {root}",
                f"2. Review {root} pod/container logs for stack traces",
                "3. Verify downstream dependencies (databases, caches, external APIs) are healthy",
                "4. Roll back the most recent deployment if errors began after it",
                "5. Escalate to on-call if error rate does not drop within 10 minutes after rollback",
            ],
        )


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------

class OpenAILLMClient(LLMClient):
    """OpenAI Chat Completions with JSON mode.

    Model defaults to gpt-4o-mini (cheap, fast, supports JSON mode). Override
    via the model kwarg in create_llm_client().
    """

    _API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("OpenAI provider requires LLM_API_KEY to be set")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def generate(self, correlation_dict: Dict[str, Any]) -> RCAResult:
        user_msg = _build_user_message(correlation_dict)
        payload = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.2,
        }
        resp = requests.post(
            self._API_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return RCAResult.from_dict(json.loads(content))


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------

class AnthropicLLMClient(LLMClient):
    """Anthropic Messages API (claude-3-haiku by default).

    JSON mode is enforced via a prefill that opens the JSON block so the
    model is forced to complete it before any prose.
    """

    _API_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("Anthropic provider requires LLM_API_KEY to be set")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def generate(self, correlation_dict: Dict[str, Any]) -> RCAResult:
        user_msg = _build_user_message(correlation_dict)
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_msg},
                # Prefill forces JSON-only response
                {"role": "assistant", "content": "{"},
            ],
        }
        resp = requests.post(
            self._API_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self._API_VERSION,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        # Reconstruct the full JSON — the prefill "{" is not in content
        raw = "{" + resp.json()["content"][0]["text"]
        return RCAResult.from_dict(json.loads(raw))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm_client(
    provider: str,
    api_key: str = "",
    **kwargs: Any,
) -> LLMClient:
    """Return the appropriate LLMClient for the configured provider.

    Args:
        provider:  Value of LLM_PROVIDER env var ("mock", "openai", "anthropic").
        api_key:   Value of LLM_API_KEY env var; required for real providers.
        **kwargs:  Forwarded to the provider constructor (e.g. model=, timeout=).

    Raises:
        ValueError: for unknown provider names.
    """
    provider = (provider or "mock").strip().lower()
    if provider == "mock" or not provider:
        fixed = kwargs.pop("fixed_response", None)
        return MockLLMClient(fixed_response=fixed)
    if provider == "openai":
        return OpenAILLMClient(api_key=api_key, **kwargs)
    if provider == "anthropic":
        return AnthropicLLMClient(api_key=api_key, **kwargs)
    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        f"Supported values: mock, openai, anthropic"
    )
