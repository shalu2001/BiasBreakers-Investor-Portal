"""Typed, environment-backed settings for the standalone narrative prediction engine.

This is a self-contained descendant of the research repo's ``NarrativePipelineSettings``.
The pure-computation modules vendored into ``narrative_engine`` depend on this object's
attributes and its ``macro_variant()`` / ``micro_variant()`` / ``analysis_window()`` helpers,
so the interface is preserved verbatim. The research CSV/file-IO fields are dropped and
replaced with Cosmos DB / collection settings plus the date-window knobs the service needs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(f"{value}T00:00:00")
        except ValueError:
            return None


def _parse_int(value: Optional[str], default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: Optional[str], default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if not value:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_optional_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class NarrativePipelineSettings:
    """Runtime settings for the standalone narrative prediction engine."""

    # --- Cosmos DB (Mongo API) connection -------------------------------------------------
    mongo_connection_string: str
    cosmos_allow_invalid_certs: bool = False
    cosmos_tls_ca_file: Optional[str] = None

    # --- Databases / collections ----------------------------------------------------------
    # News + ticker reference live in FinancialNewsDB; prices/caps/index live in SPSL20_DB.
    database_name: str = "FinancialNewsDB"  # news database (kept name for vendored code)
    excluded_collections: Tuple[str, ...] = ("Ticker_Info",)
    ticker_info_database: str = "FinancialNewsDB"
    ticker_info_collection: str = "Ticker_Info"
    cse_collection: str = "CSE_Annoucements"  # special-cased: classified micro via companyId mapping
    market_database: str = "SPSL20_DB"
    price_collection: str = "tickerdata_2020-2026"
    marketcap_collection: str = "marketcap_2026"
    index_collection: str = "sp_sl20_index"

    # --- Date windows ---------------------------------------------------------------------
    lookback_days: int = 30  # news lookback ending at as_of_date
    covariance_window_trading_days: int = 30  # trailing trading days for prices + index
    analysis_start: Optional[datetime] = None
    analysis_end: Optional[datetime] = None

    # --- Output (used only by vendored code paths that write scatter/exports; unused here) -
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "outputs")

    # --- Topic modelling / clustering -----------------------------------------------------
    min_cluster_size: int = 4
    min_topic_count: int = 4
    umap_n_neighbors: int = 15
    umap_n_components: int = 5
    umap_metric: str = "cosine"
    hdbscan_min_samples: int = 1
    topic_top_n_words: int = 5
    random_state: int = 42

    # --- Expected-return (Qi) -------------------------------------------------------------
    # Base alpha/lambda are fallbacks; the pipeline always uses the per-pipeline
    # macro_*/micro_* values below (via macro_variant()/micro_variant()). Defaults are the
    # Optuna "Jul30-conf-log" best trial (#32, mean rank-IC 0.0356).
    alpha: float = 0.02
    lambda_: float = 0.5
    micro_alpha: float = 0.10285630801219799
    micro_lambda: float = 1.3541701726546824
    macro_alpha: float = 0.16747222060949643
    macro_lambda: float = 0.744442959371803

    # --- LLM topic labelling (OpenAI) -----------------------------------------------------
    use_llm_topic_labels: bool = True
    llm_topic_model: str = "gpt-4o-mini"
    llm_topic_prompt: Optional[str] = None
    llm_topic_system_prompt: Optional[str] = None
    llm_topic_delay_in_seconds: float = 1.0
    llm_topic_nr_docs: int = 4
    llm_topic_doc_length: int = 120
    llm_topic_exponential_backoff: bool = True

    # --- Macro diffusion ------------------------------------------------------------------
    macro_diffusion_enabled: bool = True
    macro_diffusion_default_k: float = 4.0
    macro_diffusion_default_c: float = 0.5
    macro_diffusion_min_points: int = 5

    # --- Black-Litterman ------------------------------------------------------------------
    bl_risk_free_rate: float = 0.05
    bl_risk_aversion_fallback: float = 2.5
    bl_tau: Optional[float] = 0.5712965167021189  # Jul30 best trial
    bl_covariance_universe_size: int = 20
    bl_use_view_confidence: bool = True
    bl_confidence_macro_size_reference: float = 40.0
    bl_confidence_micro_size_reference: float = 6.0
    bl_confidence_macro_min: float = 0.05
    bl_confidence_micro_min: float = 0.15
    bl_confidence_max: float = 0.9
    bl_confidence_fallback_fit_penalty: float = 0.8

    # --- View-return calibration (defaults are the Jul30 best trial; set to 0/1.0/0 for no-op) -
    view_neutral_band: float = 0.09284166734679616
    view_macro_weight: float = 0.7529281487215205
    view_target_return_std: float = 0.002429301617990945

    # --- LLM macro-to-ticker override mapping (OpenAI) ------------------------------------
    use_macro_overrides: bool = True
    macro_llm_model: str = "gpt-4o-mini"
    macro_llm_api_key: Optional[str] = None
    macro_llm_seed: int = 42
    macro_max_allocations: int = 20
    macro_candidate_limit: int = 0

    @classmethod
    def from_env(cls) -> "NarrativePipelineSettings":
        """Build settings from environment variables."""

        connection_string = os.getenv("COSMOS_MONGO_CONNECTION") or os.getenv("MONGO_CONNECTION_STRING")
        if not connection_string:
            raise ValueError(
                "Missing MongoDB connection string. Set COSMOS_MONGO_CONNECTION or MONGO_CONNECTION_STRING."
            )

        macro_api_key = os.getenv("NARRATIVE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")

        return cls(
            mongo_connection_string=connection_string,
            cosmos_allow_invalid_certs=_parse_bool(os.getenv("COSMOS_ALLOW_INVALID_CERTS"), False),
            cosmos_tls_ca_file=os.getenv("COSMOS_TLS_CA_FILE") or None,
            database_name=os.getenv("NARRATIVE_NEWS_DATABASE", os.getenv("COSMOS_DATABASE", "FinancialNewsDB")),
            excluded_collections=(os.getenv("NARRATIVE_EXCLUDED_COLLECTION", "Ticker_Info"),),
            ticker_info_database=os.getenv("NARRATIVE_TICKER_INFO_DATABASE", "FinancialNewsDB"),
            ticker_info_collection=os.getenv("NARRATIVE_TICKER_INFO_COLLECTION", "Ticker_Info"),
            cse_collection=os.getenv("NARRATIVE_CSE_COLLECTION", "CSE_Annoucements"),
            market_database=os.getenv("NARRATIVE_MARKET_DATABASE", "SPSL20_DB"),
            price_collection=os.getenv("NARRATIVE_PRICE_COLLECTION", "tickerdata_2020-2026"),
            marketcap_collection=os.getenv("NARRATIVE_MARKETCAP_COLLECTION", "marketcap_2026"),
            index_collection=os.getenv("NARRATIVE_INDEX_COLLECTION", "sp_sl20_index"),
            lookback_days=_parse_int(os.getenv("NARRATIVE_LOOKBACK_DAYS"), 30),
            covariance_window_trading_days=_parse_int(os.getenv("NARRATIVE_COVARIANCE_WINDOW_TRADING_DAYS"), 30),
            analysis_start=_parse_datetime(os.getenv("NARRATIVE_ANALYSIS_START")),
            analysis_end=_parse_datetime(os.getenv("NARRATIVE_ANALYSIS_END")),
            output_dir=Path(os.getenv("NARRATIVE_OUTPUT_DIR", str(PROJECT_ROOT / "outputs"))),
            min_cluster_size=_parse_int(os.getenv("NARRATIVE_MIN_CLUSTER_SIZE"), 4),
            min_topic_count=_parse_int(os.getenv("NARRATIVE_MIN_TOPIC_COUNT"), 4),
            umap_n_neighbors=_parse_int(os.getenv("NARRATIVE_UMAP_N_NEIGHBORS"), 15),
            umap_n_components=_parse_int(os.getenv("NARRATIVE_UMAP_N_COMPONENTS"), 5),
            umap_metric=os.getenv("NARRATIVE_UMAP_METRIC", "cosine"),
            hdbscan_min_samples=_parse_int(os.getenv("NARRATIVE_HDBSCAN_MIN_SAMPLES"), 1),
            topic_top_n_words=_parse_int(os.getenv("NARRATIVE_TOPIC_TOP_WORDS"), 5),
            random_state=_parse_int(os.getenv("NARRATIVE_RANDOM_STATE"), 42),
            alpha=_parse_float(os.getenv("NARRATIVE_ALPHA"), 0.02),
            lambda_=_parse_float(os.getenv("NARRATIVE_LAMBDA"), 0.5),
            micro_alpha=_parse_float(os.getenv("NARRATIVE_MICRO_ALPHA"), 0.10285630801219799),
            micro_lambda=_parse_float(os.getenv("NARRATIVE_MICRO_LAMBDA"), 1.3541701726546824),
            macro_alpha=_parse_float(os.getenv("NARRATIVE_MACRO_ALPHA"), 0.16747222060949643),
            macro_lambda=_parse_float(os.getenv("NARRATIVE_MACRO_LAMBDA"), 0.744442959371803),
            use_llm_topic_labels=_parse_bool(os.getenv("NARRATIVE_USE_LLM_TOPIC_LABELS"), True),
            llm_topic_model=os.getenv("NARRATIVE_LLM_TOPIC_MODEL", "gpt-4o-mini"),
            llm_topic_prompt=os.getenv("NARRATIVE_LLM_TOPIC_PROMPT") or None,
            llm_topic_system_prompt=os.getenv("NARRATIVE_LLM_TOPIC_SYSTEM_PROMPT") or None,
            llm_topic_delay_in_seconds=_parse_float(os.getenv("NARRATIVE_LLM_TOPIC_DELAY_SECONDS"), 1.0),
            llm_topic_nr_docs=_parse_int(os.getenv("NARRATIVE_LLM_TOPIC_NR_DOCS"), 4),
            llm_topic_doc_length=_parse_int(os.getenv("NARRATIVE_LLM_TOPIC_DOC_LENGTH"), 120),
            llm_topic_exponential_backoff=_parse_bool(os.getenv("NARRATIVE_LLM_TOPIC_EXPONENTIAL_BACKOFF"), True),
            macro_diffusion_enabled=_parse_bool(os.getenv("NARRATIVE_MACRO_DIFFUSION_ENABLED"), True),
            macro_diffusion_default_k=_parse_float(os.getenv("NARRATIVE_MACRO_DIFFUSION_DEFAULT_K"), 4.0),
            macro_diffusion_default_c=_parse_float(os.getenv("NARRATIVE_MACRO_DIFFUSION_DEFAULT_C"), 0.5),
            macro_diffusion_min_points=_parse_int(os.getenv("NARRATIVE_MACRO_DIFFUSION_MIN_POINTS"), 5),
            bl_risk_free_rate=_parse_float(os.getenv("NARRATIVE_BL_RISK_FREE_RATE"), 0.05),
            bl_risk_aversion_fallback=_parse_float(os.getenv("NARRATIVE_BL_RISK_AVERSION_FALLBACK"), 2.5),
            bl_tau=(
                _parse_optional_float(os.getenv("NARRATIVE_BL_TAU"))
                if os.getenv("NARRATIVE_BL_TAU") not in (None, "")
                else 0.5712965167021189
            ),
            bl_covariance_universe_size=_parse_int(os.getenv("NARRATIVE_BL_COVARIANCE_UNIVERSE_SIZE"), 20),
            bl_use_view_confidence=_parse_bool(os.getenv("NARRATIVE_BL_USE_VIEW_CONFIDENCE"), True),
            bl_confidence_macro_size_reference=_parse_float(
                os.getenv("NARRATIVE_BL_CONFIDENCE_MACRO_SIZE_REFERENCE"), 40.0
            ),
            bl_confidence_micro_size_reference=_parse_float(
                os.getenv("NARRATIVE_BL_CONFIDENCE_MICRO_SIZE_REFERENCE"), 6.0
            ),
            bl_confidence_macro_min=_parse_float(os.getenv("NARRATIVE_BL_CONFIDENCE_MACRO_MIN"), 0.05),
            bl_confidence_micro_min=_parse_float(os.getenv("NARRATIVE_BL_CONFIDENCE_MICRO_MIN"), 0.15),
            bl_confidence_max=_parse_float(os.getenv("NARRATIVE_BL_CONFIDENCE_MAX"), 0.9),
            bl_confidence_fallback_fit_penalty=_parse_float(
                os.getenv("NARRATIVE_BL_CONFIDENCE_FALLBACK_FIT_PENALTY"), 0.8
            ),
            view_neutral_band=_parse_float(os.getenv("NARRATIVE_VIEW_NEUTRAL_BAND"), 0.09284166734679616),
            view_macro_weight=_parse_float(os.getenv("NARRATIVE_VIEW_MACRO_WEIGHT"), 0.7529281487215205),
            view_target_return_std=_parse_float(os.getenv("NARRATIVE_VIEW_TARGET_RETURN_STD"), 0.002429301617990945),
            use_macro_overrides=_parse_bool(os.getenv("NARRATIVE_USE_MACRO_OVERRIDES"), True),
            macro_llm_model=os.getenv("NARRATIVE_MACRO_LLM_MODEL", os.getenv("NARRATIVE_LLM_MODEL", "gpt-4o-mini")),
            macro_llm_api_key=macro_api_key,
            macro_llm_seed=_parse_int(os.getenv("NARRATIVE_MACRO_LLM_SEED"), 42),
            macro_max_allocations=_parse_int(os.getenv("NARRATIVE_MACRO_MAX_ALLOCATIONS"), 20),
            macro_candidate_limit=_parse_int(os.getenv("NARRATIVE_MACRO_CANDIDATE_LIMIT"), 0),
        )

    def with_overrides(self, **overrides) -> "NarrativePipelineSettings":
        """Create a copy of the settings with explicit field overrides."""

        return replace(self, **overrides)

    def _variant_from_prefix(
        self,
        prefix: str,
        default_alpha: Optional[float] = None,
        default_lambda: Optional[float] = None,
    ) -> "NarrativePipelineSettings":
        """Build a per-pipeline (macro/micro) variant from environment overrides.

        ``default_alpha``/``default_lambda`` carry the pipeline-specific tuned values, used
        when the ``{prefix}ALPHA`` / ``{prefix}LAMBDA`` env vars are not set.
        """

        return self.with_overrides(
            min_cluster_size=_parse_int(os.getenv(f"{prefix}MIN_CLUSTER_SIZE"), self.min_cluster_size),
            min_topic_count=_parse_int(os.getenv(f"{prefix}MIN_TOPIC_COUNT"), self.min_topic_count),
            umap_n_neighbors=_parse_int(os.getenv(f"{prefix}UMAP_N_NEIGHBORS"), self.umap_n_neighbors),
            umap_n_components=_parse_int(os.getenv(f"{prefix}UMAP_N_COMPONENTS"), self.umap_n_components),
            umap_metric=os.getenv(f"{prefix}UMAP_METRIC", self.umap_metric),
            hdbscan_min_samples=_parse_int(os.getenv(f"{prefix}HDBSCAN_MIN_SAMPLES"), self.hdbscan_min_samples),
            topic_top_n_words=_parse_int(os.getenv(f"{prefix}TOPIC_TOP_WORDS"), self.topic_top_n_words),
            alpha=_parse_float(os.getenv(f"{prefix}ALPHA"), default_alpha if default_alpha is not None else self.alpha),
            lambda_=_parse_float(os.getenv(f"{prefix}LAMBDA"), default_lambda if default_lambda is not None else self.lambda_),
            random_state=_parse_int(os.getenv(f"{prefix}RANDOM_STATE"), self.random_state),
            use_llm_topic_labels=_parse_bool(
                os.getenv(f"{prefix}USE_LLM_TOPIC_LABELS"), self.use_llm_topic_labels
            ),
            llm_topic_model=os.getenv(f"{prefix}LLM_TOPIC_MODEL", self.llm_topic_model),
            llm_topic_prompt=os.getenv(f"{prefix}LLM_TOPIC_PROMPT") or self.llm_topic_prompt,
            llm_topic_system_prompt=os.getenv(f"{prefix}LLM_TOPIC_SYSTEM_PROMPT") or self.llm_topic_system_prompt,
            llm_topic_delay_in_seconds=_parse_float(
                os.getenv(f"{prefix}LLM_TOPIC_DELAY_SECONDS"), self.llm_topic_delay_in_seconds
            ),
            llm_topic_nr_docs=_parse_int(os.getenv(f"{prefix}LLM_TOPIC_NR_DOCS"), self.llm_topic_nr_docs),
            llm_topic_doc_length=_parse_int(os.getenv(f"{prefix}LLM_TOPIC_DOC_LENGTH"), self.llm_topic_doc_length),
            llm_topic_exponential_backoff=_parse_bool(
                os.getenv(f"{prefix}LLM_TOPIC_EXPONENTIAL_BACKOFF"), self.llm_topic_exponential_backoff
            ),
            macro_diffusion_enabled=_parse_bool(
                os.getenv(f"{prefix}DIFFUSION_ENABLED"), self.macro_diffusion_enabled
            ),
            macro_diffusion_default_k=_parse_float(
                os.getenv(f"{prefix}DIFFUSION_DEFAULT_K"), self.macro_diffusion_default_k
            ),
            macro_diffusion_default_c=_parse_float(
                os.getenv(f"{prefix}DIFFUSION_DEFAULT_C"), self.macro_diffusion_default_c
            ),
            macro_diffusion_min_points=_parse_int(
                os.getenv(f"{prefix}DIFFUSION_MIN_POINTS"), self.macro_diffusion_min_points
            ),
        )

    def macro_variant(self) -> "NarrativePipelineSettings":
        """Return the macro-specific settings variant."""

        return self._variant_from_prefix("NARRATIVE_MACRO_", self.macro_alpha, self.macro_lambda)

    def micro_variant(self) -> "NarrativePipelineSettings":
        """Return the micro-specific settings variant."""

        return self._variant_from_prefix("NARRATIVE_MICRO_", self.micro_alpha, self.micro_lambda)

    def analysis_window(
        self, fallback_start: Optional[datetime], fallback_end: Optional[datetime]
    ) -> Tuple[datetime, datetime]:
        """Return the effective analysis window for persistence calculations."""

        start = self.analysis_start or fallback_start or datetime.utcnow()
        end = self.analysis_end or fallback_end or start
        if end < start:
            start, end = end, start
        return start, end


def get_settings() -> NarrativePipelineSettings:
    """Get engine settings from environment."""

    return NarrativePipelineSettings.from_env()
