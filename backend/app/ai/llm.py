"""LLM provider abstraction. The application never depends on the LLM being up (fallback mode)."""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    pass


class BaseLLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def generate(self, system: str, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str: ...

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "available": self.is_available()}


class NullProvider(BaseLLMProvider):
    name = "none"

    def is_available(self) -> bool:
        return False

    def generate(self, system: str, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        raise LLMUnavailableError("LLM disabled")


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout
        self._avail: tuple[float, bool] | None = None

    def is_available(self) -> bool:
        if self._avail and time.time() - self._avail[0] < 15:
            return self._avail[1]
        ok = False
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            if r.status_code == 200:
                names = [m.get("name", "") for m in r.json().get("models", [])]
                ok = (
                    any(n == self.model or (n.split(":")[0] == self.model.split(":")[0] and n == self.model) for n in names)
                    or self.model in names
                )
        except (httpx.HTTPError, ValueError):
            ok = False
        self._avail = (time.time(), ok)
        return ok

    def generate(self, system: str, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": temperature, "seed": 42},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if json_mode:
            payload["format"] = "json"
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
            return str(r.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            self._avail = (time.time(), False)
            raise LLMUnavailableError(f"ollama request failed: {type(exc).__name__}") from exc


def get_llm(settings: Settings | None = None) -> BaseLLMProvider:
    s = settings or get_settings()
    if not s.llm_enabled:
        return NullProvider()
    if s.llm_provider == "ollama":
        return OllamaProvider(s.ollama_base_url, s.active_llm_model, s.llm_timeout_seconds)
    logger.warning("unknown LLM provider '%s'; running without LLM", s.llm_provider)
    return NullProvider()


def extract_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from raw model output (tolerates fences / leading prose)."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None
