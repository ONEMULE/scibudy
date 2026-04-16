from pathlib import Path

import httpx

from research_mcp.library import LibraryManager, response_to_results
from research_mcp.models import LiteratureResult, SearchResponse
from research_mcp.settings import Settings


class StubResolver:
    def resolve(self, doi: str):
        raise AssertionError(f"unexpected resolver call for {doi}")


def test_download_and_organize_library(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com/paper.pdf":
            return httpx.Response(200, content=b"%PDF-1.4 test", headers={"content-type": "application/pdf"})
        return httpx.Response(404, text="missing")

    manager = LibraryManager(
        Settings(RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db")),
        oa_resolver=StubResolver(),
        transport=httpx.MockTransport(handler),
    )
    result = LiteratureResult(
        title="Simulation Based Calibration",
        authors=["A. Author"],
        year=2024,
        doi="10.1000/example",
        source="OpenAlex",
        source_id="W1",
        landing_url="https://example.com/paper",
        pdf_url="https://example.com/paper.pdf",
        open_access_url="https://example.com/paper.pdf",
        extras={"rank": 1},
    )

    batch = manager.download_pdfs(results=[result], target_dir=tmp_path / "downloads", limit=1, source_kind="run", source_ref="latest")
    assert batch.status == "ok"
    assert batch.downloaded_count == 1
    assert Path(batch.records[0].local_pdf_path).exists()

    organized = manager.organize_library(results=[result], target_dir=tmp_path / "library", limit=1, source_kind="query", source_ref="sbc", download_pdfs=True)
    assert organized.status == "ok"
    assert Path(organized.csv_path).exists()
    assert Path(organized.markdown_path).exists()
    assert Path(organized.bibtex_path).exists()
    assert Path(organized.manifest_path).exists()
    checklist_text = Path(organized.download_checklist_markdown_path).read_text(encoding="utf-8")
    assert "Status" in checklist_text
    assert "Message" in checklist_text


def test_failed_pdf_download_records_manual_checklist_reason(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not a pdf</html>", headers={"content-type": "text/html"})

    manager = LibraryManager(
        Settings(RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db")),
        oa_resolver=StubResolver(),
        transport=httpx.MockTransport(handler),
    )
    result = LiteratureResult(
        title="Manual Paper",
        source="CORE",
        source_id="C1",
        landing_url="https://example.com/manual",
        pdf_url="https://example.com/manual",
        extras={"rank": 1},
    )

    organized = manager.organize_library(results=[result], target_dir=tmp_path / "library-failed", limit=1, source_kind="query", source_ref="manual", download_pdfs=True)

    assert organized.status == "error"
    assert organized.records[0].status == "skipped"
    checklist = Path(organized.download_checklist_csv_path).read_text(encoding="utf-8")
    assert "download_message" in checklist
    assert "no usable PDF URL found" in checklist


def test_response_to_results_adds_rank():
    response = SearchResponse(
        query="q",
        mode="general",
        sort="relevance",
        generated_at="2026-01-01T00:00:00+00:00",
        result_count=1,
        provider_coverage=[],
        results=[LiteratureResult(title="A", source="OpenAlex")],
    )

    results = response_to_results(response)

    assert results[0].extras["rank"] == 1
