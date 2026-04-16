from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import httpx

from research_mcp.models import DownloadBatchResponse, DownloadRecord, LiteratureResult, OpenAccessResponse, OrganizeLibraryResponse, SearchResponse
from research_mcp.paths import LIBRARY_DIR
from research_mcp.runstore import load_run
from research_mcp.settings import Settings
from research_mcp.utils import canonical_doi, normalize_whitespace, now_utc_iso


class LibraryManager:
    def __init__(
        self,
        settings: Settings,
        *,
        oa_resolver=None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.oa_resolver = oa_resolver
        self._client = httpx.Client(
            timeout=max(settings.request_timeout_sec * 2, 30.0),
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def download_pdfs(
        self,
        *,
        results: list[LiteratureResult],
        target_dir: str | Path | None = None,
        limit: int | None = None,
        source_kind: str,
        source_ref: str,
    ) -> DownloadBatchResponse:
        root = Path(target_dir or (LIBRARY_DIR / "downloads")).expanduser().resolve()
        pdf_dir = root / "pdfs"
        metadata_dir = root / "metadata"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        selected = results[: limit or len(results)]
        records: list[DownloadRecord] = []
        warnings: list[str] = []
        downloaded_count = 0

        for index, result in enumerate(selected, start=1):
            rank = self._extract_rank(result, index)
            metadata_path = metadata_dir / f"{rank:03d}-{self._slug(result)}.json"
            metadata_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
            record = DownloadRecord(
                rank=rank,
                title=result.title,
                doi=result.doi,
                source=result.source,
                landing_url=result.landing_url,
                local_metadata_path=str(metadata_path),
                status="skipped",
                message="no usable PDF URL found",
            )

            candidates = self._candidate_urls(result)
            record.attempted_urls = candidates.copy()
            if not candidates:
                records.append(record)
                continue

            pdf_path = pdf_dir / f"{rank:03d}-{self._slug(result)}.pdf"
            for url in candidates:
                try:
                    if self._download_url(url, pdf_path):
                        record.selected_url = url
                        record.local_pdf_path = str(pdf_path)
                        record.status = "downloaded"
                        record.message = None
                        downloaded_count += 1
                        break
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{result.title or result.doi or rank}: {exc}")
                    record.status = "error"
                    record.message = str(exc)
                    record.selected_url = url
            records.append(record)

        status = "ok" if downloaded_count == len(selected) else ("error" if downloaded_count == 0 and selected else "partial")
        return DownloadBatchResponse(
            status=status,
            generated_at=now_utc_iso(),
            target_dir=str(root),
            source_kind=source_kind,
            source_ref=source_ref,
            requested_count=len(selected),
            processed_count=len(records),
            downloaded_count=downloaded_count,
            records=records,
            warnings=list(dict.fromkeys(warnings)),
        )

    def organize_library(
        self,
        *,
        results: list[LiteratureResult],
        target_dir: str | Path | None = None,
        limit: int | None = None,
        source_kind: str,
        source_ref: str,
        download_pdfs: bool = False,
    ) -> OrganizeLibraryResponse:
        root = Path(target_dir or (LIBRARY_DIR / "library")).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        selected = results[: limit or len(results)]

        batch = self.download_pdfs(
            results=selected,
            target_dir=root,
            limit=len(selected),
            source_kind=source_kind,
            source_ref=source_ref,
        ) if download_pdfs else DownloadBatchResponse(
            status="ok",
            generated_at=now_utc_iso(),
            target_dir=str(root),
            source_kind=source_kind,
            source_ref=source_ref,
            requested_count=len(selected),
            processed_count=0,
            downloaded_count=0,
            records=[
                DownloadRecord(
                    rank=self._extract_rank(item, idx),
                    title=item.title,
                    doi=item.doi,
                    source=item.source,
                    landing_url=item.landing_url,
                    status="skipped",
                    message="download skipped",
                )
                for idx, item in enumerate(selected, start=1)
            ],
            warnings=[],
        )

        manifest_path = root / "manifest.json"
        csv_path = root / "library.csv"
        markdown_path = root / "README.md"
        bibtex_path = root / "library.bib"
        checklist_csv_path = root / "download_checklist.csv"
        checklist_markdown_path = root / "download_checklist.md"

        record_map = {record.rank: record for record in batch.records if record.rank is not None}
        rows = []
        checklist_rows = []
        markdown_lines = [
            "# Research Library",
            "",
            f"Source: `{source_kind}`",
            f"Reference: `{source_ref}`",
            f"Generated at: `{now_utc_iso()}`",
            f"PDF download mode: `{'enabled' if download_pdfs else 'manual checklist only'}`",
            "",
            "| Rank | Year | Source | Download | Title | DOI |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        checklist_lines = [
            "# Manual Download Checklist",
            "",
            f"Source: `{source_kind}`",
            f"Reference: `{source_ref}`",
            "",
            "| Rank | Title | Manual download URL | Landing URL | DOI | Status | Message |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        bib_entries = []

        for index, result in enumerate(selected, start=1):
            rank = self._extract_rank(result, index)
            record = record_map.get(rank)
            candidates = record.attempted_urls if record and record.attempted_urls else self._candidate_urls(result)
            manual_url = record.selected_url if record and record.selected_url else (candidates[0] if candidates else "")
            row = {
                "rank": rank,
                "title": result.title or "",
                "year": result.year or "",
                "source": result.source,
                "authors": "; ".join(result.authors),
                "doi": result.doi or "",
                "landing_url": result.landing_url or "",
                "pdf_url": result.pdf_url or "",
                "open_access_url": result.open_access_url or "",
                "local_pdf_path": record.local_pdf_path if record else "",
                "download_status": record.status if record else "",
                "category": str(result.extras.get("category") or result.extras.get("type") or ""),
                "notes": str(result.extras.get("why_high_value") or result.extras.get("why") or ""),
            }
            rows.append(row)
            checklist_row = {
                "rank": rank,
                "title": result.title or "",
                "source": result.source,
                "manual_download_url": manual_url,
                "landing_url": result.landing_url or "",
                "pdf_url": result.pdf_url or "",
                "open_access_url": result.open_access_url or "",
                "doi": result.doi or "",
                "candidate_urls": " | ".join(candidates),
                "download_status": record.status if record else "",
                "download_message": record.message if record and record.message else "",
            }
            checklist_rows.append(checklist_row)
            download_text = "yes" if row["local_pdf_path"] else (record.status if record else "")
            markdown_lines.append(
                f"| {rank} | {row['year']} | {row['source']} | {download_text} | {row['title']} | {row['doi']} |"
            )
            checklist_lines.append(
                f"| {rank} | {row['title']} | {manual_url} | {row['landing_url']} | {row['doi']} | {checklist_row['download_status']} | {checklist_row['download_message']} |"
            )
            bib_entries.append(self._bibtex_entry(result, rank))

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["rank", "title"])
            writer.writeheader()
            writer.writerows(rows)

        markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
        bibtex_path.write_text("\n\n".join(entry for entry in bib_entries if entry) + ("\n" if bib_entries else ""), encoding="utf-8")
        with checklist_csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(checklist_rows[0].keys()) if checklist_rows else ["rank", "title", "manual_download_url"])
            writer.writeheader()
            writer.writerows(checklist_rows)
        checklist_markdown_path.write_text("\n".join(checklist_lines) + "\n", encoding="utf-8")
        manifest = {
            "generated_at": now_utc_iso(),
            "source_kind": source_kind,
            "source_ref": source_ref,
            "requested_count": len(selected),
            "downloaded_count": batch.downloaded_count,
            "status": batch.status if download_pdfs else "ok",
            "files": {
                "csv": str(csv_path),
                "markdown": str(markdown_path),
                "bibtex": str(bibtex_path),
                "download_checklist_csv": str(checklist_csv_path),
                "download_checklist_markdown": str(checklist_markdown_path),
            },
            "records": [record.model_dump(mode="json") for record in batch.records],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        return OrganizeLibraryResponse(
            status=batch.status if download_pdfs else "ok",
            generated_at=now_utc_iso(),
            target_dir=str(root),
            source_kind=source_kind,
            source_ref=source_ref,
            requested_count=len(selected),
            processed_count=len(batch.records),
            downloaded_count=batch.downloaded_count,
            manifest_path=str(manifest_path),
            csv_path=str(csv_path),
            markdown_path=str(markdown_path),
            bibtex_path=str(bibtex_path),
            download_checklist_csv_path=str(checklist_csv_path),
            download_checklist_markdown_path=str(checklist_markdown_path),
            records=batch.records,
            warnings=batch.warnings,
        )

    def load_results(
        self,
        *,
        run_id: str | None = None,
        csv_path: str | Path | None = None,
    ) -> tuple[list[LiteratureResult], str, str]:
        if csv_path:
            path = Path(csv_path).expanduser().resolve()
            return self._load_results_from_csv(path), "csv", str(path)
        document = load_run(run_id or "latest")
        payload = document.get("payload") or {}
        results = [self._from_dict(item, rank=index) for index, item in enumerate(payload.get("results") or [], start=1)]
        source_ref = document.get("summary", {}).get("query") or document.get("summary", {}).get("doi") or (run_id or "latest")
        return results, "run", str(source_ref)

    def _load_results_from_csv(self, path: Path) -> list[LiteratureResult]:
        results: list[LiteratureResult] = []
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                results.append(
                    LiteratureResult(
                        title=normalize_whitespace(row.get("title")),
                        authors=[part.strip() for part in (row.get("authors") or "").split(";") if part.strip()],
                        year=int(row["year"]) if row.get("year") and str(row.get("year")).isdigit() else None,
                        doi=canonical_doi(row.get("doi")),
                        source=row.get("venue_or_source") or row.get("source") or "unknown",
                        source_id=row.get("rank") or str(index),
                        landing_url=normalize_whitespace(row.get("url")),
                        pdf_url=normalize_whitespace(row.get("pdf_url")),
                        open_access_url=normalize_whitespace(row.get("oa_url") or row.get("open_access_url")),
                        extras={
                            "rank": int(row["rank"]) if row.get("rank") and str(row.get("rank")).isdigit() else index,
                            "category": row.get("category"),
                            "why_high_value": row.get("why_high_value"),
                        },
                    )
                )
        return results

    def _from_dict(self, payload: dict[str, Any], *, rank: int) -> LiteratureResult:
        result = LiteratureResult.model_validate(payload)
        result.extras = {**result.extras, "rank": rank}
        return result

    def _candidate_urls(self, result: LiteratureResult) -> list[str]:
        candidates: list[str] = []
        for url in [result.pdf_url, self._resolved_pdf_url(result), self._resolved_best_url(result), result.open_access_url, result.landing_url]:
            if url and url not in candidates:
                candidates.append(url)
        return candidates

    def _resolved_pdf_url(self, result: LiteratureResult) -> str | None:
        if not result.doi or self.oa_resolver is None:
            return None
        try:
            response = self.oa_resolver.resolve(result.doi)
            if isinstance(response, OpenAccessResponse):
                return response.pdf_url
        except Exception:  # noqa: BLE001
            return None
        return None

    def _resolved_best_url(self, result: LiteratureResult) -> str | None:
        if not result.doi or self.oa_resolver is None:
            return None
        try:
            response = self.oa_resolver.resolve(result.doi)
            if isinstance(response, OpenAccessResponse):
                return response.best_url
        except Exception:  # noqa: BLE001
            return None
        return None

    def _download_url(self, url: str, destination: Path) -> bool:
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
            content_type = (response.headers.get("content-type") or "").lower()
        try:
            header = destination.read_bytes()[:4]
        except FileNotFoundError:
            return False
        if "pdf" in content_type or header == b"%PDF":
            return True
        destination.unlink(missing_ok=True)
        return False

    def _extract_rank(self, result: LiteratureResult, fallback: int) -> int:
        raw = result.extras.get("rank")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return fallback

    def _slug(self, result: LiteratureResult) -> str:
        title = result.title or result.doi or result.source_id or "paper"
        compact = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
        return compact[:80] or "paper"

    def _bibtex_entry(self, result: LiteratureResult, rank: int) -> str:
        title = (result.title or "").strip()
        if not title:
            return ""
        key = canonical_doi(result.doi) or f"{self._slug(result)}-{rank}"
        key = re.sub(r"[^a-zA-Z0-9:_-]+", "_", key)
        authors = " and ".join(result.authors) if result.authors else ""
        year = str(result.year or "")
        journal = (result.journal or result.source or "").replace("{", "").replace("}", "")
        fields = [
            f"  title = {{{title}}}",
            f"  author = {{{authors}}}" if authors else "",
            f"  year = {{{year}}}" if year else "",
            f"  journal = {{{journal}}}" if journal else "",
            f"  doi = {{{result.doi}}}" if result.doi else "",
            f"  url = {{{result.landing_url or result.open_access_url or result.pdf_url or ''}}}" if (result.landing_url or result.open_access_url or result.pdf_url) else "",
        ]
        fields = [field for field in fields if field]
        return "@article{" + key + ",\n" + ",\n".join(fields) + "\n}"


def response_to_results(response: SearchResponse) -> list[LiteratureResult]:
    results = []
    for index, item in enumerate(response.results, start=1):
        clone = item.model_copy(deep=True)
        clone.extras = {**clone.extras, "rank": index}
        results.append(clone)
    return results
