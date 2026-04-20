import httpx

from research_mcp.analysis_engine import AnalysisEngine
from research_mcp.models import LibraryDetailResponse, LibraryItemEntry, LibrarySummary
from research_mcp.settings import Settings


def test_ingest_and_summarize_html_item(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com/paper":
            html = """
            <html><body>
            <h1>Simulation Based Calibration</h1>
            <p>Abstract. We introduce a simulation-based calibration diagnostic for posterior algorithms.</p>
            <p>Methods. The method evaluates coverage and posterior rank behavior under repeated simulation.</p>
            <p>Results. The diagnostic reveals biased posterior approximations and autocorrelation issues.</p>
            <p>Conclusion. SBC is a practical calibration workflow for Bayesian computation.</p>
            </body></html>
            """
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        return httpx.Response(404, text="missing")

    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="rules",
        RESEARCH_MCP_COMPUTE_BACKEND="local",
        RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED="false",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db", transport=httpx.MockTransport(handler))
    item = LibraryItemEntry(
        id="item1",
        library_id="lib1",
        rank=1,
        title="Simulation Based Calibration",
        effective_title="Simulation Based Calibration",
        authors=["A. Author"],
        source="OpenAlex",
        landing_url="https://example.com/paper",
    )

    ingest = engine.ingest_item("lib1", item, include_forums=False, reingest=True)
    assert ingest.extraction_status == "ready"
    assert ingest.chunk_count >= 1

    summary = engine.summarize_item(item, topic="calibration")
    assert summary.status == "ok"
    assert "calibration" in summary.summary.lower() or any("calibration" in point.lower() for point in summary.key_points)


def test_forum_source_profile_filters_to_high_trust(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/paper":
            return httpx.Response(
                200,
                text="""
                <html><body>
                <h1>Simulation Based Calibration</h1>
                <p>Abstract. We introduce a simulation-based calibration diagnostic for posterior algorithms.</p>
                <p>Methods. The method evaluates coverage and posterior rank behavior under repeated simulation.</p>
                </body></html>
                """,
                headers={"content-type": "text/html"},
            )
        if "openreview.net/search" in url:
            return httpx.Response(200, text='<a href="/forum?id=abc">Simulation Based Calibration Review</a>')
        if "github.com/search" in url:
            return httpx.Response(200, text='<a class="v-align-middle" href="/org/repo/issues/1">Simulation Based Calibration issue</a>')
        if "reddit.com/search.json" in url:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "children": [
                            {
                                "data": {
                                    "title": "Simulation Based Calibration reddit thread",
                                    "selftext": "Discussion text",
                                    "permalink": "/r/test/comments/1",
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404, text="missing")

    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="hybrid",
        RESEARCH_MCP_COMPUTE_BACKEND="local",
        RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED="true",
        RESEARCH_MCP_FORUM_SOURCE_PROFILE="high_trust",
        RESEARCH_MCP_FORUM_SOURCES="openreview,github,reddit",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db", transport=httpx.MockTransport(handler))
    item = LibraryItemEntry(
        id="item1",
        library_id="lib1",
        rank=1,
        title="Simulation Based Calibration",
        effective_title="Simulation Based Calibration",
        authors=["A. Author"],
        source="OpenAlex",
        landing_url="https://example.com/paper",
    )

    ingest = engine.ingest_item("lib1", item, include_forums=True, reingest=True)
    assert ingest.extraction_status == "ready"
    evidence = engine._load_discussion_for_item("item1")
    assert evidence
    assert {record.source_type for record in evidence} <= {"openreview", "github"}


def test_search_library_evidence_includes_scores_and_report_id(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com/paper":
            return httpx.Response(
                200,
                text="""
                <html><body>
                <h1>Simulation Based Calibration</h1>
                <p>Abstract. We introduce simulation-based calibration diagnostics for posterior approximations.</p>
                <p>Methods. Coverage and rank statistics reveal calibration failures under repeated simulation.</p>
                <p>Limitations. Diagnostics can miss some model mismatch pathologies.</p>
                </body></html>
                """,
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404, text="missing")

    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="hybrid",
        RESEARCH_MCP_COMPUTE_BACKEND="local",
        RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED="false",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db", transport=httpx.MockTransport(handler))
    item = LibraryItemEntry(
        id="item1",
        library_id="lib1",
        rank=1,
        title="Simulation Based Calibration",
        effective_title="Simulation Based Calibration",
        authors=["A. Author"],
        source="OpenAlex",
        landing_url="https://example.com/paper",
    )
    engine.ingest_item("lib1", item, include_forums=False, reingest=True)
    detail = LibraryDetailResponse(
        status="ok",
        generated_at="now",
        library=LibrarySummary(
            id="lib1",
            name="Test library",
            slug="test-library",
            source_kind="run",
            source_ref="latest",
            root_path=str(tmp_path / "library"),
            created_at="now",
            updated_at="now",
        ),
        items=[item],
    )

    response = engine.search_library_evidence(detail, query="calibration", max_hits=3)

    assert response.status == "ok"
    assert response.report_id
    assert response.evidence
    metadata = response.evidence[0].metadata
    assert "lexical_score" in metadata
    assert "semantic_score" in metadata
    assert "semantic_backend" in metadata
    assert metadata.get("report_id") == response.report_id


def test_build_research_synthesis_persists_structured_payload(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        pages = {
            "https://example.com/sbc": """
                <html><body>
                <h1>Simulation Based Calibration</h1>
                <p>Abstract. We introduce simulation-based calibration diagnostics for posterior approximations.</p>
                <p>Methods. The method evaluates coverage and rank statistics under repeated simulation.</p>
                <p>Limitations. Diagnostics can miss model misspecification and correlated simulation failures.</p>
                <p>Conclusion. SBC is a practical workflow for validating posterior calibration.</p>
                </body></html>
            """,
            "https://example.com/npe": """
                <html><body>
                <h1>Neural Posterior Estimation Calibration</h1>
                <p>Abstract. Neural posterior estimation needs calibration checks for amortized inference.</p>
                <p>Methods. We propose coverage tests and posterior predictive simulation protocols.</p>
                <p>Assumptions. The simulator and prior must represent the deployment setting.</p>
                <p>Failure modes include biased posteriors, simulation mismatch, and poor tail coverage.</p>
                </body></html>
            """,
        }
        if str(request.url) in pages:
            return httpx.Response(200, text=pages[str(request.url)], headers={"content-type": "text/html"})
        return httpx.Response(404, text="missing")

    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="hybrid",
        RESEARCH_MCP_COMPUTE_BACKEND="local",
        RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED="false",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db", transport=httpx.MockTransport(handler))
    items = [
        LibraryItemEntry(
            id="item1",
            library_id="lib1",
            rank=1,
            title="Simulation Based Calibration",
            effective_title="Simulation Based Calibration",
            authors=["A. Author"],
            source="OpenAlex",
            landing_url="https://example.com/sbc",
        ),
        LibraryItemEntry(
            id="item2",
            library_id="lib1",
            rank=2,
            title="Neural Posterior Estimation Calibration",
            effective_title="Neural Posterior Estimation Calibration",
            authors=["B. Author"],
            source="Semantic Scholar",
            landing_url="https://example.com/npe",
        ),
    ]
    for item in items:
        assert engine.ingest_item("lib1", item, include_forums=False, reingest=True).extraction_status == "ready"
    detail = LibraryDetailResponse(
        status="ok",
        generated_at="now",
        library=LibrarySummary(
            id="lib1",
            name="SBI calibration",
            slug="sbi-calibration",
            source_kind="query",
            source_ref="calibration",
            root_path=str(tmp_path / "library"),
            created_at="now",
            updated_at="now",
        ),
        items=items,
    )

    response = engine.build_research_synthesis(detail, topic="calibration in simulation-based inference", max_items=50)

    assert response.status == "ok"
    payload = response.structured_payload
    assert payload["schema_version"] == "research_synthesis.v1"
    assert payload["requested_profile"] == "auto"
    assert payload["resolved_profile"] == "sbi_calibration"
    assert payload["profile_source"] == "auto"
    assert payload["profile"] == "sbi_calibration"
    assert payload["analyzed_item_count"] == 2
    assert payload["evidence_coverage"]["evidence_backed_item_count"] == 2
    assert payload["missing_fulltext_count"] == 0
    assert payload["confidence"] > 0.5
    assert len(payload["method_cards"]) == 2
    assert payload["comparison_matrix"]
    assert payload["claim_evidence_graph"]["claims"]
    assert any(claim["support_status"] == "supported" for claim in payload["claim_evidence_graph"]["claims"])
    assert payload["calibration_protocol_digest"]["protocol_steps"]

    report = engine.read_report(response.report_id)
    assert report.status == "ok"
    assert report.structured_payload["schema_version"] == "research_synthesis.v1"


def test_general_profile_stays_general_for_non_sbi_topic(tmp_path):
    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="rules",
        RESEARCH_MCP_COMPUTE_BACKEND="local",
        RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED="false",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db")
    item = LibraryItemEntry(
        id="item1",
        library_id="lib1",
        rank=1,
        title="Causal Inference Robustness",
        effective_title="Causal Inference Robustness",
        authors=[],
        source="OpenAlex",
    )
    text_path = engine._write_text("lib1", "item1", "Methods. We compare robustness checks for causal inference. Results. Sensitivity analysis reveals limitations.")
    engine._store_ingest(
        item=item,
        library_id="lib1",
        source_label="test",
        text_path=text_path,
        chunks=engine._chunk_text("item1", text_path.read_text(encoding="utf-8")),
        discussion=[],
    )
    detail = LibraryDetailResponse(
        status="ok",
        generated_at="now",
        library=LibrarySummary(
            id="lib1",
            name="General library",
            slug="general-library",
            source_kind="query",
            source_ref="causal inference",
            root_path=str(tmp_path / "library"),
            created_at="now",
            updated_at="now",
        ),
        items=[item],
    )

    response = engine.build_research_synthesis(detail, topic="causal inference robustness", profile="auto")

    assert response.structured_payload["requested_profile"] == "auto"
    assert response.structured_payload["resolved_profile"] == "general"
    assert response.structured_payload["profile_source"] == "auto"


def test_build_research_synthesis_tracks_missing_fulltext_and_unsupported_claims(tmp_path):
    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="rules",
        RESEARCH_MCP_COMPUTE_BACKEND="local",
        RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED="false",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db")
    chunks = engine._chunk_text("item1", "Abstract\n\nCalibration is useful but details are sparse.")
    engine._store_ingest(
        item=LibraryItemEntry(
            id="item1",
            library_id="lib1",
            rank=1,
            title="Sparse Calibration Paper",
            effective_title="Sparse Calibration Paper",
            authors=[],
            source="OpenAlex",
        ),
        library_id="lib1",
        source_label="test",
        text_path=engine._write_text("lib1", "item1", "Calibration is useful but details are sparse."),
        chunks=chunks,
        discussion=[],
    )
    missing = LibraryItemEntry(
        id="item2",
        library_id="lib1",
        rank=2,
        title="Missing Paper",
        effective_title="Missing Paper",
        authors=[],
        source="OpenAlex",
        landing_url="https://example.com/missing",
    )
    detail = LibraryDetailResponse(
        status="ok",
        generated_at="now",
        library=LibrarySummary(
            id="lib1",
            name="Sparse library",
            slug="sparse-library",
            source_kind="query",
            source_ref="calibration",
            root_path=str(tmp_path / "library"),
            created_at="now",
            updated_at="now",
        ),
        items=[
            LibraryItemEntry(
                id="item1",
                library_id="lib1",
                rank=1,
                title="Sparse Calibration Paper",
                effective_title="Sparse Calibration Paper",
                authors=[],
                source="OpenAlex",
            ),
            missing,
        ],
    )

    response = engine.build_research_synthesis(detail, topic="calibration in simulation-based inference", profile="sbi_calibration")

    assert response.status == "ok"
    payload = response.structured_payload
    assert payload["missing_fulltext_count"] == 1
    assert payload["missing_fulltext"][0]["item_id"] == "item2"
    assert payload["manual_review_needed"] is True
    assert "missing_fulltext" in payload["risk_flags"]
    assert payload["unsupported_claims"]


def test_openai_runtime_failure_falls_back_to_local(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com/paper":
            return httpx.Response(
                200,
                text="""
                <html><body>
                <h1>Simulation Based Calibration</h1>
                <p>Abstract. We introduce simulation-based calibration diagnostics for posterior approximations.</p>
                <p>Methods. Coverage and rank statistics reveal calibration failures under repeated simulation.</p>
                </body></html>
                """,
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404, text="missing")

    class _FailingEmbeddings:
        def create(self, **_kwargs):
            raise RuntimeError("insufficient_quota")

    class _FailingResponses:
        def create(self, **_kwargs):
            raise RuntimeError("insufficient_quota")

    class _FailingOpenAI:
        embeddings = _FailingEmbeddings()
        responses = _FailingResponses()

    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="hybrid",
        RESEARCH_MCP_COMPUTE_BACKEND="openai",
        RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED="false",
        OPENAI_API_KEY="dummy",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db", transport=httpx.MockTransport(handler))
    engine._openai = _FailingOpenAI()
    item = LibraryItemEntry(
        id="item1",
        library_id="lib1",
        rank=1,
        title="Simulation Based Calibration",
        effective_title="Simulation Based Calibration",
        authors=["A. Author"],
        source="OpenAlex",
        landing_url="https://example.com/paper",
    )

    ingest = engine.ingest_item("lib1", item, include_forums=False, reingest=True)
    assert ingest.extraction_status == "ready"
    assert engine._openai_disabled_reason is not None

    summary = engine.summarize_item(item, topic="calibration")
    assert summary.status == "ok"
    assert summary.compute_backend == "local_heuristic"


def test_reranker_reorders_selected_chunks(tmp_path):
    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        RESEARCH_MCP_ANALYSIS_MODE="hybrid",
        RESEARCH_MCP_COMPUTE_BACKEND="local",
        RESEARCH_MCP_LOCAL_EMBEDDING_MODEL="hash-embedding-v1",
    )
    engine = AnalysisEngine(settings, tmp_path / "state.db")

    class _FakeReranker:
        def is_configured(self):
            return True

        def rerank(self, query, documents):
            return [0.1, 0.9]

    class _FakeEmbedder:
        def close(self):
            return None

    engine._local_reranker = _FakeReranker()
    engine._local_embedder = _FakeEmbedder()
    chunks = [
        engine._chunk_text("item1", "Abstract\n\ncalibration is useful.\n\nfirst chunk")[0],
        engine._chunk_text("item1", "Abstract\n\ncalibration is useful.\n\nsecond chunk")[0],
    ]
    for idx, chunk in enumerate(chunks):
        chunk.id = f"item1_{idx}"
        chunk.lexical_score = 0.5
        chunk.semantic_score = 0.5

    reranked = engine._rerank_chunks(chunks, query="calibration")
    assert reranked[0].id == "item1_1"
