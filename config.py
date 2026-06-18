"""Central configuration for Athena-Academic.

A single immutable :class:`Settings` instance (``settings``) holds every tunable
path and parameter so that no manager hardcodes filesystem locations or magic
numbers. Managers default their constructor arguments from ``settings`` but
accept explicit overrides, which keeps them easy to point at temporary
directories in tests.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_BASE_DIR = Path(__file__).resolve().parent


def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back on missing/invalid."""
    try:
        value = int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class Settings(BaseModel):
    """Project-wide settings with sensible local defaults."""

    model_config = ConfigDict(frozen=True)

    # --- Filesystem layout -------------------------------------------------
    base_dir: Path = Field(default=_BASE_DIR)
    data_dir: Path = Field(default=_BASE_DIR / "data")

    # --- SQLite ------------------------------------------------------------
    sqlite_path: Path = Field(default=_BASE_DIR / "data" / "athena.db")
    db_busy_timeout_ms: int = Field(default=5000, gt=0)
    db_max_retries: int = Field(default=5, ge=0)
    db_retry_base_delay: float = Field(default=0.1, gt=0)

    # --- ChromaDB ----------------------------------------------------------
    chroma_persist_dir: Path = Field(default=_BASE_DIR / "data" / "chroma")
    chroma_collection: str = Field(default="academic_documents")
    embedding_model: str = Field(default="all-MiniLM-L6-v2")

    # --- Document chunking -------------------------------------------------
    chunk_size: int = Field(default=512, gt=0)
    chunk_overlap: int = Field(default=64, ge=0)

    # --- LLM provider (OpenRouter, OpenAI-compatible) ----------------------
    # All LLM access is routed through OpenRouter via langchain-openai's
    # ChatOpenAI. The API key is read from the environment at call time and is
    # never stored in settings or source.
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_api_key_env: str = Field(default="OPENROUTER_API_KEY")

    # Default model per graph node. Slugs are OpenRouter model identifiers.
    router_model: str = Field(default="google/gemini-3.5-flash")
    chat_model: str = Field(default="google/gemini-3.1-pro-preview")
    router_max_tokens: int = Field(default=1024, gt=0)
    chat_max_tokens: int = Field(default=2048, gt=0)

    # Registry of selectable models (friendly name -> OpenRouter slug).
    available_models: dict[str, str] = Field(
        default_factory=lambda: {
            "haiku": "anthropic/claude-haiku-4.5",
            "opus": "anthropic/claude-opus-4.8",
            "gemini-flash": "google/gemini-3.5-flash",
            "gemini-pro": "google/gemini-3.1-pro-preview",
        }
    )

    # --- In-process PDF->LaTeX engine (vendored from the automation repo) ---
    # The engine runs entirely in-process via tools/pdf_engine/automation/.
    # All artifacts (notes .tex/.pdf, exam .pdf, flashcard .csv/.apkg) land under
    # these directories, persisted by the data volume in docker-compose.
    pdf_output_dir: Path = Field(default=_BASE_DIR / "data" / "pdf" / "output")
    pdf_exam_dir: Path = Field(default=_BASE_DIR / "data" / "pdf" / "exams")
    pdf_flashcard_dir: Path = Field(default=_BASE_DIR / "data" / "pdf" / "flashcards")
    pdf_temp_dir: Path = Field(default=_BASE_DIR / "data" / "pdf" / "temp")

    # OpenRouter model slugs per pipeline stage. Transcriber must be vision-capable
    # for the scanned-PDF (image) fallback.
    pdf_transcriber_model: str = Field(default="google/gemini-3.1-pro-preview")
    pdf_exam_model: str = Field(default="anthropic/claude-opus-4.8")
    pdf_flashcard_model: str = Field(default="anthropic/claude-haiku-4.5")
    pdf_validator_model: str = Field(default="google/gemini-3.1-pro-preview")

    # LaTeX compilation. Engines tried in order; first available wins.
    pdf_latex_engines: list[str] = Field(
        default_factory=lambda: ["lualatex", "xelatex", "pdflatex"]
    )
    pdf_compile_timeout_seconds: int = Field(default=180, gt=0)
    pdf_compile_passes: int = Field(default=2, gt=0)
    pdf_self_correction_attempts: int = Field(default=3, ge=1)

    # Generation knobs (token caps / temperatures), mirrored from the engine repo.
    pdf_transcribe_max_tokens: int = Field(default=64000, gt=0)
    pdf_transcribe_temperature: float = Field(default=0.1, ge=0)
    pdf_exam_max_tokens: int = Field(default=32000, gt=0)
    pdf_exam_temperature: float = Field(default=0.3, ge=0)
    pdf_flashcard_max_tokens: int = Field(default=16000, gt=0)
    pdf_flashcard_temperature: float = Field(default=0.2, ge=0)
    pdf_validate_temperature: float = Field(default=0.1, ge=0)
    pdf_validate_before_compile: bool = Field(default=False)
    pdf_exam_notes_max_chars: int = Field(default=80000, gt=0)

    # PDF text-layer extraction (digital vs scanned routing).
    pdf_dpi: int = Field(default=200, gt=0)
    pdf_image_format: str = Field(default="png")
    pdf_prefer_text: bool = Field(default=True)
    pdf_min_chars_per_page: int = Field(default=100, ge=0)

    # HTTP / retry for the engine's OpenRouter client.
    pdf_request_timeout: int = Field(default=600, gt=0)
    pdf_validate_timeout: int = Field(default=120, gt=0)
    pdf_max_retries: int = Field(default=4, ge=1)
    pdf_retry_min_wait: int = Field(default=4, ge=0)
    pdf_retry_max_wait: int = Field(default=60, ge=1)
    pdf_referer: str = Field(default="https://localhost")
    pdf_title: str = Field(default="Athena-Academic")

    # Whether to also generate exam + Anki flashcards from the notes (full pipeline).
    pdf_generate_exam: bool = Field(default=True)
    pdf_generate_flashcards: bool = Field(default=True)

    # --- API cost tracking -------------------------------------------------
    # OpenRouter pricing in USD per 1M tokens: slug -> (prompt, completion).
    # Used to estimate cost when the API response omits a native cost figure,
    # and to price agent-side LLM calls captured via the usage callback.
    model_pricing: dict[str, tuple[float, float]] = Field(
        default_factory=lambda: {
            "anthropic/claude-opus-4.8": (5.0, 25.0),
            "anthropic/claude-haiku-4.5": (1.0, 5.0),
            "google/gemini-3.5-flash": (0.30, 2.50),
            "google/gemini-3.1-pro-preview": (1.25, 5.0),
        }
    )
    usage_csv_path: Path = Field(default=_BASE_DIR / "data" / "usage.csv")
    # Fallback price (USD per 1M tokens: prompt, completion) used when a returned
    # model slug has no entry in model_pricing — so cost is never silently zero.
    default_model_pricing: tuple[float, float] = Field(default=(1.0, 3.0))

    # --- API / web layer ---------------------------------------------------
    # CORS origins allowed to call the API. Read from the CORS_ORIGINS env var
    # (comma-separated) so docker-compose can configure it; defaults to the
    # local frontend dev origin.
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            o.strip()
            for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ]
    )
    uploads_dir: Path = Field(default=_BASE_DIR / "data" / "uploads")

    # High-capacity model used for note analysis + subtask generation.
    notes_model: str = Field(default="anthropic/claude-opus-4.8")
    notes_model_max_tokens: int = Field(default=4096, gt=0)

    # --- Runalyze integration ---------------------------------------------
    # Personal-API token is read from the environment (or .env fallback) at
    # call time; never stored in settings. Activities are pulled and stored as
    # completed workouts both on demand and by a background loop.
    runalyze_token_env: str = Field(default="RUNALYZE_TOKEN")
    runalyze_sync_interval_min: int = Field(
        default_factory=lambda: _env_int("RUNALYZE_SYNC_INTERVAL_MIN", 30),
        gt=0,
    )
    # How many days back the auto-sync looks (paging stops past this cutoff).
    runalyze_sync_lookback_days: int = Field(default=90, gt=0)
    # Safety cap on pages fetched per sync run.
    runalyze_sync_max_pages: int = Field(default=20, gt=0)

    # --- Task extraction defaults -----------------------------------------
    # Applied by the task tool / extractor so the user never has to spell out
    # every detail; the LLM fills omissions with these and overrides them only
    # when the user states a value (see TASK_EXTRACTION_SYSTEM_PROMPT).
    default_discipline: str = Field(default="General")
    default_estimated_hours: float = Field(default=1.0, gt=0)
    default_deadline_hour: int = Field(default=23, ge=0, le=23)
    default_deadline_minute: int = Field(default=59, ge=0, le=59)


settings = Settings()

__all__ = ["Settings", "settings"]
