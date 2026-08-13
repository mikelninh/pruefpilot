from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import settings


class Provider(Protocol):
    name: str

    def configured(self) -> bool: ...
    def extract(self, prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], float, float | None]: ...


@dataclass
class OpenAIProvider:
    name: str = "openai"

    def configured(self) -> bool:
        return bool(settings.openai_api_key)

    def extract(self, prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], float, float | None]:
        if not self.configured():
            raise RuntimeError("OPENAI_API_KEY is not configured")
        started = time.perf_counter()
        payload = {
            "model": settings.openai_model,
            "input": prompt,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "document_extraction",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        text = body.get("output_text")
        if not text:
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text = content.get("text")
                        break
        return json.loads(text or "{}"), (time.perf_counter() - started) * 1000, None


@dataclass
class MistralProvider:
    name: str = "mistral"

    def configured(self) -> bool:
        return bool(settings.mistral_api_key)

    def extract(self, prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], float, float | None]:
        if not self.configured():
            raise RuntimeError("MISTRAL_API_KEY is not configured")
        started = time.perf_counter()
        payload = {
            "model": settings.mistral_model,
            "messages": [
                {"role": "system", "content": "Return only valid JSON matching the requested schema."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        text = body["choices"][0]["message"]["content"]
        return json.loads(text), (time.perf_counter() - started) * 1000, None


@dataclass
class LocalHTTPProvider:
    name: str = "local"

    def configured(self) -> bool:
        return bool(settings.local_model_url)

    def extract(self, prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], float, float | None]:
        if not self.configured():
            raise RuntimeError("LOCAL_MODEL_URL is not configured")
        started = time.perf_counter()
        with httpx.Client(timeout=120) as client:
            response = client.post(
                str(settings.local_model_url),
                json={"prompt": prompt, "schema": schema, "temperature": 0},
            )
            response.raise_for_status()
            body = response.json()
        return body, (time.perf_counter() - started) * 1000, None


PROVIDERS: dict[str, Provider] = {
    "openai": OpenAIProvider(),
    "mistral": MistralProvider(),
    "local": LocalHTTPProvider(),
}


@dataclass(frozen=True)
class ProviderConfig:
    """Small compatibility config used by product tests and local provider selection."""

    provider: str = "openai"


class ProviderRegistry:
    """Resolve a configured provider explicitly; never silently fall back to another model."""

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def get(self) -> Provider:
        provider = PROVIDERS.get(self.config.provider)
        if provider is None:
            raise ValueError(f"Unknown provider: {self.config.provider}")
        if not provider.configured():
            raise ValueError(f"Provider '{self.config.provider}' is not configured")
        return provider
