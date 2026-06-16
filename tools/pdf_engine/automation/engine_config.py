"""Configuration adapter for the vendored PDF->LaTeX engine.

The engine modules (``ai_client``, ``latex_engine``, ``flashcard``) were lifted
from the upstream *PDF-OCR-MD-LaTeX-PDF-Lecture-Automation* project, where they
read a ``config.toml`` via an ``AppConfig`` dataclass. Here we drop the TOML/sync
machinery entirely and synthesize an equivalent ``EngineConfig`` from the
project-wide :data:`config.settings`, so the engine has no config file, no
watcher, and no rclone sync — it is a pure in-process library.

The API key is read from the environment at construction time and never stored
in :data:`config.settings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from config import settings

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(frozen=True)
class ModelConfig:
    transcriber: str
    exam: str
    flashcard: str
    validator: str


@dataclass(frozen=True)
class Pricing:
    """USD per 1M tokens."""

    prompt: float
    completion: float


def _load_prompts() -> dict[str, str]:
    keys = [
        "notes_system",
        "exam_system",
        "flashcard_system",
        "validator_notes",
        "validator_exam",
    ]
    out: dict[str, str] = {}
    for key in keys:
        path = _PROMPT_DIR / f"{key}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Engine prompt missing: {path}")
        out[key] = path.read_text(encoding="utf-8")
    return out


@dataclass
class EngineConfig:
    """Mirror of the upstream ``AppConfig`` surface the engine modules touch."""

    api_url: str
    api_key: str
    referer: str
    title: str
    request_timeout: int
    validate_timeout: int
    max_retries: int
    retry_min_wait: int
    retry_max_wait: int

    models: ModelConfig
    gen: dict
    pdf: dict
    latex: dict
    pricing: dict

    output_folder: Path
    exam_folder: Path
    flashcard_folder: Path
    temp_folder: Path

    prompts: dict = field(default_factory=dict)

    def price_for(self, model: str) -> Pricing | None:
        return self.pricing.get(model)

    def ensure_dirs(self) -> None:
        for d in (
            self.output_folder,
            self.exam_folder,
            self.flashcard_folder,
            self.temp_folder,
        ):
            d.mkdir(parents=True, exist_ok=True)


def build_engine_config() -> EngineConfig:
    """Construct an :class:`EngineConfig` from the project settings + env."""
    api_key = os.environ.get(settings.openrouter_api_key_env, "") or ""

    pricing = {
        slug: Pricing(prompt=float(p), completion=float(c))
        for slug, (p, c) in settings.model_pricing.items()
    }

    cfg = EngineConfig(
        api_url=_OPENROUTER_CHAT_URL,
        api_key=api_key,
        referer=settings.pdf_referer,
        title=settings.pdf_title,
        request_timeout=settings.pdf_request_timeout,
        validate_timeout=settings.pdf_validate_timeout,
        max_retries=settings.pdf_max_retries,
        retry_min_wait=settings.pdf_retry_min_wait,
        retry_max_wait=settings.pdf_retry_max_wait,
        models=ModelConfig(
            transcriber=settings.pdf_transcriber_model,
            exam=settings.pdf_exam_model,
            flashcard=settings.pdf_flashcard_model,
            validator=settings.pdf_validator_model,
        ),
        gen={
            "transcribe_max_tokens": settings.pdf_transcribe_max_tokens,
            "transcribe_temperature": settings.pdf_transcribe_temperature,
            "exam_max_tokens": settings.pdf_exam_max_tokens,
            "exam_temperature": settings.pdf_exam_temperature,
            "flashcard_max_tokens": settings.pdf_flashcard_max_tokens,
            "flashcard_temperature": settings.pdf_flashcard_temperature,
            "validate_temperature": settings.pdf_validate_temperature,
            "validate_before_compile": settings.pdf_validate_before_compile,
            "exam_notes_max_chars": settings.pdf_exam_notes_max_chars,
        },
        pdf={
            "dpi": settings.pdf_dpi,
            "fmt": settings.pdf_image_format,
            "prefer_text": settings.pdf_prefer_text,
            "min_chars_per_page": settings.pdf_min_chars_per_page,
        },
        latex={
            "engines": list(settings.pdf_latex_engines),
            "compile_timeout": settings.pdf_compile_timeout_seconds,
            "passes": settings.pdf_compile_passes,
            "self_correction_attempts": settings.pdf_self_correction_attempts,
        },
        pricing=pricing,
        output_folder=settings.pdf_output_dir,
        exam_folder=settings.pdf_exam_dir,
        flashcard_folder=settings.pdf_flashcard_dir,
        temp_folder=settings.pdf_temp_dir,
        prompts=_load_prompts(),
    )
    return cfg


__all__ = ["EngineConfig", "ModelConfig", "Pricing", "build_engine_config"]
