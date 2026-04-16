from research_mcp.codex_config import MANAGED_BEGIN, MANAGED_END, upsert_research_block


def test_upsert_research_block_appends_when_missing():
    content = 'model = "gpt-5.4"\n'
    updated = upsert_research_block(content)
    assert MANAGED_BEGIN in updated
    assert "[mcp_servers.research]" in updated
    assert MANAGED_END in updated
    assert "tool_timeout_sec = 120" in updated
    assert 'RESEARCH_MCP_HOME = "' in updated
    assert 'SCIBUDY_HOME = "' in updated
    assert 'RESEARCH_MCP_PROVIDER_TIMEOUT_SEC = "45"' in updated
    assert 'RESEARCH_MCP_SEARCH_TOTAL_TIMEOUT_SEC = "110"' in updated
    assert 'RESEARCH_MCP_MAX_PROVIDER_WORKERS = "6"' in updated
    assert 'RESEARCH_MCP_FORUM_SOURCE_PROFILE = "high_trust"' in updated
    assert 'RESEARCH_MCP_FORUM_SOURCES = "openreview,github"' in updated
    assert 'RESEARCH_MCP_LOCAL_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-4B"' in updated
    assert 'RESEARCH_MCP_LOCAL_EMBEDDING_ENV = "research_embed"' in updated


def test_upsert_research_block_replaces_existing_unmanaged_block():
    content = """
model = "gpt-5.4"

[mcp_servers.research]
command = "/old/python"
args = ["-m", "research_mcp"]

[mcp_servers.research.env]
RESEARCH_MCP_LOG_LEVEL = "INFO"

[features]
undo = true
"""
    updated = upsert_research_block(content)
    assert updated.count("[mcp_servers.research]") == 1
    assert 'command = "/old/python"' not in updated
    assert "[features]" in updated
