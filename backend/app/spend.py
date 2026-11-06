"""Measured API spend: every paid call reports the usage OpenAI billed for it.

A ``Meter`` collects that usage for a job or a step. Meters nest: opening one
inside another records into both, so a job's total includes its transcription
and the episode keeps the transcription's own cost. The current meter lives in
a context variable, so code that fans out to thread pools submits through
``submit`` to carry it along.
"""

from __future__ import annotations

import contextvars
import logging
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Executor, Future
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class ModelSpend:
    usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0  # for models billed by audio duration
    calls: int = 0


@dataclass
class Meter:
    parent: Meter | None = None
    by_model: dict[str, ModelSpend] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def usd(self) -> float:
        with self._lock:
            return sum(m.usd for m in self.by_model.values())

    def add(self, model: str, usd: float, inp: int = 0, out: int = 0, seconds: float = 0.0):
        with self._lock:
            m = self.by_model.setdefault(model, ModelSpend())
            m.usd += usd
            m.input_tokens += inp
            m.output_tokens += out
            m.seconds += seconds
            m.calls += 1
        if self.parent is not None:
            self.parent.add(model, usd, inp, out, seconds)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            models = {
                k: {
                    "usd": round(v.usd, 6),
                    "input_tokens": v.input_tokens,
                    "output_tokens": v.output_tokens,
                    "seconds": round(v.seconds, 1),
                    "calls": v.calls,
                }
                for k, v in self.by_model.items()
            }
        return {"usd": round(sum(m["usd"] for m in models.values()), 6), "by_model": models}


_current: contextvars.ContextVar[Meter | None] = contextvars.ContextVar("meter", default=None)


@contextmanager
def metering() -> Iterator[Meter]:
    """Open a meter nested in the current one (if any) for the duration of the block."""
    meter = Meter(parent=_current.get())
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)


def submit[T](pool: Executor, fn: Callable[..., T], *args: Any) -> Future[T]:
    """``pool.submit`` that keeps the current meter (and other context) in the worker."""
    return pool.submit(contextvars.copy_context().run, fn, *args)


def run_with[T](meter: Meter, fn: Callable[..., T], *args: Any) -> T:
    """Call ``fn`` with ``meter`` as the current meter (for a job's worker thread)."""
    token = _current.set(meter)
    try:
        return fn(*args)
    finally:
        _current.reset(token)


# ----------------------------------------------------------------------------- prices


def _token_prices(model: str) -> tuple[float, float] | None:
    """USD per 1M (input, output) tokens for a model this app calls, if known."""
    s = get_settings()
    bare = model.split("/", 1)[-1]  # OpenRouter ids carry a vendor prefix
    if bare == s.diarize_model:
        return s.price_diarize_input_per_mtok, s.price_diarize_output_per_mtok
    if bare == s.llm_model.split("/", 1)[-1]:
        return s.price_llm_input_per_mtok, s.price_llm_output_per_mtok
    if bare == s.embedding_model:
        return s.price_embedding_per_mtok, 0.0
    return None


def record(model: str, usage: Any) -> None:
    """Record one call's billed usage (an SDK usage object or dict) on the current meter.

    Understands transcription usage (``input_tokens``/``output_tokens`` or
    ``type="duration"`` with ``seconds``), chat usage (``prompt_tokens``/
    ``completion_tokens``) and embedding usage (``prompt_tokens``).
    """
    meter = _current.get()
    if meter is None or usage is None:
        return
    s = get_settings()
    if _get(usage, "type") == "duration":
        seconds = float(_get(usage, "seconds", 0.0) or 0.0)
        meter.add(model, seconds / 60.0 * s.price_text_transcribe_per_min, seconds=seconds)
        return
    inp = int(_get(usage, "input_tokens", None) or _get(usage, "prompt_tokens", 0) or 0)
    out = int(_get(usage, "output_tokens", None) or _get(usage, "completion_tokens", 0) or 0)
    prices = _token_prices(model)
    if prices is None:
        log.warning("spend: no price configured for model %s; recording tokens only", model)
        prices = (0.0, 0.0)
    meter.add(model, inp / 1e6 * prices[0] + out / 1e6 * prices[1], inp, out)
