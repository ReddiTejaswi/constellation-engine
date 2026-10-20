"""Thin async LLM client targeting any OpenAI-compatible chat endpoint.

The model name is read from configuration — it is never hardcoded.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self) -> None:
        s = get_settings().model
        self._model = s.name
        self._base_url = s.base_url.rstrip("/")
        self._api_key = s.api_key
        self._temperature = s.temperature
        self._max_tokens = s.max_tokens
        self._timeout = s.request_timeout

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format_json: bool = False,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature if temperature is None else temperature,
            "max_tokens": self._max_tokens if max_tokens is None else max_tokens,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise LLMError(f"LLM request failed {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected LLM response shape: {data}") from e

    async def json(
        self,
        system: str,
        user: str,
        schema: Type[T],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> T:
        """Call the model and parse the response as `schema`.

        We first try the native JSON mode. If that fails or isn't honored,
        we fall back to extracting the first JSON object in the response.
        """
        schema_hint = _schema_hint(schema)
        sys_prompt = (
            f"{system}\n\n"
            "Respond with a single JSON object matching this schema. "
            "Do not include commentary. If a field is unknown, use null, "
            "an empty list, or an empty string — never fabricate values.\n\n"
            f"Schema:\n{schema_hint}"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ]
        text = ""
        for attempt in range(2):
            try:
                text = await self.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format_json=attempt == 0,
                )
                return schema.model_validate_json(_extract_json(text))
            except (ValidationError, json.JSONDecodeError) as e:
                logger.warning("Attempt %d: JSON parse/validation failed: %s", attempt, e)
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response did not conform to the schema. "
                            "Return ONLY a valid JSON object matching the schema. "
                            f"Validation error: {e}"
                        ),
                    }
                )
            except LLMError:
                raise
        raise LLMError("Failed to obtain schema-conformant JSON from the LLM.")


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # strip markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if text.startswith("{"):
        return text
    m = _JSON_OBJ_RE.search(text)
    if not m:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    return m.group(0)


def _schema_hint(model: Type[BaseModel]) -> str:
    try:
        return json.dumps(model.model_json_schema(), indent=2)[:4000]
    except Exception:  # pragma: no cover
        return model.__name__
