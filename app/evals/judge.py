"""LLM-as-a-judge for deepeval, backed by any OpenAI-compatible chat endpoint.

Default target is DeepSeek (``JUDGE_BASE_URL=https://api.deepseek.com/v1``, ``JUDGE_MODEL=...``,
``JUDGE_API_KEY=...``); works with any provider that speaks the OpenAI chat-completions API.
"""

from __future__ import annotations

import re
from typing import Any

from deepeval.models.base_model import DeepEvalBaseLLM
from openai import AsyncOpenAI, OpenAI

from app.config import SETTINGS

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_RETRIES = 3


def _message_text(response: Any) -> str:
    message = response.choices[0].message
    return str(getattr(message, "content", None) or getattr(message, "reasoning_content", None) or "")


def _parse(text: str, schema: Any | None) -> Any:
    if schema is None:
        return text
    try:
        return schema.model_validate_json(text)
    except ValueError:
        match = _JSON_RE.search(text)
        if match is None:
            raise
        return schema.model_validate_json(match.group(0))


class OpenAICompatibleJudge(DeepEvalBaseLLM):
    """A deepeval judge calling an OpenAI-compatible ``/chat/completions`` endpoint.

    Clients can be injected for tests; otherwise they are built from settings. Reasoning models
    that leave ``content`` empty (DeepSeek) are handled via ``reasoning_content``, and replies that
    wrap JSON in prose are recovered; transient empties/parse failures are retried.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        client: Any | None = None,
        async_client: Any | None = None,
    ) -> None:
        self._base_url = base_url or SETTINGS.judge_base_url
        self._api_key = api_key or SETTINGS.judge_api_key or "missing-judge-key"
        self._temperature = SETTINGS.judge_temperature if temperature is None else temperature
        self._injected_client = client
        super().__init__(model or SETTINGS.judge_model)
        self._async_client = async_client or AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    def load_model(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        return OpenAI(api_key=self._api_key, base_url=self._base_url)

    def get_model_name(self) -> str:
        return str(self.name)

    def _completion_kwargs(self, prompt: str, *, json_mode: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def generate(self, prompt: str, schema: Any | None = None) -> Any:
        kwargs = self._completion_kwargs(prompt, json_mode=schema is not None)
        last_error: Exception | None = None
        for _ in range(_RETRIES):
            text = _message_text(self.model.chat.completions.create(**kwargs))
            try:
                return _parse(text, schema)
            except ValueError as exc:
                last_error = exc
        raise last_error or ValueError("judge returned no parseable content")

    async def a_generate(self, prompt: str, schema: Any | None = None) -> Any:
        kwargs = self._completion_kwargs(prompt, json_mode=schema is not None)
        last_error: Exception | None = None
        for _ in range(_RETRIES):
            response = await self._async_client.chat.completions.create(**kwargs)
            try:
                return _parse(_message_text(response), schema)
            except ValueError as exc:
                last_error = exc
        raise last_error or ValueError("judge returned no parseable content")
