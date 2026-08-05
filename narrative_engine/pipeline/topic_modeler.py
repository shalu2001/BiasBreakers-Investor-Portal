"""BERTopic wrapper for clustering using precomputed embeddings (vendored).

Behaviour matches the research modeler. One addition: `cluster_dataframe` accepts
`build_visualization=False` so the service can skip the extra 2-D UMAP scatter fit it
does not need. LLM topic/narrative labels are produced via the OpenAI representation
model exactly as in the research pipeline.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:  # pragma: no cover - optional runtime dependency
    from bertopic import BERTopic
    from bertopic.representation import OpenAI as BERTopicOpenAI
    from hdbscan import HDBSCAN
    from umap import UMAP
    from sklearn.feature_extraction.text import CountVectorizer
except ImportError as exc:  # pragma: no cover - explicit runtime guard
    BERTopic = None  # type: ignore[assignment]
    BERTopicOpenAI = None  # type: ignore[assignment]
    HDBSCAN = None  # type: ignore[assignment]
    UMAP = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

try:  # pragma: no cover - optional runtime dependency
    import openai
except ImportError:  # pragma: no cover - optional runtime dependency
    openai = None  # type: ignore[assignment]

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.models import TopicCluster

logger = logging.getLogger(__name__)


@dataclass
class BerTopicModeler:
    """Fit BERTopic over existing embeddings and emit topic clusters."""

    settings: NarrativePipelineSettings
    current_view_type: str = "macro"

    @staticmethod
    def _default_llm_prompt_macro() -> str:
        return (
            "You are a quantitative research assistant extracting investable macro narratives for an adaptive portfolio system.\n"
            "You will be given representative documents and keywords for a topic cluster.\n"
            "Write one short, clear, declarative sentence that summarizes the broader market, economic, or sector-level narrative represented by the cluster.\n\n"

            "CRITICAL INSTRUCTIONS:\n"
            "1. Prioritize macro-level narratives over company-specific descriptions. Transform individual company events into broader economic or industry themes only when the documents support that interpretation.\n"
            "2. Do not focus on specific companies, executives, products, branches, or isolated corporate actions. Extract the underlying market force, sector trend, or economic condition driving the events.\n"
            "3. Do not invent market impact, directional pressure, sentiment, or investment implications that are not explicitly supported by the documents.\n"
            "4. If the text naturally implies a direction (e.g., rising rates, slowing demand, improving exports, stronger credit growth, increasing inflation), include that direction in the narrative.\n"
            "5. If the cluster reflects a neutral or informational theme, state the broader factual trend without adding bullish or bearish interpretation.\n"
            "6. The output should represent a potential portfolio research view, focusing on macroeconomic conditions, sector trends, business cycles, risks, or opportunities rather than news summaries.\n\n"

            "[DOCUMENTS]\n\n"
            "Keywords: [KEYWORDS]\n\n"

            "Return only the final sentence in the format:\n"
            "topic: <macro-level declarative narrative>"
        )

    @staticmethod
    def _default_llm_prompt_micro() -> str:
        return (
            "You are a quantitative research assistant extracting company-specific narratives for portfolio signals.\n"
            "You will be given representative documents and keywords for one micro topic cluster tied to a single company.\n"
            "Write one short, clear, declarative sentence summarizing the key company-level development that may influence the company's fundamentals or outlook.\n\n"

            "CRITICAL INSTRUCTIONS:\n"
            "1. Keep the narrative company-specific and grounded in the provided documents.\n"
            "2. Focus on fundamental company drivers such as earnings, revenue, costs, margins, operations, strategy, competitive position, financial condition, or company-specific risks.\n"
            "3. Do not generalize into market-wide, industry-wide, or macroeconomic conclusions unless the documents explicitly state such effects.\n"
            "4. Do not infer stock price movements, investor sentiment, or valuation impacts unless directly supported by the documents.\n"
            "5. If direction is explicitly present (e.g., revenue growth, declining margins, increasing costs, rising regulatory risk), include the direction concisely.\n"
            "6. If the information is a neutral disclosure (e.g., appointments, announcements, filings, routine updates), summarize only the factual company event without adding interpretation.\n\n"

            "[DOCUMENTS]\n\n"
            "Keywords: [KEYWORDS]\n\n"

            "Return only the final sentence in the format:\n"
            "topic: <company-specific declarative narrative>"
        )

    def _default_llm_prompt(self, view_type: Optional[str] = None) -> str:
        target_view_type = (view_type or self.current_view_type or "macro").lower()
        if target_view_type == "micro":
            return self._default_llm_prompt_micro()
        return self._default_llm_prompt_macro()

    def _api_key(self) -> Optional[str]:
        return (
            self.settings.macro_llm_api_key
            or os.getenv("NARRATIVE_LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

    def _create_representation_model(self, view_type: Optional[str] = None):
        if not self.settings.use_llm_topic_labels:
            return None
        if BERTopicOpenAI is None or openai is None:
            logger.warning("LLM topic labels are enabled but openai/bertopic representation support is unavailable.")
            return None

        api_key = self._api_key()
        if not api_key:
            logger.warning(
                "LLM topic labels are enabled but no OpenAI API key was found in NARRATIVE_LLM_API_KEY or OPENAI_API_KEY."
            )
            return None

        client = openai.OpenAI(api_key=api_key)
        prompt = self.settings.llm_topic_prompt or self._default_llm_prompt(view_type)
        return BERTopicOpenAI(
            client,
            model=self.settings.llm_topic_model,
            prompt=prompt,
            system_prompt=self.settings.llm_topic_system_prompt,
            delay_in_seconds=self.settings.llm_topic_delay_in_seconds,
            exponential_backoff=self.settings.llm_topic_exponential_backoff,
            nr_docs=self.settings.llm_topic_nr_docs,
            doc_length=self.settings.llm_topic_doc_length,
            tokenizer="vectorizer",
        )

    def _create_model_with_adjusted_neighbors(
        self, n_neighbors: int, n_components: int, view_type: Optional[str] = None
    ) -> Any:
        """Create BERTopic with specific `n_neighbors` and `n_components` for UMAP."""

        if _IMPORT_ERROR is not None:
            raise ImportError(
                "BERTopic dependencies are not installed. Install bertopic, umap-learn, and hdbscan."
            ) from _IMPORT_ERROR

        umap_model = UMAP(
            n_neighbors=n_neighbors,
            n_components=n_components,
            metric=self.settings.umap_metric,
            random_state=self.settings.random_state,
        )
        hdbscan_model = HDBSCAN(
            min_cluster_size=self.settings.min_cluster_size,
            min_samples=self.settings.hdbscan_min_samples,
            prediction_data=True,
        )
        vectorizer = CountVectorizer(ngram_range=(1, 3), stop_words="english", min_df=2)
        representation_model = self._create_representation_model(view_type)
        return BERTopic(
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer,
            representation_model=representation_model,
            calculate_probabilities=True,
            verbose=False,
            top_n_words=self.settings.topic_top_n_words,
            min_topic_size=self.settings.min_topic_count,
        )

    def fit_transform(
        self, documents: Sequence[str], embeddings: Sequence[Sequence[float]], view_type: Optional[str] = None
    ) -> Tuple[np.ndarray, Optional[np.ndarray], Any]:
        """Cluster documents using their precomputed embeddings."""

        n_samples = len(embeddings)
        if n_samples < 3:
            topics = np.full(n_samples, -1, dtype=int)
            return topics, None, None

        desired_neighbors = min(self.settings.umap_n_neighbors, max(2, n_samples - 1))
        desired_components = min(self.settings.umap_n_components, max(1, n_samples - 1))
        model = self._create_model_with_adjusted_neighbors(desired_neighbors, desired_components, view_type=view_type)
        try:
            topics, probabilities = model.fit_transform(list(documents), embeddings=np.asarray(embeddings, dtype=float))
            return np.asarray(topics), probabilities, model
        except Exception:
            topics = np.full(n_samples, -1, dtype=int)
            return topics, None, None

    def cluster_dataframe(
        self,
        dataframe: pd.DataFrame,
        view_type: str,
        company: Optional[str] = None,
        build_visualization: bool = False,
    ) -> Tuple[List[TopicCluster], pd.DataFrame]:
        """Cluster a dataframe and return clusters (visualization frame optional)."""

        if dataframe.empty:
            return [], pd.DataFrame()

        self.current_view_type = view_type
        documents = [self._document_text(row) for _, row in dataframe.iterrows()]
        embeddings = dataframe["final_embedding"].tolist()
        topics, probabilities, model = self.fit_transform(documents, embeddings, view_type=view_type)
        if model is None:
            return [], pd.DataFrame()

        clusters: List[TopicCluster] = []
        for topic_id in sorted(set(int(topic) for topic in topics if int(topic) != -1)):
            topic_mask = topics == topic_id
            cluster_df = dataframe.loc[topic_mask].copy().reset_index(drop=True)
            if len(cluster_df) < self.settings.min_cluster_size:
                continue

            cluster_probabilities = None
            if probabilities is not None:
                cluster_probabilities = probabilities[topic_mask].tolist()

            topic_name = self._topic_name(model, topic_id, cluster_df, cluster_probabilities, view_type=view_type)
            doc_ids = [str(doc_id) for doc_id in cluster_df.get("_id", pd.Series(dtype=str)).tolist()]

            clusters.append(
                TopicCluster(
                    view_type=view_type,
                    company=company,
                    topic_id=int(topic_id),
                    topic_name=topic_name,
                    cluster_size=int(len(cluster_df)),
                    document_ids=doc_ids,
                    documents=cluster_df.to_dict(orient="records"),
                    probabilities=cluster_probabilities,
                )
            )

        return clusters, pd.DataFrame()

    def build_clusters(
        self,
        dataframe: pd.DataFrame,
        view_type: str,
        company: Optional[str] = None,
    ) -> List[TopicCluster]:
        """Cluster a dataframe into narrative topic groups."""

        clusters, _ = self.cluster_dataframe(dataframe, view_type=view_type, company=company)
        return clusters

    def _topic_name(
        self,
        model: Any,
        topic_id: int,
        cluster_df: Optional[pd.DataFrame] = None,
        cluster_probabilities: Optional[List[float]] = None,
        view_type: Optional[str] = None,
    ) -> str:
        """Generate a descriptive topic label (LLM-preferred when enabled)."""

        def _is_generic(tok: str) -> bool:
            tok_l = tok.lower().strip()
            if len(tok_l) <= 2:
                return True
            if tok_l in {"the", "of", "in", "to", "and", "for", "on", "at", "by", "is", "a", "an"}:
                return True
            return False

        topic_words = model.get_topic(topic_id) or []
        words = [word for word, _ in topic_words if word]
        if not words:
            return f"topic_{topic_id}"

        if self.settings.use_llm_topic_labels:
            try:
                llm_label = self._get_llm_label_for_cluster(
                    model,
                    topic_id,
                    cluster_df,
                    cluster_probabilities,
                    view_type=view_type,
                )
                if llm_label:
                    return llm_label
            except Exception:
                logger.exception("LLM label generation failed; falling back to keyword labels.")

        phrases = [w for w in words if (" " in w or "-" in w or "_" in w)]
        candidates = phrases + [w for w in words if w not in phrases]

        filtered = [w for w in candidates if not _is_generic(w)]
        if not filtered:
            filtered = candidates

        top_n = min(self.settings.topic_top_n_words, len(filtered)) if filtered else min(self.settings.topic_top_n_words, len(words))
        label_terms = filtered[:top_n] if filtered else words[:top_n]
        label = " / ".join(label_terms)

        token_count = sum(0 if _is_generic(t) else 1 for t in label_terms)
        if token_count <= 1 and cluster_df is not None and not cluster_df.empty:
            headline = ""
            for h in cluster_df.get("headline", pd.Series(dtype=str)).tolist():
                if h and str(h).strip():
                    headline = str(h).strip()
                    break
            if headline:
                snippet = (headline[:60] + "...") if len(headline) > 63 else headline
                return f"{label} — {snippet}" if label else snippet

        return label

    @staticmethod
    def _normalize_llm_label(label: str) -> str:
        normalized = str(label or "").strip()
        if not normalized:
            return ""
        if normalized.lower().startswith("topic:"):
            normalized = normalized.split(":", 1)[1].strip()
        return normalized

    def _get_llm_label_for_cluster(
        self,
        model: Any,
        topic_id: int,
        cluster_df: Optional[pd.DataFrame],
        cluster_probabilities: Optional[List[float]],
        view_type: Optional[str] = None,
    ) -> str:
        """Call the LLM with a representative sample of documents and return the label."""

        if cluster_df is None or cluster_df.empty:
            return ""

        if openai is None:
            logger.warning("OpenAI SDK not available for LLM topic labels.")
            return ""

        api_key = self._api_key()
        if not api_key:
            logger.warning("No OpenAI API key found for LLM topic labels.")
            return ""

        nr_docs = max(1, int(self.settings.llm_topic_nr_docs))
        cluster_size = len(cluster_df)
        take = min(cluster_size, nr_docs)

        if cluster_probabilities:
            indices = sorted(range(len(cluster_probabilities)), key=lambda i: cluster_probabilities[i], reverse=True)[:take]
        else:
            indices = list(range(min(take, cluster_size)))

        docs = []
        for idx in indices:
            row = cluster_df.iloc[idx]
            text = self._document_text(row)
            if len(text) > self.settings.llm_topic_doc_length:
                text = text[: self.settings.llm_topic_doc_length]
            docs.append(text)

        topic_words = model.get_topic(topic_id) or []
        keywords = ", ".join([w for w, _ in topic_words[: self.settings.topic_top_n_words]])

        prompt = self.settings.llm_topic_prompt or self._default_llm_prompt(view_type)
        if "[DOCUMENTS]" in prompt or "[KEYWORDS]" in prompt:
            user_content = prompt.replace("[DOCUMENTS]", "\n\n".join(docs)).replace("[KEYWORDS]", keywords)
        else:
            joined_docs = "\n\n".join(docs)
            user_content = f"[DOCUMENTS]\n\n{joined_docs}\n\nKeywords: {keywords}\n"

        system_prompt = self.settings.llm_topic_system_prompt or ""

        client = openai.OpenAI(api_key=api_key)

        attempts = 3
        delay = float(self.settings.llm_topic_delay_in_seconds or 1.0)
        for attempt in range(1, attempts + 1):
            try:
                if system_prompt:
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ]
                else:
                    messages = [{"role": "user", "content": user_content}]

                resp = client.chat.completions.create(model=self.settings.llm_topic_model, messages=messages)
                if resp and getattr(resp, "choices", None):
                    text = resp.choices[0].message.content if hasattr(resp.choices[0].message, "content") else resp.choices[0].text
                    label = self._normalize_llm_label(text)
                    time.sleep(delay)
                    return label
            except Exception:
                logger.exception("LLM request failed on attempt %s", attempt)
                if not self.settings.llm_topic_exponential_backoff or attempt == attempts:
                    break
                time.sleep(delay * (2 ** (attempt - 1)))

        return ""

    @staticmethod
    def _document_text(row: pd.Series) -> str:
        headline = str(row.get("headline", "") or "")
        content = str(row.get("content", "") or "")
        return "\n".join(part for part in (headline, content) if part.strip())
