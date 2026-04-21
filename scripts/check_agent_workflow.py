from __future__ import annotations

import tempfile
from pathlib import Path

from research_mcp.models import LiteratureResult
from research_mcp.service import ResearchService
from research_mcp.settings import Settings


class StubProvider:
    name = "OpenAlex"

    def ready(self):
        return True, None

    def search(self, query: str, limit: int, sort: str):
        return [
            LiteratureResult(
                title="Agent workflow smoke paper",
                source=self.name,
                source_id="W-smoke",
                year=2026,
                landing_url="https://example.com/smoke",
            )
        ]


class StubResolver:
    name = "Unpaywall"
    required_settings = ()

    def ready(self):
        return True, None


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scibudy-agent-workflow-") as tmp:
        root = Path(tmp)
        settings = Settings(RESEARCH_MCP_CACHE_DB_PATH=str(root / "state.db"))
        service = ResearchService(
            settings=settings,
            providers={"openalex": StubProvider()},
            oa_resolver=StubResolver(),
        )
        response = service.research_workflow(
            query="agent workflow smoke",
            mode="general",
            limit=1,
            target_dir=str(root / "library"),
            download_pdfs=False,
            ingest=False,
            synthesize=True,
        )
        assert response.status == "partial"
        assert response.library_id
        assert response.paths.get("download_checklist_markdown")
        assert any("ingest_library" in action for action in response.next_actions)
        assert response.metrics["total_elapsed_ms"] >= 0

        dry_run_target = root / "dry-run-library"
        dry_run = service.research_workflow(
            query="agent workflow smoke",
            mode="general",
            limit=1,
            target_dir=str(dry_run_target),
            dry_run=True,
        )
        assert dry_run.status == "ok"
        assert dry_run.workflow_stage == "planned"
        assert not dry_run_target.exists()

        fast = service.research_workflow(
            query="agent workflow smoke",
            mode="general",
            limit=1,
            target_dir=str(root / "fast-library"),
            download_pdfs=False,
            quality_mode="fast",
        )
        assert fast.workflow_stage == "organized"
        assert fast.ingest_status == "skipped"
        security = service.security_check()
        assert security.status in {"ok", "warning"}
        print("agent-workflow-smoke: ok")


if __name__ == "__main__":
    main()
