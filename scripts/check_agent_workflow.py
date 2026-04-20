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
        print("agent-workflow-smoke: ok")


if __name__ == "__main__":
    main()
