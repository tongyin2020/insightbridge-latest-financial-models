from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMResponse:
    content: str
    model: str = "none"
    usage: dict[str, Any] = None  # type: ignore[assignment]


class LLMClient:
    """Thin wrapper around LangChain ChatOpenAI pointing to NVIDIA's OpenAI-compatible endpoint.

    Default disabled. When disabled, callers should fall back to deterministic logic.
    """

    def __init__(self, config: Any) -> None:
        self.enabled = bool(getattr(config, "use_llm", False))
        self.model = getattr(config, "llm_model", "nvidia/nemotron-3.5-lightning-30b-a3b")
        self.base_url = getattr(config, "llm_base_url", "https://integrate.api.nvidia.com/v1")
        self.api_key = getattr(config, "llm_api_key", None) or os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")
        self.temperature = float(getattr(config, "llm_temperature", 0.2))
        self.max_tokens = int(getattr(config, "llm_max_tokens", 1024))
        self._client: Optional[Any] = None

    def _lazy_client(self) -> Optional[Any]:
        if not self.enabled or not self.api_key:
            return None
        if self._client is None:
            try:
                from langchain_openai import ChatOpenAI
                self._client = ChatOpenAI(
                    model=self.model,
                    api_key=self.api_key,
                    base_url=self.base_url,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            except Exception:
                self._client = None
        return self._client

    def invoke(self, prompt: str, system: str = "") -> Optional[LLMResponse]:
        client = self._lazy_client()
        if client is None:
            return None
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = client.invoke(messages)
            return LLMResponse(
                content=str(resp.content),
                model=self.model,
                usage=getattr(resp, "usage_metadata", None) or {},
            )
        except Exception as exc:
            return LLMResponse(content=f"", model=self.model, usage={"error": str(exc)})
