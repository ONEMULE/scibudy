from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from research_mcp.analysis_config import settings_response, update_settings
from research_mcp.errors import IngestionError
from research_mcp.local_embedding_client import LocalEmbeddingClient
from research_mcp.local_reranker_client import LocalRerankerClient
from research_mcp.models import (
    AnalysisReportsResponse,
    AnalysisReportDetailResponse,
    AnalysisReportSummary,
    AnalysisSettingsResponse,
    AnalysisSummaryResponse,
    EvidenceRecord,
    IngestItemStatus,
    IngestResponse,
    LibraryDetailResponse,
    LibraryItemEntry,
)
from research_mcp.paths import ANALYSIS_DIR
from research_mcp.settings import Settings
from research_mcp.utils import now_utc_iso, slugify

try:
    from openai import OpenAI
except Exception:  # noqa: BLE001
    OpenAI = None


@dataclass
class ChunkRecord:
    id: str
    item_id: str
    chunk_index: int
    section: str
    text: str
    embedding: list[float] | None = None
    lexical_score: float | None = None
    semantic_score: float | None = None
    embedding_backend: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    chunking_version: str | None = None


class AnalysisEngine:
    def __init__(self, settings: Settings, db_path: Path, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.analysis_root = ANALYSIS_DIR
        self.analysis_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        self._http = httpx.Client(
            timeout=max(settings.request_timeout_sec * 2, 30.0),
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
            transport=transport,
        )
        self._openai = OpenAI(api_key=settings.openai_api_key) if (settings.openai_api_key and OpenAI is not None) else None
        self._openai_disabled_reason: str | None = None
        self._local_embedder = LocalEmbeddingClient(settings)
        self._local_reranker = LocalRerankerClient(settings)

    def close(self) -> None:
        self._http.close()
        self._local_embedder.close()
        self._local_reranker.close()

    def get_settings(self) -> AnalysisSettingsResponse:
        return settings_response(self.settings)

    def update_settings(self, **updates) -> AnalysisSettingsResponse:
        response = update_settings(**updates)
        self.settings = Settings()
        self._openai = OpenAI(api_key=self.settings.openai_api_key) if (self.settings.openai_api_key and OpenAI is not None) else None
        self._openai_disabled_reason = None
        self._local_embedder.close()
        self._local_embedder = LocalEmbeddingClient(self.settings)
        self._local_reranker.close()
        self._local_reranker = LocalRerankerClient(self.settings)
        return response

    def ingest_library(
        self,
        detail: LibraryDetailResponse,
        *,
        include_forums: bool = True,
        reingest: bool = False,
    ) -> IngestResponse:
        if detail.status != "ok" or not detail.library:
            return IngestResponse(
                status="error",
                generated_at=now_utc_iso(),
                mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                warnings=["library not found"],
            )
        records = []
        warnings: list[str] = []
        ready_count = 0
        for item in detail.items:
            record = self.ingest_item(detail.library.id, item, include_forums=include_forums, reingest=reingest)
            records.append(record)
            if record.extraction_status == "ready":
                ready_count += 1
            elif record.message:
                warnings.append(f"{item.effective_title}: {record.message}")
        status = "ok" if ready_count == len(records) else ("error" if ready_count == 0 else "partial")
        return IngestResponse(
            status=status,
            generated_at=now_utc_iso(),
            library_id=detail.library.id,
            mode=self.settings.analysis_mode,
            compute_backend=self.settings.compute_backend,
            processed_count=len(records),
            ready_count=ready_count,
            records=records,
            warnings=warnings,
        )

    def ingest_item(
        self,
        library_id: str,
        item: LibraryItemEntry,
        *,
        include_forums: bool = True,
        reingest: bool = False,
    ) -> IngestItemStatus:
        existing = self._conn.execute("SELECT * FROM ingested_items WHERE item_id = ?", (item.id,)).fetchone()
        if existing and not reingest:
            return IngestItemStatus(
                item_id=item.id,
                title=item.effective_title,
                extraction_status="ready" if existing["status"] == "ready" else "error",
                extraction_path=existing["text_path"],
                text_length=int(existing["text_length"] or 0),
                chunk_count=int(existing["chunk_count"] or 0),
                discussion_count=int(existing["discussion_count"] or 0),
                message="already ingested",
            )
        try:
            source_label, text = self._extract_item_text(item)
            if not text.strip():
                raise IngestionError("no extractable text found")
            text_path = self._write_text(library_id, item.id, text)
            chunks = self._chunk_text(item.id, text)
            if self._should_embed():
                self._embed_chunks(chunks)
            discussion = self._fetch_forum_evidence(item) if include_forums and self.settings.forum_enrichment_enabled else []
            self._store_ingest(item=item, library_id=library_id, source_label=source_label, text_path=text_path, chunks=chunks, discussion=discussion)
            return IngestItemStatus(
                item_id=item.id,
                title=item.effective_title,
                extraction_status="ready",
                extraction_path=str(text_path),
                text_length=len(text),
                chunk_count=len(chunks),
                discussion_count=len(discussion),
            )
        except Exception as exc:  # noqa: BLE001
            self._store_ingest_error(item.id, library_id, str(exc))
            return IngestItemStatus(
                item_id=item.id,
                title=item.effective_title,
                extraction_status="error",
                message=str(exc),
            )

    def summarize_item(self, item: LibraryItemEntry, *, topic: str | None = None) -> AnalysisSummaryResponse:
        chunks = self._load_chunks_for_item(item.id)
        evidence = self._load_discussion_for_item(item.id)
        if not chunks:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                item_id=item.id,
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                title=item.effective_title,
                summary="No ingested text available. Run ingestion first.",
                message="not ingested",
            )
        selected_chunks = self._select_chunks(chunks, topic=topic, max_chunks=8)
        summary, key_points = self._summarize_text(item.effective_title, selected_chunks, evidence, topic=topic)
        structured = self._structured_item_fields(item.effective_title, selected_chunks, topic=topic)
        key_points = _dedupe(
            [
                f"Problem: {structured['problem']}",
                f"Method: {structured['method']}",
                f"Protocol: {structured['protocol']}",
                f"Assumptions: {structured['assumptions']}",
                f"Failure modes: {structured['failure_modes']}",
                f"Limitations: {structured['limitations']}",
                f"Practical value: {structured['practical_value']}",
            ]
            + key_points
        )[:10]
        report = self._persist_report(
            analysis_kind="item_summary",
            title=item.effective_title,
            summary=summary,
            key_points=key_points,
            evidence=evidence,
            library_id=item.library_id,
            item_id=item.id,
            topic=topic,
        )
        self._persist_report(
            analysis_kind="method_card",
            title=f"{item.effective_title} method card",
            summary=structured["method"],
            key_points=[
                f"Problem: {structured['problem']}",
                f"Protocol: {structured['protocol']}",
                f"Assumptions: {structured['assumptions']}",
                f"Practical value: {structured['practical_value']}",
            ],
            evidence=evidence[:4],
            library_id=item.library_id,
            item_id=item.id,
            topic=topic,
        )
        self._persist_report(
            analysis_kind="limitation_card",
            title=f"{item.effective_title} limitation card",
            summary=structured["limitations"],
            key_points=[
                f"Failure modes: {structured['failure_modes']}",
                f"Assumptions: {structured['assumptions']}",
                f"Protocol: {structured['protocol']}",
            ],
            evidence=evidence[:4],
            library_id=item.library_id,
            item_id=item.id,
            topic=topic,
        )
        return AnalysisSummaryResponse(
            status="ok",
            generated_at=now_utc_iso(),
            library_id=item.library_id,
            item_id=item.id,
            topic=topic,
            analysis_mode=self.settings.analysis_mode,
            compute_backend=self._effective_backend(),
            title=item.effective_title,
            summary=summary,
            report_id=report.id,
            report_path=report.report_path,
            key_points=key_points,
            evidence=evidence[:5],
        )

    def summarize_library(self, detail: LibraryDetailResponse, *, topic: str | None = None) -> AnalysisSummaryResponse:
        if detail.status != "ok" or not detail.library:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                title="Library summary",
                summary="Library not found.",
            )
        parts = []
        points = []
        evidence: list[EvidenceRecord] = []
        for item in detail.items[: min(10, len(detail.items))]:
            item_summary = self.summarize_item(item, topic=topic)
            if item_summary.status == "ok":
                parts.append(f"{item.effective_title}: {item_summary.summary}")
                points.extend(item_summary.key_points[:2])
                evidence.extend(item_summary.evidence[:2])
        title = f"{detail.library.name} digest"
        if not parts:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                library_id=detail.library.id,
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                title=title,
                summary="No ingested items available.",
            )
        if self._effective_backend() == "openai":
            summary, key_points = self._openai_summarize(title, parts, topic=topic)
        else:
            summary = "\n\n".join(parts[:5])
            key_points = _dedupe(points)[:8]
        report = self._persist_report(
            analysis_kind="library_summary",
            title=title,
            summary=summary,
            key_points=key_points,
            evidence=evidence,
            library_id=detail.library.id,
            topic=topic,
        )
        self._persist_report(
            analysis_kind="topic_digest",
            title=f"{detail.library.name} topic digest",
            summary=summary,
            key_points=key_points[:10],
            evidence=evidence[:10],
            library_id=detail.library.id,
            topic=topic,
        )
        self._persist_report(
            analysis_kind="reading_order",
            title=f"{detail.library.name} reading order",
            summary="Suggested reading order for the current library.",
            key_points=self._reading_order_points(detail.items, topic=topic),
            evidence=[],
            library_id=detail.library.id,
            topic=topic,
        )
        return AnalysisSummaryResponse(
            status="ok",
            generated_at=now_utc_iso(),
            library_id=detail.library.id,
            topic=topic,
            analysis_mode=self.settings.analysis_mode,
            compute_backend=self._effective_backend(),
            title=title,
            summary=summary,
            report_id=report.id,
            report_path=report.report_path,
            key_points=key_points,
            evidence=evidence[:8],
        )

    def compare_items(self, items: list[LibraryItemEntry], *, topic: str | None = None) -> AnalysisSummaryResponse:
        summaries = [self.summarize_item(item, topic=topic) for item in items]
        successful = [summary for summary in summaries if summary.status == "ok"]
        if not successful:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                title="Comparison",
                summary="No ingested items available.",
            )
        if self._effective_backend() == "openai":
            prompt_parts = [f"{summary.title}\n{summary.summary}" for summary in successful[:6]]
            summary, key_points = self._openai_summarize("Comparison", prompt_parts, topic=topic or "comparison")
        else:
            summary = "\n".join(f"- {summary.title}: {summary.summary}" for summary in successful[:6])
            key_points = _dedupe(point for summary in successful for point in summary.key_points)[:10]
        evidence = [ev for summary in successful for ev in summary.evidence]
        library_id = successful[0].library_id if successful and successful[0].library_id else None
        report = self._persist_report(
            analysis_kind="item_compare",
            title="Comparison",
            summary=summary,
            key_points=key_points,
            evidence=evidence,
            library_id=library_id,
            topic=topic,
        )
        self._persist_report(
            analysis_kind="comparison_matrix",
            title="Comparison matrix",
            summary=summary,
            key_points=[
                f"{summary.title}: {summary.summary[:220]}"
                for summary in successful[:6]
            ],
            evidence=evidence[:10],
            library_id=library_id,
            topic=topic,
        )
        return AnalysisSummaryResponse(
            status="ok",
            generated_at=now_utc_iso(),
            library_id=library_id,
            analysis_mode=self.settings.analysis_mode,
            compute_backend=self._effective_backend(),
            title="Comparison",
            topic=topic,
            summary=summary,
            report_id=report.id,
            report_path=report.report_path,
            key_points=key_points,
            evidence=evidence[:8],
        )

    def analyze_topic(self, detail: LibraryDetailResponse, *, topic: str) -> AnalysisSummaryResponse:
        if detail.status != "ok" or not detail.library:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                title="Topic analysis",
                summary="Library not found.",
            )
        all_chunks = []
        all_evidence = []
        for item in detail.items:
            all_chunks.extend(self._load_chunks_for_item(item.id))
            all_evidence.extend(self._load_discussion_for_item(item.id))
        selected_chunks = self._select_chunks(all_chunks, topic=topic, max_chunks=10)
        selected_evidence = [
            ev
            for ev in sorted(all_evidence, key=lambda item: (item.confidence_score or item.relevance_score or 0.0), reverse=True)
            if (ev.confidence_score or ev.relevance_score or 0.0) >= 0.35
        ][:10]
        summary, key_points = self._summarize_text(f"{detail.library.name}: {topic}", selected_chunks, selected_evidence, topic=topic)
        report = self._persist_report(
            analysis_kind="topic_analysis",
            title=f"{detail.library.name}: {topic}",
            summary=summary,
            key_points=key_points,
            evidence=selected_evidence,
            library_id=detail.library.id,
            topic=topic,
        )
        return AnalysisSummaryResponse(
            status="ok",
            generated_at=now_utc_iso(),
            library_id=detail.library.id,
            topic=topic,
            analysis_mode=self.settings.analysis_mode,
            compute_backend=self._effective_backend(),
            title=f"{detail.library.name}: {topic}",
            summary=summary,
            report_id=report.id,
            report_path=report.report_path,
            key_points=key_points,
            evidence=selected_evidence[:8],
        )

    def search_library_evidence(self, detail: LibraryDetailResponse, *, query: str, max_hits: int = 8) -> AnalysisSummaryResponse:
        if detail.status != "ok" or not detail.library:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                title="Evidence search",
                summary="Library not found.",
            )
        all_chunks = []
        for item in detail.items:
            all_chunks.extend(self._load_chunks_for_item(item.id))
        selected_chunks = self._select_chunks(all_chunks, topic=query, max_chunks=max_hits)
        summary = "\n".join(
            f"- {chunk.section} [lexical={round(chunk.lexical_score or 0.0, 3)}, semantic={round(chunk.semantic_score or 0.0, 3)}]: "
            f"{chunk.text[:220].replace(chr(10), ' ')}"
            for chunk in selected_chunks[:max_hits]
        )
        key_points = [
            f"{chunk.section}: {chunk.text[:180].replace(chr(10), ' ')} "
            f"(lexical={round(chunk.lexical_score or 0.0, 3)}, semantic={round(chunk.semantic_score or 0.0, 3)})"
            for chunk in selected_chunks[:max_hits]
        ]
        evidence = [
            EvidenceRecord(
                id=chunk.id,
                item_id=chunk.item_id,
                source_type="pdf" if chunk.section != "html" else "html",
                title=f"Chunk {chunk.chunk_index} [{chunk.section}]",
                excerpt=chunk.text[:320],
                relevance_score=round((chunk.lexical_score or 0.0) * 0.6 + (chunk.semantic_score or 0.0) * 0.4, 6),
                confidence_score=round(max(chunk.lexical_score or 0.0, chunk.semantic_score or 0.0), 6),
                metadata={
                    "section": chunk.section,
                    "chunk_index": chunk.chunk_index,
                    "lexical_score": round(chunk.lexical_score or 0.0, 6),
                    "semantic_score": round(chunk.semantic_score or 0.0, 6),
                    "semantic_backend": self._semantic_backend_label(),
                    "embedding_backend": chunk.embedding_backend,
                    "embedding_model": chunk.embedding_model,
                    "embedding_dimension": chunk.embedding_dimension,
                    "chunking_version": chunk.chunking_version,
                },
            )
            for chunk in selected_chunks[:max_hits]
        ]
        report = self._persist_report(
            analysis_kind="evidence_search",
            title=f"Evidence search: {query}",
            summary=summary,
            key_points=key_points,
            evidence=evidence,
            library_id=detail.library.id,
            topic=query,
        )
        return AnalysisSummaryResponse(
            status="ok",
            generated_at=now_utc_iso(),
            library_id=detail.library.id,
            topic=query,
            analysis_mode=self.settings.analysis_mode,
            compute_backend=self._effective_backend(),
            title=f"Evidence search: {query}",
            summary=summary,
            report_id=report.id,
            report_path=report.report_path,
            key_points=key_points,
            evidence=[
                ev.model_copy(update={"metadata": {**ev.metadata, "report_id": report.id}})
                for ev in evidence
            ],
        )

    def build_research_synthesis(self, detail: LibraryDetailResponse, *, topic: str, max_items: int = 50) -> AnalysisSummaryResponse:
        if detail.status != "ok" or not detail.library:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self.settings.compute_backend,
                title="Research synthesis",
                summary="Library not found.",
            )
        selected_items = [item for item in detail.items if not item.archived][: max(1, min(int(max_items), 50))]
        method_cards: list[dict[str, Any]] = []
        matrix_rows: list[dict[str, Any]] = []
        claims: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        evidence_records: list[EvidenceRecord] = []
        warnings: list[str] = []

        for item in selected_items:
            chunks = self._load_chunks_for_item(item.id)
            if not chunks:
                warnings.append(f"{item.effective_title}: not ingested")
                continue
            selected_chunks = self._select_chunks(chunks, topic=topic, max_chunks=5)
            fields = self._structured_item_fields(item.effective_title, selected_chunks, topic=topic)
            chunk_evidence = [self._chunk_evidence_record(chunk, item) for chunk in selected_chunks[:3]]
            evidence_records.extend(chunk_evidence)
            card = {
                "item_id": item.id,
                "rank": item.rank,
                "title": item.effective_title,
                "source": item.source,
                "year": item.year,
                "doi": item.doi,
                "problem": fields["problem"],
                "method": fields["method"],
                "protocol": fields["protocol"],
                "assumptions": fields["assumptions"],
                "failure_modes": fields["failure_modes"],
                "limitations": fields["limitations"],
                "practical_value": fields["practical_value"],
                "evidence_ids": [ev.id for ev in chunk_evidence],
            }
            method_cards.append(card)
            matrix_rows.append(
                {
                    "title": item.effective_title,
                    "method": fields["method"],
                    "calibration_protocol": fields["protocol"],
                    "assumptions": fields["assumptions"],
                    "failure_modes": fields["failure_modes"],
                    "limitations": fields["limitations"],
                    "practical_value": fields["practical_value"],
                }
            )
            for claim_text, claim_type in [
                (fields["method"], "method"),
                (fields["protocol"], "calibration_protocol"),
                (fields["failure_modes"], "failure_mode"),
                (fields["limitations"], "limitation"),
            ]:
                claim_id = slugify(f"{item.id}-{claim_type}-{claim_text}", max_length=72)
                claims.append(
                    {
                        "id": claim_id,
                        "type": claim_type,
                        "item_id": item.id,
                        "title": item.effective_title,
                        "claim": claim_text,
                        "evidence_ids": [ev.id for ev in chunk_evidence],
                        "confidence": self._claim_confidence(claim_text, chunk_evidence),
                    }
                )
                for ev in chunk_evidence:
                    edges.append({"claim_id": claim_id, "evidence_id": ev.id, "relation": "supports"})

        if not method_cards:
            return AnalysisSummaryResponse(
                status="error",
                generated_at=now_utc_iso(),
                library_id=detail.library.id,
                topic=topic,
                analysis_mode=self.settings.analysis_mode,
                compute_backend=self._effective_backend(),
                title=f"{detail.library.name}: synthesis",
                summary="No ingested items available. Run ingestion first.",
                warnings=warnings,
            )

        protocol_digest = self._calibration_protocol_digest(method_cards, topic=topic)
        structured_payload = {
            "schema_version": "research_synthesis.v1",
            "library_id": detail.library.id,
            "library_name": detail.library.name,
            "topic": topic,
            "requested_max_items": max_items,
            "analyzed_item_count": len(method_cards),
            "method_cards": method_cards,
            "comparison_matrix": matrix_rows,
            "claim_evidence_graph": {"claims": claims, "edges": edges},
            "calibration_protocol_digest": protocol_digest,
            "warnings": warnings,
        }
        summary = self._synthesis_summary(detail.library.name, topic, method_cards, protocol_digest)
        key_points = _dedupe(
            [
                f"Analyzed {len(method_cards)} ingested papers for {topic}.",
                *protocol_digest["protocol_steps"][:4],
                *protocol_digest["failure_modes"][:3],
                *protocol_digest["practical_recommendations"][:3],
            ]
        )[:12]
        report = self._persist_report(
            analysis_kind="research_synthesis",
            title=f"{detail.library.name}: {topic} synthesis",
            summary=summary,
            key_points=key_points,
            evidence=evidence_records[:20],
            library_id=detail.library.id,
            topic=topic,
            structured_payload=structured_payload,
        )
        self._persist_report(
            analysis_kind="comparison_matrix",
            title=f"{detail.library.name}: {topic} comparison matrix",
            summary="Cross-paper method and calibration comparison matrix.",
            key_points=[f"{row['title']}: {row['method'][:180]}" for row in matrix_rows[:12]],
            evidence=evidence_records[:20],
            library_id=detail.library.id,
            topic=topic,
            structured_payload={"schema_version": "comparison_matrix.v1", "rows": matrix_rows},
        )
        self._persist_report(
            analysis_kind="claim_evidence_graph",
            title=f"{detail.library.name}: {topic} claim/evidence graph",
            summary="Structured claims linked to supporting evidence chunks.",
            key_points=[claim["claim"] for claim in claims[:12]],
            evidence=evidence_records[:20],
            library_id=detail.library.id,
            topic=topic,
            structured_payload={"schema_version": "claim_evidence_graph.v1", "claims": claims, "edges": edges},
        )
        self._persist_report(
            analysis_kind="calibration_protocol_digest",
            title=f"{detail.library.name}: {topic} calibration protocol digest",
            summary=protocol_digest["summary"],
            key_points=protocol_digest["protocol_steps"] + protocol_digest["practical_recommendations"],
            evidence=evidence_records[:20],
            library_id=detail.library.id,
            topic=topic,
            structured_payload={"schema_version": "calibration_protocol_digest.v1", **protocol_digest},
        )
        return AnalysisSummaryResponse(
            status="ok",
            generated_at=now_utc_iso(),
            library_id=detail.library.id,
            topic=topic,
            analysis_mode=self.settings.analysis_mode,
            compute_backend=self._effective_backend(),
            title=f"{detail.library.name}: {topic} synthesis",
            summary=summary,
            report_id=report.id,
            report_path=report.report_path,
            key_points=key_points,
            evidence=evidence_records[:10],
            structured_payload=structured_payload,
            warnings=warnings,
        )

    def list_reports(self, *, library_id: str | None = None, item_id: str | None = None) -> AnalysisReportsResponse:
        query = "SELECT * FROM analysis_reports"
        clauses = []
        params: list[Any] = []
        if library_id:
            clauses.append("library_id = ?")
            params.append(library_id)
        if item_id:
            clauses.append("item_id = ?")
            params.append(item_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC"
        rows = self._conn.execute(query, tuple(params)).fetchall()
        return AnalysisReportsResponse(
            status="ok",
            generated_at=now_utc_iso(),
            reports=[self._report_summary_from_row(row) for row in rows],
        )

    def read_report(self, report_id: str) -> AnalysisReportDetailResponse:
        row = self._conn.execute("SELECT * FROM analysis_reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return AnalysisReportDetailResponse(status="error", generated_at=now_utc_iso(), message="report not found")
        return AnalysisReportDetailResponse(
            status="ok",
            generated_at=now_utc_iso(),
            report=self._report_summary_from_row(row),
            summary=row["summary"],
            key_points=json.loads(row["key_points_json"] or "[]"),
            evidence=[EvidenceRecord.model_validate(item) for item in json.loads(row["evidence_json"] or "[]")],
            structured_payload=json.loads(row["structured_payload_json"] or "{}"),
        )

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ingested_items (
                    item_id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL,
                    source_label TEXT,
                    text_path TEXT,
                    status TEXT NOT NULL,
                    text_length INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    discussion_count INTEGER NOT NULL DEFAULT 0,
                    message TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS item_chunks (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    section TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding_json TEXT,
                    embedding_backend TEXT,
                    embedding_model TEXT,
                    embedding_dimension INTEGER,
                    chunking_version TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS item_chunks_fts USING fts5(id UNINDEXED, item_id UNINDEXED, text);

                CREATE TABLE IF NOT EXISTS discussion_evidence (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT,
                    url TEXT,
                    excerpt TEXT,
                    relevance_score REAL,
                    confidence_score REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analysis_reports (
                    id TEXT PRIMARY KEY,
                    library_id TEXT,
                    item_id TEXT,
                    analysis_kind TEXT NOT NULL,
                    topic TEXT,
                    title TEXT NOT NULL,
                    analysis_mode TEXT NOT NULL,
                    compute_backend TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    key_points_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    structured_payload_json TEXT NOT NULL DEFAULT '{}',
                    report_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column("discussion_evidence", "confidence_score", "REAL")
            self._ensure_column("item_chunks", "embedding_backend", "TEXT")
            self._ensure_column("item_chunks", "embedding_model", "TEXT")
            self._ensure_column("item_chunks", "embedding_dimension", "INTEGER")
            self._ensure_column("item_chunks", "chunking_version", "TEXT")
            self._ensure_column("analysis_reports", "structured_payload_json", "TEXT NOT NULL DEFAULT '{}'")

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    def _extract_item_text(self, item: LibraryItemEntry) -> tuple[str, str]:
        local_pdf = Path(item.local_pdf_path).expanduser() if item.local_pdf_path else None
        if local_pdf and local_pdf.exists():
            return "local_pdf", self._extract_pdf_text(local_pdf.read_bytes())
        for url in [item.pdf_url, item.open_access_url]:
            if url:
                response = self._http.get(url)
                response.raise_for_status()
                if response.content.startswith(b"%PDF") or "pdf" in (response.headers.get("content-type") or "").lower():
                    return url, self._extract_pdf_text(response.content)
        for url in [item.landing_url, item.open_access_url]:
            if url:
                response = self._http.get(url)
                response.raise_for_status()
                return url, self._extract_html_text(response.text)
        raise IngestionError("no available PDF or HTML source")

    def _extract_pdf_text(self, content: bytes) -> str:
        reader = PdfReader(BytesIO(content))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        return "\n\n".join(page for page in pages if page)

    def _extract_html_text(self, html: str) -> str:
        lowered = html.lower()
        if "incapsula incident" in lowered or "request unsuccessful" in lowered or "access denied" in lowered:
            raise IngestionError("blocked HTML source")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        lines = [part.strip() for part in soup.get_text("\n").splitlines()]
        text = "\n".join(line for line in lines if line)
        if len(text) < 150:
            raise IngestionError("HTML extraction too short to be useful")
        return text

    def _write_text(self, library_id: str, item_id: str, text: str) -> Path:
        target_dir = self.analysis_root / library_id / "texts"
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{item_id}.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def _chunk_text(self, item_id: str, text: str) -> list[ChunkRecord]:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        chunks: list[ChunkRecord] = []
        buffer = ""
        chunk_index = 0
        chunking_version = f"{self.settings.chunk_size}:{self.settings.chunk_overlap}"
        for paragraph in paragraphs:
            if len(buffer) + len(paragraph) + 2 <= self.settings.chunk_size:
                buffer = f"{buffer}\n\n{paragraph}".strip()
                continue
            if buffer:
                chunks.append(
                    ChunkRecord(
                        id=f"{item_id}_{chunk_index}",
                        item_id=item_id,
                        chunk_index=chunk_index,
                        section=_infer_section(buffer),
                        text=buffer,
                        chunking_version=chunking_version,
                    )
                )
                chunk_index += 1
            overlap = buffer[-self.settings.chunk_overlap :] if buffer else ""
            buffer = f"{overlap}\n\n{paragraph}".strip()
        if buffer:
            chunks.append(
                ChunkRecord(
                    id=f"{item_id}_{chunk_index}",
                    item_id=item_id,
                    chunk_index=chunk_index,
                    section=_infer_section(buffer),
                    text=buffer,
                    chunking_version=chunking_version,
                )
            )
        return chunks

    def _should_embed(self) -> bool:
        return self.settings.analysis_mode in {"hybrid", "semantic_heavy"}

    def _embed_chunks(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return
        if self._effective_backend() == "openai" and self._openai is not None:
            try:
                for start in range(0, len(chunks), 32):
                    batch = chunks[start : start + 32]
                    response = self._openai.embeddings.create(
                        model=self.settings.openai_embedding_model,
                        input=[chunk.text[:8000] for chunk in batch],
                    )
                    for chunk, embedding in zip(batch, response.data, strict=False):
                        chunk.embedding = list(embedding.embedding)
                        chunk.embedding_backend = "openai"
                        chunk.embedding_model = self.settings.openai_embedding_model
                        chunk.embedding_dimension = len(chunk.embedding)
                return
            except Exception as exc:  # noqa: BLE001
                self._disable_openai_runtime(exc)
        if self._effective_backend() == "local_transformer":
            vectors = self._local_embedder.embed([chunk.text[:8000] for chunk in chunks], input_type="passage")
            if vectors:
                for chunk, vector in zip(chunks, vectors, strict=False):
                    chunk.embedding = vector
                    chunk.embedding_backend = "local_transformer"
                    chunk.embedding_model = self.settings.local_embedding_model
                    chunk.embedding_dimension = len(vector)
                return
        for chunk in chunks:
            chunk.embedding = _local_embed(chunk.text, dim=self.settings.local_embedding_dimension)
            chunk.embedding_backend = "local_heuristic"
            chunk.embedding_model = self.settings.local_embedding_model
            chunk.embedding_dimension = self.settings.local_embedding_dimension

    def _store_ingest(
        self,
        *,
        item: LibraryItemEntry,
        library_id: str,
        source_label: str,
        text_path: Path,
        chunks: list[ChunkRecord],
        discussion: list[EvidenceRecord],
    ) -> None:
        now = now_utc_iso()
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM item_chunks WHERE item_id = ?", (item.id,))
            self._conn.execute("DELETE FROM item_chunks_fts WHERE item_id = ?", (item.id,))
            self._conn.execute("DELETE FROM discussion_evidence WHERE item_id = ?", (item.id,))
            for chunk in chunks:
                self._conn.execute(
                    """
                    INSERT INTO item_chunks(
                        id, item_id, chunk_index, section, text, embedding_json,
                        embedding_backend, embedding_model, embedding_dimension, chunking_version, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        item.id,
                        chunk.chunk_index,
                        chunk.section,
                        chunk.text,
                        json.dumps(chunk.embedding) if chunk.embedding else None,
                        chunk.embedding_backend,
                        chunk.embedding_model,
                        chunk.embedding_dimension,
                        chunk.chunking_version,
                        now,
                    ),
                )
                self._conn.execute("INSERT INTO item_chunks_fts(id, item_id, text) VALUES (?, ?, ?)", (chunk.id, item.id, chunk.text))
            for evidence in discussion:
                self._conn.execute(
                    """
                    INSERT INTO discussion_evidence(id, item_id, source_type, title, url, excerpt, relevance_score, confidence_score, metadata_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence.id,
                        item.id,
                        evidence.source_type,
                        evidence.title,
                        evidence.url,
                        evidence.excerpt,
                        evidence.relevance_score,
                        evidence.confidence_score,
                        json.dumps(evidence.metadata, ensure_ascii=False),
                        now,
                    ),
                )
            self._conn.execute(
                """
                INSERT INTO ingested_items(item_id, library_id, source_label, text_path, status, text_length, chunk_count, discussion_count, message, updated_at)
                VALUES (?, ?, ?, ?, 'ready', ?, ?, ?, '', ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    source_label = excluded.source_label,
                    text_path = excluded.text_path,
                    status = excluded.status,
                    text_length = excluded.text_length,
                    chunk_count = excluded.chunk_count,
                    discussion_count = excluded.discussion_count,
                    message = excluded.message,
                    updated_at = excluded.updated_at
                """,
                (item.id, library_id, source_label, str(text_path), len(text_path.read_text(encoding='utf-8')), len(chunks), len(discussion), now),
            )

    def _store_ingest_error(self, item_id: str, library_id: str, message: str) -> None:
        now = now_utc_iso()
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM item_chunks WHERE item_id = ?", (item_id,))
            self._conn.execute("DELETE FROM item_chunks_fts WHERE item_id = ?", (item_id,))
            self._conn.execute("DELETE FROM discussion_evidence WHERE item_id = ?", (item_id,))
            self._conn.execute(
                """
                INSERT INTO ingested_items(item_id, library_id, source_label, text_path, status, text_length, chunk_count, discussion_count, message, updated_at)
                VALUES (?, ?, '', '', 'error', 0, 0, 0, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    status = excluded.status,
                    message = excluded.message,
                    updated_at = excluded.updated_at
                """,
                (item_id, library_id, message, now),
            )

    def _load_chunks_for_item(self, item_id: str) -> list[ChunkRecord]:
        rows = self._conn.execute("SELECT * FROM item_chunks WHERE item_id = ? ORDER BY chunk_index ASC", (item_id,)).fetchall()
        return [
            ChunkRecord(
                id=row["id"],
                item_id=row["item_id"],
                chunk_index=row["chunk_index"],
                section=row["section"],
                text=row["text"],
                embedding=json.loads(row["embedding_json"]) if row["embedding_json"] else None,
                embedding_backend=row["embedding_backend"],
                embedding_model=row["embedding_model"],
                embedding_dimension=row["embedding_dimension"],
                chunking_version=row["chunking_version"],
            )
            for row in rows
        ]

    def _load_discussion_for_item(self, item_id: str) -> list[EvidenceRecord]:
        rows = self._conn.execute("SELECT * FROM discussion_evidence WHERE item_id = ? ORDER BY COALESCE(confidence_score, relevance_score, 0) DESC, updated_at DESC", (item_id,)).fetchall()
        return [
            EvidenceRecord(
                id=row["id"],
                item_id=item_id,
                source_type=row["source_type"],
                title=row["title"],
                url=row["url"],
                excerpt=row["excerpt"],
                relevance_score=row["relevance_score"],
                confidence_score=row["confidence_score"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )
            for row in rows
        ]

    def _select_chunks(self, chunks: list[ChunkRecord], *, topic: str | None, max_chunks: int) -> list[ChunkRecord]:
        if not chunks:
            return []
        if not topic:
            return chunks[:max_chunks]
        ranked = self._rank_chunks(chunks, topic=topic)
        return self._rerank_chunks(ranked[: max(max_chunks * 3, 12)], query=topic)[:max_chunks]

    def _rank_chunks(self, chunks: list[ChunkRecord], *, topic: str) -> list[ChunkRecord]:
        if not chunks:
            return []
        lexical_rows = self._lexical_rank(chunks, topic)
        lexical_scores = {chunk.id: score for score, chunk in lexical_rows}
        semantic_scores: dict[str, float] = {}
        query_embedding = self._embed_query(topic) if self._should_embed() else None
        if query_embedding:
            for chunk in chunks:
                if chunk.embedding:
                    semantic_scores[chunk.id] = max(self._cosine_similarity(query_embedding, chunk.embedding), 0.0)
        ranked: list[tuple[float, ChunkRecord]] = []
        for chunk in chunks:
            lexical_score = lexical_scores.get(chunk.id, 0.0)
            semantic_score = semantic_scores.get(chunk.id, 0.0)
            chunk.lexical_score = lexical_score
            chunk.semantic_score = semantic_score
            if self.settings.analysis_mode == "semantic_heavy":
                combined = semantic_score * 0.7 + lexical_score * 0.3
            elif self.settings.analysis_mode == "hybrid":
                combined = lexical_score * 0.6 + semantic_score * 0.4
            else:
                combined = lexical_score
            ranked.append((combined, chunk))
        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].semantic_score or 0.0,
                item[1].lexical_score or 0.0,
                -item[1].chunk_index,
            ),
            reverse=True,
        )
        ordered = [chunk for _, chunk in ranked]
        return ordered if any((chunk.lexical_score or 0.0) > 0 or (chunk.semantic_score or 0.0) > 0 for chunk in ordered) else chunks[:]

    def _rerank_chunks(self, chunks: list[ChunkRecord], *, query: str) -> list[ChunkRecord]:
        if len(chunks) <= 1 or not self._local_reranker.is_configured():
            return chunks
        # Free the embedding model before loading the reranker on a 12 GB card.
        self._local_embedder.close()
        scores = self._local_reranker.rerank(query, [chunk.text[:4000] for chunk in chunks])
        if not scores:
            return chunks
        reranked: list[tuple[float, ChunkRecord]] = []
        for chunk, score in zip(chunks, scores, strict=False):
            chunk.semantic_score = max(chunk.semantic_score or 0.0, float(score))
            reranked.append((float(score), chunk))
        reranked.sort(key=lambda item: (item[0], item[1].lexical_score or 0.0), reverse=True)
        return [chunk for _, chunk in reranked]

    def _embed_query(self, text: str) -> list[float] | None:
        if self._effective_backend() == "openai" and self._openai is not None:
            try:
                response = self._openai.embeddings.create(model=self.settings.openai_embedding_model, input=text[:8000])
                return list(response.data[0].embedding)
            except Exception as exc:  # noqa: BLE001
                self._disable_openai_runtime(exc)
        if self._effective_backend() == "local_transformer":
            vectors = self._local_embedder.embed([text[:8000]], input_type="query")
            if vectors:
                return vectors[0]
        return _local_embed(text, dim=self.settings.local_embedding_dimension)

    def _lexical_rank(self, chunks: list[ChunkRecord], topic: str) -> list[tuple[float, ChunkRecord]]:
        tokens = [token.lower() for token in topic.split() if token.strip()]
        scored: list[tuple[float, ChunkRecord]] = []
        for chunk in chunks:
            score = sum(chunk.text.lower().count(token) for token in tokens)
            if score > 0:
                scored.append((float(score), chunk))
        max_score = max((score for score, _ in scored), default=0.0)
        if max_score > 0:
            scored = [(score / max_score, chunk) for score, chunk in scored]
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _summarize_text(self, title: str, chunks: list[ChunkRecord], evidence: list[EvidenceRecord], *, topic: str | None) -> tuple[str, list[str]]:
        if self._effective_backend() == "openai" and self._openai is not None:
            try:
                context = "\n\n".join(chunk.text[:1400] for chunk in chunks[:6])
                discussion = "\n".join(f"- {ev.source_type}: {ev.title or ev.excerpt or ''}" for ev in evidence[:4])
                prompt = (
                    f"Summarize this paper or evidence packet for research use.\nTitle: {title}\n"
                    f"Focus topic: {topic or 'general'}\n"
                    f"Text:\n{context}\n\nDiscussion evidence:\n{discussion}\n\n"
                    "Return a concise synthesis followed by 6 short key points."
                )
                response = self._openai.responses.create(model=self.settings.openai_summary_model, input=prompt)
                text = response.output_text.strip()
                lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
                return (lines[0] if lines else text), (lines[1:7] if len(lines) > 1 else [text])
            except Exception as exc:  # noqa: BLE001
                self._disable_openai_runtime(exc)

        joined = "\n\n".join(chunk.text for chunk in chunks[:6])
        sentences = _sentence_split(joined)
        summary = " ".join(sentences[:4]).strip()
        key_points = _extract_key_points(sentences, topic=topic)
        if evidence:
            key_points.extend(
                [
                    f"Forum signal ({ev.source_type}, confidence={round(ev.confidence_score or ev.relevance_score or 0, 2)}): {ev.title or (ev.excerpt or '')[:80]}"
                    for ev in evidence[:3]
                ]
            )
        return summary or joined[:500], _dedupe(key_points)[:10]

    def _structured_item_fields(self, title: str, chunks: list[ChunkRecord], *, topic: str | None) -> dict[str, str]:
        text = "\n\n".join(chunk.text for chunk in chunks[:8])
        sentences = _sentence_split(text)
        lower_topic = topic.lower() if topic else None
        fields = {
            "problem": _pick_sentence(
                sentences,
                ["problem", "challenge", "goal", "we study", "we consider", *(lower_topic.split() if lower_topic else [])],
                fallback=f"{title} studies a calibration-relevant research problem.",
            ),
            "method": _pick_sentence(
                sentences,
                ["we propose", "we introduce", "method", "approach", "algorithm", "framework"],
                fallback=f"{title} introduces a method or workflow relevant to the target topic.",
            ),
            "protocol": _pick_sentence(
                sentences,
                ["experiment", "evaluation", "protocol", "coverage", "rank", "simulation", "benchmark"],
                fallback="Evaluation protocol details were not explicit in the extracted text.",
            ),
            "assumptions": _pick_sentence(
                sentences,
                ["assume", "assumption", "under", "requires", "prior", "model"],
                fallback="Assumptions are not explicitly stated in the extracted sections.",
            ),
            "failure_modes": _pick_sentence(
                sentences,
                ["fail", "failure", "bias", "misspecification", "autocorrelation", "mismatch", "limitation"],
                fallback="Failure modes are not clearly spelled out in the extracted text.",
            ),
            "limitations": _pick_sentence(
                sentences,
                ["limitation", "however", "but", "cost", "expensive", "future work"],
                fallback="Limitations were not explicit in the extracted sections.",
            ),
            "practical_value": _pick_sentence(
                sentences,
                ["practical", "workflow", "useful", "diagnostic", "application", "recommend"],
                fallback="Practical value needs manual inspection of the full paper.",
            ),
        }
        return fields

    def _chunk_evidence_record(self, chunk: ChunkRecord, item: LibraryItemEntry) -> EvidenceRecord:
        relevance = round((chunk.lexical_score or 0.0) * 0.6 + (chunk.semantic_score or 0.0) * 0.4, 6)
        confidence = round(max(chunk.lexical_score or 0.0, chunk.semantic_score or 0.0, 0.25), 6)
        return EvidenceRecord(
            id=chunk.id,
            item_id=item.id,
            source_type="pdf" if chunk.section != "html" else "html",
            title=f"{item.effective_title}: chunk {chunk.chunk_index} [{chunk.section}]",
            url=item.landing_url or item.open_access_url or item.pdf_url,
            excerpt=chunk.text[:420],
            relevance_score=relevance,
            confidence_score=confidence,
            metadata={
                "rank": item.rank,
                "source": item.source,
                "year": item.year,
                "doi": item.doi,
                "section": chunk.section,
                "chunk_index": chunk.chunk_index,
                "lexical_score": round(chunk.lexical_score or 0.0, 6),
                "semantic_score": round(chunk.semantic_score or 0.0, 6),
                "semantic_backend": self._semantic_backend_label(),
                "embedding_backend": chunk.embedding_backend,
                "embedding_model": chunk.embedding_model,
            },
        )

    def _claim_confidence(self, claim: str, evidence: list[EvidenceRecord]) -> float:
        if claim.startswith("Failure modes are not") or claim.startswith("Limitations were not"):
            return 0.35
        if not evidence:
            return 0.45
        return round(min(0.95, max(ev.confidence_score or 0.0 for ev in evidence)), 3)

    def _calibration_protocol_digest(self, method_cards: list[dict[str, Any]], *, topic: str) -> dict[str, list[str] | str]:
        protocols = _dedupe([card["protocol"] for card in method_cards])
        assumptions = _dedupe([card["assumptions"] for card in method_cards])
        failure_modes = _dedupe([card["failure_modes"] for card in method_cards])
        limitations = _dedupe([card["limitations"] for card in method_cards])
        practical = _dedupe([card["practical_value"] for card in method_cards])
        return {
            "summary": f"{topic} synthesis across {len(method_cards)} ingested papers, emphasizing calibration protocol, assumptions, and failure modes.",
            "protocol_steps": protocols[:8] or ["No explicit calibration protocol steps were detected."],
            "assumptions": assumptions[:8] or ["Assumptions require manual verification."],
            "failure_modes": failure_modes[:8] or ["Failure modes require manual verification."],
            "limitations": limitations[:8] or ["Limitations require manual verification."],
            "practical_recommendations": practical[:8] or ["Inspect method cards before applying these methods."],
        }

    def _synthesis_summary(self, library_name: str, topic: str, method_cards: list[dict[str, Any]], protocol_digest: dict[str, Any]) -> str:
        top_methods = "; ".join(card["method"] for card in method_cards[:3])
        top_protocols = "; ".join(protocol_digest.get("protocol_steps", [])[:3])
        top_failures = "; ".join(protocol_digest.get("failure_modes", [])[:3])
        return (
            f"{library_name} synthesis for {topic}. "
            f"Main method signals: {top_methods}. "
            f"Calibration/evaluation protocols: {top_protocols}. "
            f"Observed failure or risk signals: {top_failures}."
        )

    def _reading_order_points(self, items: list[LibraryItemEntry], *, topic: str | None) -> list[str]:
        points = []
        for index, item in enumerate(items[:8], start=1):
            label = item.effective_title
            rationale = f"start with this ranked item for {topic}" if index == 1 and topic else "use this as supporting context"
            if item.favorite:
                rationale = "favorite item; prioritize early"
            points.append(f"{index}. {label} ({item.source}, {item.year or 'n.d.'}) — {rationale}.")
        return points or ["No ranked items available for a reading order."]

    def _openai_summarize(self, title: str, parts: list[str], *, topic: str | None) -> tuple[str, list[str]]:
        if self._openai is None:
            merged = "\n".join(parts[:5])
            return merged, [part[:180] for part in parts[:5]]
        try:
            prompt = (
                f"Create a compact research digest.\nTitle: {title}\nFocus topic: {topic or 'general'}\n\n"
                + "\n\n".join(parts[:8])
                + "\n\nReturn a short digest followed by 6 concise key points."
            )
            response = self._openai.responses.create(model=self.settings.openai_summary_model, input=prompt)
            text = response.output_text.strip()
            lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
            return (lines[0] if lines else text), (lines[1:7] if len(lines) > 1 else [text])
        except Exception as exc:  # noqa: BLE001
            self._disable_openai_runtime(exc)
            merged = "\n".join(parts[:5])
            return merged, [part[:180] for part in parts[:5]]

    def _fetch_forum_evidence(self, item: LibraryItemEntry) -> list[EvidenceRecord]:
        query = item.effective_title
        evidence: list[EvidenceRecord] = []
        sources = self._active_forum_sources()
        if "openreview" in sources:
            evidence.extend(self._openreview_evidence(item.id, query))
        if "github" in sources:
            evidence.extend(self._github_evidence(item.id, query))
        if "reddit" in sources:
            evidence.extend(self._reddit_evidence(item.id, query))
        if "huggingface" in sources:
            evidence.extend(self._huggingface_evidence(item.id, query))
        filtered: list[EvidenceRecord] = []
        for record in evidence:
            threshold = self._source_confidence_threshold(record.source_type)
            confidence = record.confidence_score or record.relevance_score or 0.0
            if confidence < threshold:
                continue
            metadata = dict(record.metadata)
            metadata.setdefault("forum_source_profile", self.settings.forum_source_profile)
            record.metadata = metadata
            filtered.append(record)
        filtered.sort(key=lambda item: (item.confidence_score or item.relevance_score or 0.0), reverse=True)
        return filtered[:10]

    def _active_forum_sources(self) -> list[str]:
        configured = {part.strip().lower() for part in self.settings.forum_sources.split(",") if part.strip()}
        profile_allowlist = {
            "high_trust": {"openreview", "github"},
            "extended": {"openreview", "github", "reddit"},
            "experimental": {"openreview", "github", "reddit", "huggingface"},
        }.get(self.settings.forum_source_profile, {"openreview", "github"})
        active = configured & profile_allowlist
        if not active:
            active = profile_allowlist
        return sorted(active)

    def _source_confidence_threshold(self, source_type: str) -> float:
        thresholds = {
            "openreview": 0.45,
            "github": 0.5,
            "reddit": 0.7,
            "huggingface": 0.65,
        }
        return thresholds.get(source_type, 0.5)

    def _disable_openai_runtime(self, exc: Exception) -> None:
        self._openai_disabled_reason = str(exc)

    def _openreview_evidence(self, item_id: str, query: str) -> list[EvidenceRecord]:
        url = f"https://openreview.net/search?term={quote_plus(query)}"
        try:
            response = self._http.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.select("a[href*='/forum?id=']")[:3]
            out = []
            for idx, link in enumerate(links, start=1):
                title = link.get_text(" ", strip=True) or query
                score = max(0.0, min(1.0, 0.55 + _token_overlap(query, title) * 0.4 - idx * 0.05))
                out.append(
                    EvidenceRecord(
                        id=f"{item_id}_openreview_{idx}",
                        item_id=item_id,
                        source_type="openreview",
                        title=title,
                        url=f"https://openreview.net{link.get('href')}",
                        excerpt="OpenReview forum result",
                        relevance_score=score,
                        confidence_score=score,
                        metadata={"source_weight": 0.9, "match_overlap": round(_token_overlap(query, title), 3)},
                    )
                )
            return out
        except Exception:
            return []

    def _github_evidence(self, item_id: str, query: str) -> list[EvidenceRecord]:
        url = f"https://github.com/search?q={quote_plus(query)}&type=issues"
        try:
            response = self._http.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.select("a.v-align-middle")[:5]
            out = []
            for idx, link in enumerate(links, start=1):
                href = link.get("href")
                title = link.get_text(" ", strip=True)
                if not href or _token_overlap(query, title) < 0.35:
                    continue
                score = max(0.0, min(1.0, 0.45 + _token_overlap(query, title) * 0.5 - idx * 0.05))
                out.append(
                    EvidenceRecord(
                        id=f"{item_id}_github_{idx}",
                        item_id=item_id,
                        source_type="github",
                        title=title,
                        url=f"https://github.com{href}",
                        excerpt="GitHub issue/discussion search result",
                        relevance_score=score,
                        confidence_score=score,
                        metadata={"source_weight": 0.7, "match_overlap": round(_token_overlap(query, title), 3)},
                    )
                )
            return out
        except Exception:
            return []

    def _reddit_evidence(self, item_id: str, query: str) -> list[EvidenceRecord]:
        quoted_query = f'"{query}"'
        url = f"https://www.reddit.com/search.json?q={quote_plus(quoted_query)}&limit=6&sort=relevance"
        try:
            response = self._http.get(url, headers={"User-Agent": self.settings.user_agent})
            response.raise_for_status()
            data = response.json()
            children = data.get("data", {}).get("children", [])[:6]
            out = []
            for idx, child in enumerate(children, start=1):
                title = child.get("data", {}).get("title") or ""
                excerpt = child.get("data", {}).get("selftext", "")[:240]
                overlap = _token_overlap(query, f"{title} {excerpt}")
                if overlap < 0.4:
                    continue
                score = max(0.0, min(1.0, 0.2 + overlap * 0.6 - idx * 0.05))
                out.append(
                    EvidenceRecord(
                        id=f"{item_id}_reddit_{idx}",
                        item_id=item_id,
                        source_type="reddit",
                        title=title,
                        url=f"https://www.reddit.com{child.get('data', {}).get('permalink', '')}",
                        excerpt=excerpt,
                        relevance_score=score,
                        confidence_score=score,
                        metadata={"source_weight": 0.35, "match_overlap": round(overlap, 3)},
                    )
                )
            return out
        except Exception:
            return []

    def _huggingface_evidence(self, item_id: str, query: str) -> list[EvidenceRecord]:
        return []

    def _effective_backend(self) -> str:
        if self.settings.compute_backend == "openai" and self._openai is not None and self._openai_disabled_reason is None:
            return "openai"
        if (
            self.settings.compute_backend == "auto"
            and self._openai is not None
            and self._openai_disabled_reason is None
            and self.settings.analysis_mode in {"hybrid", "semantic_heavy"}
        ):
            return "openai"
        if self._should_embed() and self._local_embedder.is_configured():
            return "local_transformer"
        if self._should_embed():
            return "local_heuristic"
        return "local"

    def _semantic_backend_label(self) -> str:
        if not self._should_embed():
            return "disabled"
        if self._effective_backend() == "openai":
            return "openai"
        if self._effective_backend() == "local_transformer":
            if self._local_reranker.is_configured():
                return "local_transformer+reranker"
            return "local_transformer"
        return "local_heuristic"

    def _persist_report(
        self,
        *,
        analysis_kind: str,
        title: str,
        summary: str,
        key_points: list[str],
        evidence: list[EvidenceRecord],
        library_id: str | None = None,
        item_id: str | None = None,
        topic: str | None = None,
        structured_payload: dict[str, Any] | None = None,
    ) -> AnalysisReportSummary:
        now = now_utc_iso()
        report_id = slugify(f"{analysis_kind}-{title}-{now}", max_length=48)
        root = self.analysis_root / (library_id or "global") / "reports"
        root.mkdir(parents=True, exist_ok=True)
        report_path = root / f"{report_id}.md"
        report_json_path = root / f"{report_id}.json"
        lines = [f"# {title}", "", summary, "", "## Key points"]
        for point in key_points:
            lines.append(f"- {point}")
        if evidence:
            lines.extend(["", "## Evidence"])
            for ev in evidence[:10]:
                lines.append(f"- [{ev.source_type}] {ev.title or ev.url or ev.excerpt or ''}")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report_json_path.write_text(
            json.dumps(
                {
                    "title": title,
                    "summary": summary,
                    "key_points": key_points,
                    "evidence": [ev.model_dump(mode="json") for ev in evidence],
                    "structured_payload": structured_payload or {},
                    "analysis_kind": analysis_kind,
                    "library_id": library_id,
                    "item_id": item_id,
                    "topic": topic,
                    "analysis_mode": self.settings.analysis_mode,
                    "compute_backend": self._effective_backend(),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO analysis_reports(
                    id, library_id, item_id, analysis_kind, topic, title, analysis_mode,
                    compute_backend, summary, key_points_json, evidence_json, structured_payload_json, report_path,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    library_id,
                    item_id,
                    analysis_kind,
                    topic,
                    title,
                    self.settings.analysis_mode,
                    self._effective_backend(),
                    summary,
                    json.dumps(key_points, ensure_ascii=False),
                    json.dumps([ev.model_dump(mode="json") for ev in evidence], ensure_ascii=False),
                    json.dumps(structured_payload or {}, ensure_ascii=False),
                    str(report_path),
                    now,
                    now,
                ),
            )
        return AnalysisReportSummary(
            id=report_id,
            library_id=library_id,
            item_id=item_id,
            analysis_kind=analysis_kind,
            topic=topic,
            title=title,
            analysis_mode=self.settings.analysis_mode,
            compute_backend=self._effective_backend(),
            report_path=str(report_path),
            created_at=now,
            updated_at=now,
        )

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    def _report_summary_from_row(self, row: sqlite3.Row) -> AnalysisReportSummary:
        return AnalysisReportSummary(
            id=row["id"],
            library_id=row["library_id"],
            item_id=row["item_id"],
            analysis_kind=row["analysis_kind"],
            topic=row["topic"],
            title=row["title"],
            analysis_mode=row["analysis_mode"],
            compute_backend=row["compute_backend"],
            report_path=row["report_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _sentence_split(text: str) -> list[str]:
    return [part.strip() for part in text.replace("\n", " ").split(". ") if part.strip()]


def _extract_key_points(sentences: list[str], *, topic: str | None) -> list[str]:
    preferred = []
    markers = ["we propose", "we introduce", "calibration", "coverage", "posterior", "misspecification", "diagnostic", "result", "limitation", "conclusion"]
    if topic:
        markers.extend(topic.lower().split())
    for sentence in sentences:
        lower = sentence.lower()
        if any(marker in lower for marker in markers):
            preferred.append(sentence)
    return preferred[:8] or sentences[:6]


def _pick_sentence(sentences: list[str], markers: list[str], *, fallback: str) -> str:
    lowered_markers = [marker.lower() for marker in markers if marker]
    for sentence in sentences:
        lower = sentence.lower()
        if any(marker in lower for marker in lowered_markers):
            return sentence.strip()
    return fallback


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _infer_section(text: str) -> str:
    start = text[:160].lower()
    if "abstract" in start:
        return "abstract"
    if "introduction" in start:
        return "introduction"
    if "method" in start or "approach" in start:
        return "method"
    if "result" in start:
        return "results"
    if "conclusion" in start:
        return "conclusion"
    return "body"


def _unique_chunks(chunks: list[ChunkRecord]) -> list[ChunkRecord]:
    seen = set()
    out = []
    for chunk in chunks:
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        out.append(chunk)
    return out


def _token_overlap(query: str, text: str) -> float:
    q = {token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 3}
    t = {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 3}
    if not q:
        return 0.0
    return len(q & t) / len(q)


def _local_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for token in tokens:
        if not token:
            continue
        index = hash(token) % dim
        vec[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vec))
    if norm == 0:
        return vec
    return [value / norm for value in vec]
