"""Async OpenRouter client for the PDF->LaTeX engine.

Vendored from the upstream ``services/ai_client.py`` with two adaptations for
Jarvis-Academic:
- logging goes through the ``jarvis.pdf_engine`` namespace (so lines reach the
  live log stream), not the upstream ``rich`` logger;
- token/cost usage is recorded into our :class:`~tools.pdf_engine.automation.usage.UsageTracker`
  under the ``"pdf"`` category, instead of the upstream ``AppState``.

httpx + tenacity give non-blocking requests with exponential backoff on
429/5xx/timeout. No call ever crashes the pipeline; validation/correction fall
back to the raw input on failure.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from io import BytesIO

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .engine_config import EngineConfig
from .usage import UsageTracker

log = logging.getLogger("jarvis.pdf_engine.ai")

_CATEGORY = "pdf"


class RetryableAPIError(Exception):
    """429/5xx-style errors worth retrying."""


class FatalAPIError(Exception):
    """401/402-style errors where retrying is pointless."""


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    finish_reason: str
    model: str


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


class AIClient:
    def __init__(self, cfg: EngineConfig, usage: UsageTracker) -> None:
        self.cfg = cfg
        self.usage = usage
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AIClient":
        if not self.cfg.api_key:
            raise FatalAPIError(
                "OPENROUTER_API_KEY is not set; the PDF engine cannot call OpenRouter."
            )
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.cfg.referer,
                "X-Title": self.cfg.title,
            }
        )
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client:
            await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Low-level chat call (retrying)
    # ------------------------------------------------------------------ #
    def _estimate_cost(
        self, model: str, native_cost, prompt_t: int, completion_t: int
    ) -> float:
        if native_cost is not None:
            try:
                return float(native_cost)
            except (TypeError, ValueError):
                pass
        price = self.cfg.price_for(model)
        if not price:
            return 0.0
        return (prompt_t / 1_000_000) * price.prompt + (
            completion_t / 1_000_000
        ) * price.completion

    async def _chat(
        self,
        *,
        model: str,
        messages: list,
        max_tokens: int | None,
        temperature: float,
        timeout: int,
        label: str,
    ) -> ChatResult:
        assert self._client is not None, "AIClient must be used inside its context"

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.cfg.max_retries),
            wait=wait_exponential(
                multiplier=1,
                min=self.cfg.retry_min_wait,
                max=self.cfg.retry_max_wait,
            ),
            retry=retry_if_exception_type(
                (RetryableAPIError, httpx.TimeoutException, httpx.TransportError)
            ),
            before_sleep=before_sleep_log(log, logging.WARNING),
        )
        async def _do() -> ChatResult:
            payload = {"model": model, "messages": messages, "temperature": temperature}
            if max_tokens:
                payload["max_tokens"] = max_tokens

            log.info("[%s] request -> %s", label, model)
            resp = await self._client.post(
                self.cfg.api_url, json=payload, timeout=timeout
            )

            if resp.status_code == 200:
                return self._parse_ok(resp.json(), model, label)
            if resp.status_code in (401, 402):
                raise FatalAPIError(
                    f"[{label}] fatal API error {resp.status_code}: {resp.text[:200]}"
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RetryableAPIError(
                    f"[{label}] transient API error {resp.status_code}"
                )
            raise FatalAPIError(
                f"[{label}] API error {resp.status_code}: {resp.text[:200]}"
            )

        return await _do()

    def _parse_ok(self, data: dict, model: str, label: str) -> ChatResult:
        usage = data.get("usage", {}) or {}
        prompt_t = int(usage.get("prompt_tokens", 0) or 0)
        completion_t = int(usage.get("completion_tokens", 0) or 0)
        total_t = int(usage.get("total_tokens", prompt_t + completion_t) or 0)
        cost = self._estimate_cost(model, usage.get("cost"), prompt_t, completion_t)

        choices = data.get("choices") or []
        if not choices:
            raise FatalAPIError(f"[{label}] response has no 'choices'")

        choice = choices[0]
        text = choice.get("message", {}).get("content", "") or ""
        finish = choice.get("finish_reason", "?")

        used_model = data.get("model", model)
        self.usage.record(
            _CATEGORY, used_model, prompt_t, completion_t, cost, label=label
        )
        log.info(
            "[%s] done · %s · in=%d out=%d ≈$%.4f",
            label,
            finish,
            prompt_t,
            completion_t,
            cost,
        )
        if finish == "length":
            log.warning("[%s] hit token limit; output may be truncated", label)

        return ChatResult(
            text=text,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
            cost_usd=cost,
            finish_reason=finish,
            model=used_model,
        )

    # ------------------------------------------------------------------ #
    # High-level operations
    # ------------------------------------------------------------------ #
    @staticmethod
    def _encode_image(image) -> str:
        buf = BytesIO()
        image.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def transcribe_images(self, images: list, filename: str) -> str:
        """Produce a single LaTeX document from page images (scanned-PDF path)."""
        total = len(images)
        encoded = await asyncio.gather(
            *(asyncio.to_thread(self._encode_image, img) for img in images)
        )
        content = [
            {
                "type": "text",
                "text": (
                    f"These images are the {total} page(s) of the PDF '{filename}'. "
                    f"Analyze all pages and produce a single LaTeX document."
                ),
            }
        ]
        for data in encoded:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{data}"},
                }
            )

        result = await self._chat(
            model=self.cfg.models.transcriber,
            messages=[
                {"role": "system", "content": self.cfg.prompts["notes_system"]},
                {"role": "user", "content": content},
            ],
            max_tokens=self.cfg.gen["transcribe_max_tokens"],
            temperature=self.cfg.gen["transcribe_temperature"],
            timeout=self.cfg.request_timeout,
            label="transcription",
        )
        return result.text

    async def describe_image_markdown(self, image, filename: str) -> str:
        """Transcribe a single image into clean Markdown (chat-attachment path)."""
        data = await asyncio.to_thread(self._encode_image, image)
        content = [
            {
                "type": "text",
                "text": (
                    f"Transcribe the image '{filename}' into clean GitHub-flavored "
                    "Markdown: capture all text, tables, formulae (as LaTeX in $...$), "
                    "and briefly describe any diagrams. Output Markdown only."
                ),
            },
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
        ]
        result = await self._chat(
            model=self.cfg.models.transcriber,
            messages=[{"role": "user", "content": content}],
            max_tokens=self.cfg.gen["transcribe_max_tokens"],
            temperature=self.cfg.gen["transcribe_temperature"],
            timeout=self.cfg.request_timeout,
            label="image-transcription",
        )
        return result.text

    async def transcribe_text(self, markdown: str, filename: str) -> str:
        """Produce a single LaTeX document from the PDF's extracted markdown.

        Far cheaper in input tokens than the image path; preferred for digital
        PDFs that carry a real text layer.
        """
        user_msg = (
            f"Below is the extracted markdown text of the PDF '{filename}'. "
            f"Analyze all of it and produce a single LaTeX document.\n\n"
            f"--- MARKDOWN ---\n{markdown}\n--- END ---"
        )
        result = await self._chat(
            model=self.cfg.models.transcriber,
            messages=[
                {"role": "system", "content": self.cfg.prompts["notes_system"]},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=self.cfg.gen["transcribe_max_tokens"],
            temperature=self.cfg.gen["transcribe_temperature"],
            timeout=self.cfg.request_timeout,
            label="transcription",
        )
        return result.text

    async def generate_exam(self, notes: str, filename: str) -> str:
        user_msg = (
            f"Below is the LaTeX source of the lecture notes '{filename}'.\n"
            f"Create an exam based on these notes.\n\n"
            f"Difficulty distribution:\n"
            f"- 2 Easy (7 pts x 2 = 14)\n"
            f"- 3 Medium (10 pts x 3 = 30)\n"
            f"- 5 Hard (14 pts x 5 = 70)\n"
            f"- Total: 100 points\n\n"
            f"Order easy to hard. Include an answer key.\n\n"
            f"--- LECTURE NOTES ---\n{notes}\n--- END ---"
        )
        result = await self._chat(
            model=self.cfg.models.exam,
            messages=[
                {"role": "system", "content": self.cfg.prompts["exam_system"]},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=self.cfg.gen["exam_max_tokens"],
            temperature=self.cfg.gen["exam_temperature"],
            timeout=self.cfg.request_timeout,
            label="exam",
        )
        return result.text

    async def generate_flashcards(self, notes: str, filename: str) -> str:
        """Return a raw JSON flashcard array (text) from the lecture notes."""
        user_msg = (
            f"Below is the LaTeX source of the lecture notes '{filename}'. "
            f"Produce Anki flashcards as specified.\n\n"
            f"--- LECTURE NOTES (LaTeX) ---\n{notes}\n--- END ---"
        )
        result = await self._chat(
            model=self.cfg.models.flashcard,
            messages=[
                {"role": "system", "content": self.cfg.prompts["flashcard_system"]},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=self.cfg.gen["flashcard_max_tokens"],
            temperature=self.cfg.gen["flashcard_temperature"],
            timeout=self.cfg.request_timeout,
            label="flashcard",
        )
        return result.text

    async def validate_latex(self, raw_code: str, kind: str) -> str:
        """Second-AI LaTeX validation; on any error returns the raw code."""
        if not raw_code.strip():
            return raw_code
        prompt_key = "validator_exam" if kind == "exam" else "validator_notes"
        try:
            result = await self._chat(
                model=self.cfg.models.validator,
                messages=[
                    {"role": "system", "content": self.cfg.prompts[prompt_key]},
                    {
                        "role": "user",
                        "content": f"Correct this LaTeX code if needed:\n\n{raw_code}",
                    },
                ],
                max_tokens=None,
                temperature=self.cfg.gen["validate_temperature"],
                timeout=self.cfg.validate_timeout,
                label="validation",
            )
            cleaned = _strip_code_fence(result.text)
            if cleaned:
                if cleaned != raw_code:
                    log.info("validation applied a correction")
                return cleaned
            log.info("validation returned empty; using raw code")
            return raw_code
        except Exception as exc:  # noqa: BLE001 - validation must never block
            log.info("validation failed (%s); using raw code", type(exc).__name__)
            return raw_code

    async def correct_latex(self, code: str, error_log: str, kind: str) -> str:
        """LLM self-correction for a document that failed to compile.

        On error returns the current code unchanged (to break the retry loop).
        """
        prompt_key = "validator_exam" if kind == "exam" else "validator_notes"
        system = (
            self.cfg.prompts[prompt_key]
            + "\n\nThe document below FAILED to compile. Fix the specific errors in "
            "the compiler log and return ONLY the corrected, fully compilable LaTeX."
        )
        user = (
            f"=== COMPILER ERROR LOG (truncated) ===\n{error_log[:4000]}\n\n"
            f"=== LATEX SOURCE ===\n{code}"
        )
        try:
            result = await self._chat(
                model=self.cfg.models.validator,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=None,
                temperature=self.cfg.gen["validate_temperature"],
                timeout=self.cfg.validate_timeout,
                label="self-correction",
            )
            fixed = _strip_code_fence(result.text)
            return fixed or code
        except Exception as exc:  # noqa: BLE001
            log.info(
                "self-correction failed (%s); keeping current code",
                type(exc).__name__,
            )
            return code


__all__ = ["AIClient", "ChatResult", "FatalAPIError", "RetryableAPIError"]
