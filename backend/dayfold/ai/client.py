"""AI adapters. Every call asks for JSON and is validated by the caller with Pydantic.

Kinds:

* ``openai``: any OpenAI compatible ``/chat/completions`` endpoint (OpenAI, Ollama at
  ``http://localhost:11434/v1``, OpenRouter, LM Studio, vLLM...). Images via
  ``/images/generations`` when ``image_model`` is set.
* ``anthropic``: Anthropic Messages API.
* ``cli``: a local command that reads the prompt on stdin and prints the answer, e.g.
  ``claude -p --output-format text`` or ``codex exec -``. Useful with subscriptions.
"""

from __future__ import annotations

import base64
import json
import re
import shlex
import subprocess
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AIProvider


class AIError(RuntimeError):
    pass


@dataclass
class AIUsage:
    prompt_chars: int = 0
    completion_chars: int = 0
    calls: int = 0


usage = AIUsage()

SYSTEM_JSON = (
    "Você é um editor de jornal. Responda SOMENTE com um objeto JSON válido, sem texto "
    "antes ou depois e sem blocos de código."
)


def extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIError(f"JSON inválido na resposta da IA: {exc}") from exc
    raise AIError("a IA não retornou JSON")


class AIClient:
    def __init__(self, provider: AIProvider):
        self.p = provider

    @property
    def label(self) -> str:
        return f"{self.p.name} ({self.p.kind}{': ' + self.p.model if self.p.model else ''})"

    # -- text ---------------------------------------------------------------
    def complete(self, prompt: str, *, system: str = SYSTEM_JSON, max_tokens: int | None = None) -> str:
        max_tokens = max_tokens or self.p.max_tokens
        usage.calls += 1
        usage.prompt_chars += len(prompt) + len(system)
        if self.p.kind == "openai":
            out = self._openai(prompt, system, max_tokens)
        elif self.p.kind == "anthropic":
            out = self._anthropic(prompt, system, max_tokens)
        elif self.p.kind == "cli":
            out = self._cli(prompt, system)
        else:
            raise AIError(f"tipo de IA desconhecido: {self.p.kind}")
        usage.completion_chars += len(out)
        return out

    def complete_json[T: BaseModel](self, prompt: str, model: type[T], *, retries: int = 1,
                                    max_tokens: int | None = None) -> T:
        last: Exception | None = None
        current = prompt
        for _ in range(retries + 1):
            raw = self.complete(current, max_tokens=max_tokens)
            try:
                return model.model_validate(extract_json(raw))
            except (AIError, ValidationError) as exc:
                last = exc
                current = (
                    f"{prompt}\n\nSua resposta anterior era inválida ({str(exc)[:300]}). "
                    "Responda novamente apenas com o JSON no formato pedido."
                )
        raise AIError(f"resposta da IA não validou: {last}")

    def _openai(self, prompt: str, system: str, max_tokens: int) -> str:
        base = (self.p.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {self.p.api_key}"} if self.p.api_key else {}
        body = {
            "model": self.p.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.4,
        }
        try:
            r = httpx.post(f"{base}/chat/completions", json=body, headers=headers,
                           timeout=self.p.timeout_s)
        except httpx.HTTPError as exc:
            raise AIError(f"falha de conexão com {base}: {exc}") from exc
        if r.status_code >= 400:
            raise AIError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"] or ""

    def _anthropic(self, prompt: str, system: str, max_tokens: int) -> str:
        base = (self.p.base_url or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": self.p.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.p.model or "claude-haiku-5-5",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            r = httpx.post(f"{base}/v1/messages", json=body, headers=headers,
                           timeout=self.p.timeout_s)
        except httpx.HTTPError as exc:
            raise AIError(f"falha de conexão com {base}: {exc}") from exc
        if r.status_code >= 400:
            raise AIError(f"HTTP {r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")

    def _cli(self, prompt: str, system: str) -> str:
        if not self.p.command:
            raise AIError("comando da CLI não configurado")
        argv = shlex.split(self.p.command)
        try:
            proc = subprocess.run(argv, input=f"{system}\n\n{prompt}", capture_output=True,
                                  text=True, timeout=self.p.timeout_s)
        except FileNotFoundError as exc:
            raise AIError(f"comando não encontrado: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AIError(f"a CLI passou de {self.p.timeout_s}s") from exc
        if proc.returncode != 0:
            raise AIError(f"CLI saiu com código {proc.returncode}: {proc.stderr[-300:]}")
        return proc.stdout

    # -- images -------------------------------------------------------------
    @property
    def can_generate_images(self) -> bool:
        return self.p.kind == "openai" and bool(self.p.image_model)

    def generate_image(self, prompt: str, size: str = "1024x1024") -> bytes:
        if not self.can_generate_images:
            raise AIError("este provedor de IA não gera imagens")
        base = (self.p.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {self.p.api_key}"} if self.p.api_key else {}
        r = httpx.post(
            f"{base}/images/generations",
            json={"model": self.p.image_model, "prompt": prompt, "size": size, "n": 1},
            headers=headers, timeout=max(self.p.timeout_s, 180),
        )
        if r.status_code >= 400:
            raise AIError(f"HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()["data"][0]
        if data.get("b64_json"):
            return base64.b64decode(data["b64_json"])
        if data.get("url"):
            return httpx.get(data["url"], timeout=60).content
        raise AIError("resposta de imagem vazia")


def active_client(session: Session) -> AIClient | None:
    p = session.scalar(select(AIProvider).where(AIProvider.is_active.is_(True)).limit(1))
    return AIClient(p) if p else None


class _Ping(BaseModel):
    ok: bool
    message: str = ""


def test_provider(provider: AIProvider) -> tuple[bool, str]:
    try:
        r = AIClient(provider).complete_json(
            'Responda exatamente {"ok": true, "message": "pronto"}', _Ping, retries=0,
            max_tokens=60,
        )
        return r.ok, r.message or "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:500]
