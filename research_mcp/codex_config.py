from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from research_mcp.paths import APP_HOME, CODEX_CONFIG_FILE, PROJECT_ROOT, command_path


MANAGED_BEGIN = "# BEGIN research-mcp managed block"
MANAGED_END = "# END research-mcp managed block"


def render_managed_block() -> str:
    command = command_path()
    cache_path = APP_HOME / "state" / "research.db"
    return "\n".join(
        [
            MANAGED_BEGIN,
            "[mcp_servers.research]",
            f'command = "{command}"',
            'args = []',
            f'cwd = "{APP_HOME}"',
            "startup_timeout_sec = 20",
            "tool_timeout_sec = 120",
            "enabled = true",
            "required = false",
            "enabled_tools = [",
            '  "search_literature",',
            '  "search_biomed",',
            '  "search_source",',
            '  "resolve_open_access",',
            '  "health_check",',
            '  "download_pdfs",',
            '  "organize_library",',
            '  "collect_library",',
            '  "import_library",',
            '  "list_libraries",',
            '  "read_library",',
            '  "rename_library",',
            '  "archive_library",',
            '  "restore_library",',
            '  "tag_library",',
            '  "update_library_item",',
            '  "archive_library_item",',
            '  "restore_library_item",',
            '  "generate_context_bundle",',
            '  "read_context_bundle",',
            '  "render_library_manager",',
            '  "get_analysis_settings",',
            '  "update_analysis_settings",',
            '  "ingest_library",',
            '  "ingest_library_item",',
            '  "summarize_library",',
            '  "summarize_library_item",',
            '  "compare_library_items",',
            '  "analyze_library_topic",',
            '  "search_library_evidence",',
            '  "build_research_synthesis",',
            '  "read_synthesis_report",',
            '  "list_domain_profiles",',
            '  "list_analysis_reports",',
            '  "read_analysis_report",',
            "]",
            "env_vars = [",
            '  "OPENALEX_API_KEY",',
            '  "CROSSREF_MAILTO",',
            '  "SEMANTIC_SCHOLAR_API_KEY",',
            '  "NCBI_API_KEY",',
            '  "UNPAYWALL_EMAIL",',
            '  "CORE_API_KEY",',
            '  "OPENAI_API_KEY",',
            "]",
            "",
            "[mcp_servers.research.env]",
            f'RESEARCH_MCP_HOME = "{APP_HOME}"',
            f'SCIBUDY_HOME = "{APP_HOME}"',
            f'RESEARCH_MCP_CACHE_DB_PATH = "{cache_path}"',
            'RESEARCH_MCP_PROVIDER_TIMEOUT_SEC = "45"',
            'RESEARCH_MCP_SEARCH_TOTAL_TIMEOUT_SEC = "110"',
            'RESEARCH_MCP_MAX_PROVIDER_WORKERS = "6"',
            'RESEARCH_MCP_ENABLE_DOAJ = "true"',
            'RESEARCH_MCP_ENABLE_CORE = "true"',
            'RESEARCH_MCP_ENABLE_SEMANTIC_SCHOLAR = "true"',
            'RESEARCH_MCP_ALLOW_PUBLIC_SEMANTIC_SCHOLAR = "true"',
            'RESEARCH_MCP_ANALYSIS_MODE = "hybrid"',
            'RESEARCH_MCP_COMPUTE_BACKEND = "auto"',
            'RESEARCH_MCP_CHUNK_SIZE = "1800"',
            'RESEARCH_MCP_CHUNK_OVERLAP = "250"',
            'RESEARCH_MCP_MAX_SUMMARY_DEPTH = "standard"',
            'RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED = "true"',
            'RESEARCH_MCP_FORUM_SOURCE_PROFILE = "high_trust"',
            'RESEARCH_MCP_FORUM_SOURCES = "openreview,github"',
            'RESEARCH_MCP_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"',
            'RESEARCH_MCP_OPENAI_SUMMARY_MODEL = "gpt-5.4-mini"',
            'RESEARCH_MCP_LOCAL_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-4B"',
            'RESEARCH_MCP_LOCAL_EMBEDDING_DIMENSION = "2560"',
            'RESEARCH_MCP_LOCAL_EMBEDDING_ENV = "research_embed"',
            'RESEARCH_MCP_LOCAL_RERANKER_MODEL = "Qwen/Qwen3-Reranker-4B"',
            'RESEARCH_MCP_LOCAL_RERANKER_ENV = "research_embed"',
            'RESEARCH_MCP_LOG_LEVEL = "ERROR"',
            MANAGED_END,
            "",
        ]
    )


def has_research_block(content: str) -> bool:
    return MANAGED_BEGIN in content or "[mcp_servers.research]" in content


def upsert_research_block(content: str) -> str:
    block = render_managed_block()
    cleaned = _remove_managed_block(content)
    cleaned = _remove_research_tables(cleaned)
    return _insert_block(cleaned, block)


def _remove_managed_block(content: str) -> str:
    if MANAGED_BEGIN not in content or MANAGED_END not in content:
        return content
    pattern = re.compile(rf"{re.escape(MANAGED_BEGIN)}.*?{re.escape(MANAGED_END)}\n?", re.DOTALL)
    return pattern.sub("", content)


def _remove_research_tables(content: str) -> str:
    lines = content.splitlines(keepends=True)
    kept: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[mcp_servers.research"):
            skipping = True
            continue
        if skipping and stripped.startswith("[") and not stripped.startswith("[mcp_servers.research"):
            skipping = False
        if not skipping:
            kept.append(line)
    return "".join(kept)


def _insert_block(content: str, block: str) -> str:
    marker = "\n[projects."
    index = content.find(marker)
    if index != -1:
        prefix = content[:index].rstrip() + "\n\n"
        suffix = content[index + 1 :]
        return f"{prefix}{block}\n{suffix}"

    suffix = "" if not content or content.endswith("\n") else "\n"
    return f"{content}{suffix}\n{block}"


def install_to_codex_config(config_path: Path = CODEX_CONFIG_FILE, *, create_backup: bool = True) -> Path:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated = upsert_research_block(original)
    if create_backup and config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.bak-{timestamp}")
        backup_path.write_text(original, encoding="utf-8")
    config_path.write_text(updated, encoding="utf-8")
    return config_path
