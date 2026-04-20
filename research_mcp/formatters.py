from __future__ import annotations

import json
from typing import Any


def format_search_response(payload: dict[str, Any], *, fmt: str = "table", details: bool = False) -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)

    results = payload.get("results") or []
    if fmt == "titles":
        return "\n".join((item.get("title") or "").strip() for item in results if item.get("title"))
    if fmt == "tsv":
        lines = ["index\tyear\tsource\tcitations\toa\ttitle\tdoi\turl"]
        for index, item in enumerate(results, start=1):
            lines.append(
                "\t".join(
                    [
                        str(index),
                        str(item.get("year") or ""),
                        str(item.get("source") or ""),
                        str(item.get("citation_count") or ""),
                        "yes" if item.get("is_open_access") else "",
                        _clean(item.get("title")),
                        str(item.get("doi") or ""),
                        str(item.get("landing_url") or ""),
                    ]
                )
            )
        return "\n".join(lines)
    if fmt == "markdown":
        lines = []
        for index, item in enumerate(results, start=1):
            title = item.get("title") or "(untitled)"
            source = item.get("source") or ""
            year = item.get("year") or ""
            citation = item.get("citation_count") or ""
            lines.append(f"{index}. **{title}** [{source} {year}]")
            if details:
                if item.get("doi"):
                    lines.append(f"   DOI: {item['doi']}")
                if item.get("landing_url"):
                    lines.append(f"   URL: {item['landing_url']}")
                if citation:
                    lines.append(f"   Citations: {citation}")
        return "\n".join(lines)

    headers = ["#", "Year", "Source", "Cites", "OA", "Title"]
    rows = []
    for index, item in enumerate(results, start=1):
        rows.append(
            [
                str(index),
                str(item.get("year") or ""),
                str(item.get("source") or ""),
                str(item.get("citation_count") or ""),
                "Y" if item.get("is_open_access") else "",
                _truncate(item.get("title") or "", 88),
            ]
        )
    lines = [_render_table(headers, rows)]
    if details and results:
        lines.append("")
        for index, item in enumerate(results, start=1):
            lines.append(f"[{index}] {item.get('title') or '(untitled)'}")
            if item.get("doi"):
                lines.append(f"  DOI: {item['doi']}")
            if item.get("landing_url"):
                lines.append(f"  URL: {item['landing_url']}")
            if item.get("pdf_url"):
                lines.append(f"  PDF: {item['pdf_url']}")
    return "\n".join(lines)


def format_open_access_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    lines = [
        f"doi: {payload.get('doi', '')}",
        f"status: {payload.get('status', '')}",
        f"is_open_access: {payload.get('is_open_access', '')}",
        f"oa_status: {payload.get('oa_status', '')}",
        f"best_url: {payload.get('best_url', '')}",
        f"pdf_url: {payload.get('pdf_url', '')}",
        f"license: {payload.get('license', '')}",
    ]
    if payload.get("message"):
        lines.append(f"message: {payload['message']}")
    return "\n".join(lines)


def format_download_batch_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    headers = ["Rank", "Status", "Source", "Saved PDF", "Title"]
    rows = []
    for item in payload.get("records") or []:
        rows.append(
            [
                str(item.get("rank") or ""),
                str(item.get("status") or ""),
                str(item.get("source") or ""),
                _truncate(str(item.get("local_pdf_path") or ""), 48),
                _truncate(str(item.get("title") or ""), 72),
            ]
        )
    prefix = [
        f"status: {payload.get('status', '')}",
        f"target_dir: {payload.get('target_dir', '')}",
        f"downloaded_count: {payload.get('downloaded_count', 0)}/{payload.get('requested_count', 0)}",
        "",
    ]
    return "\n".join(prefix) + _render_table(headers, rows)


def format_organize_library_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    lines = [
        f"status: {payload.get('status', '')}",
        f"target_dir: {payload.get('target_dir', '')}",
        f"downloaded_count: {payload.get('downloaded_count', 0)}/{payload.get('requested_count', 0)}",
        f"manifest_path: {payload.get('manifest_path', '')}",
        f"csv_path: {payload.get('csv_path', '')}",
        f"markdown_path: {payload.get('markdown_path', '')}",
        f"bibtex_path: {payload.get('bibtex_path', '')}",
        f"download_checklist_csv_path: {payload.get('download_checklist_csv_path', '')}",
        f"download_checklist_markdown_path: {payload.get('download_checklist_markdown_path', '')}",
        "",
    ]
    return "\n".join(lines) + _render_table(
        ["Rank", "Status", "Saved PDF", "Title"],
        [
            [
                str(item.get("rank") or ""),
                str(item.get("status") or ""),
                "yes" if item.get("local_pdf_path") else "",
                _truncate(str(item.get("title") or ""), 76),
            ]
            for item in (payload.get("records") or [])
        ],
    )


def format_provider_statuses(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    items = payload.get("provider_statuses") or []
    headers = ["Provider", "Type", "Enabled", "Ready", "Missing", "Message"]
    rows = []
    for item in items:
        rows.append(
            [
                str(item.get("provider") or ""),
                str(item.get("category") or ""),
                "Y" if item.get("enabled") else "N",
                "Y" if item.get("ready") else "N",
                ",".join(item.get("missing_credentials") or []),
                _truncate(item.get("message") or "", 52),
            ]
        )
    return _render_table(headers, rows)


def format_libraries_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    items = payload.get("libraries") or []
    rows = [
        [
            item.get("id") or "",
            item.get("name") or "",
            str(item.get("active_item_count") or 0),
            str(item.get("item_count") or 0),
            ",".join(item.get("tags") or []),
            "Y" if item.get("archived") else "",
        ]
        for item in items
    ]
    return _render_table(["ID", "Name", "Active", "Total", "Tags", "Archived"], rows)


def format_library_detail_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    library = payload.get("library") or {}
    items = payload.get("items") or []
    lines = [
        f"status: {payload.get('status', '')}",
        f"id: {library.get('id', '')}",
        f"name: {library.get('name', '')}",
        f"source_kind: {library.get('source_kind', '')}",
        f"source_ref: {library.get('source_ref', '')}",
        f"root_path: {library.get('root_path', '')}",
        "",
    ]
    rows = [
        [
            str(item.get("rank") or ""),
            _truncate(str(item.get("effective_title") or item.get("title") or ""), 64),
            str(item.get("year") or ""),
            str(item.get("source") or ""),
            ",".join(item.get("tags") or []),
            "Y" if item.get("favorite") else "",
            "Y" if item.get("archived") else "",
        ]
        for item in items
    ]
    return "\n".join(lines) + _render_table(["Rank", "Title", "Year", "Source", "Tags", "Fav", "Archived"], rows)


def format_mutation_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return "\n".join(
        [
            f"status: {payload.get('status', '')}",
            f"message: {payload.get('message', '')}",
            f"library: {(payload.get('library') or {}).get('name', '')}",
            f"item: {(payload.get('item') or {}).get('effective_title', '')}",
            f"bundle: {(payload.get('bundle') or {}).get('name', '')}",
        ]
    )


def format_context_bundle_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    bundle = payload.get("bundle") or {}
    return "\n".join(
        [
            f"status: {payload.get('status', '')}",
            f"id: {bundle.get('id', '')}",
            f"name: {bundle.get('name', '')}",
            f"library_id: {bundle.get('library_id', '')}",
            f"mode: {bundle.get('mode', '')}",
            f"max_items: {bundle.get('max_items', '')}",
            "",
            payload.get("text") or bundle.get("preview") or "",
        ]
    )


def format_analysis_settings_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    lines = [
        f"status: {payload.get('status', '')}",
        f"analysis_mode: {payload.get('analysis_mode', '')}",
        f"compute_backend: {payload.get('compute_backend', '')}",
        f"chunk_size: {payload.get('chunk_size', '')}",
        f"chunk_overlap: {payload.get('chunk_overlap', '')}",
        f"max_summary_depth: {payload.get('max_summary_depth', '')}",
        f"forum_enrichment_enabled: {payload.get('forum_enrichment_enabled', '')}",
        f"forum_source_profile: {payload.get('forum_source_profile', '')}",
        f"forum_sources: {', '.join(payload.get('forum_sources') or [])}",
        f"openai_embedding_model: {payload.get('openai_embedding_model', '')}",
        f"openai_summary_model: {payload.get('openai_summary_model', '')}",
        f"local_embedding_model: {payload.get('local_embedding_model', '')}",
        f"local_embedding_dimension: {payload.get('local_embedding_dimension', '')}",
        f"local_embedding_env: {payload.get('local_embedding_env', '')}",
        f"local_reranker_model: {payload.get('local_reranker_model', '')}",
        f"local_reranker_env: {payload.get('local_reranker_env', '')}",
        f"openai_ready: {payload.get('openai_ready', False)}",
    ]
    if payload.get("message"):
        lines.append(f"message: {payload['message']}")
    return "\n".join(lines)


def format_ingest_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    lines = [
        f"status: {payload.get('status', '')}",
        f"library_id: {payload.get('library_id', '')}",
        f"item_id: {payload.get('item_id', '')}",
        f"mode: {payload.get('mode', '')}",
        f"compute_backend: {payload.get('compute_backend', '')}",
        f"ready_count: {payload.get('ready_count', 0)}/{payload.get('processed_count', 0)}",
        "",
    ]
    rows = [
        [
            item.get("item_id") or "",
            _truncate(item.get("title") or "", 52),
            item.get("extraction_status") or "",
            str(item.get("chunk_count") or 0),
            str(item.get("discussion_count") or 0),
            _truncate(item.get("message") or "", 42),
        ]
        for item in payload.get("records") or []
    ]
    return "\n".join(lines) + _render_table(["Item", "Title", "Status", "Chunks", "Discussions", "Message"], rows)


def format_analysis_summary_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    lines = [
        f"status: {payload.get('status', '')}",
        f"title: {payload.get('title', '')}",
        f"analysis_mode: {payload.get('analysis_mode', '')}",
        f"compute_backend: {payload.get('compute_backend', '')}",
        f"topic: {payload.get('topic', '')}",
        "",
        payload.get("summary") or "",
        "",
        "key_points:",
    ]
    for point in payload.get("key_points") or []:
        lines.append(f"- {point}")
    structured = payload.get("structured_payload") or {}
    if structured:
        lines.extend(["", "structured_payload: yes"])
        if structured.get("analyzed_item_count") is not None:
            lines.append(f"analyzed_item_count: {structured.get('analyzed_item_count')}")
        if structured.get("schema_version"):
            lines.append(f"schema_version: {structured.get('schema_version')}")
    evidence = payload.get("evidence") or []
    if evidence:
        lines.extend(["", "evidence:"])
        for item in evidence:
            metadata = item.get("metadata") or {}
            parts = [
                f"- {item.get('source_type', '')}: {item.get('title') or item.get('url') or item.get('excerpt') or ''}",
            ]
            score_bits = []
            if metadata.get("lexical_score") is not None:
                score_bits.append(f"lexical={metadata['lexical_score']}")
            if metadata.get("semantic_score") is not None:
                score_bits.append(f"semantic={metadata['semantic_score']}")
            if metadata.get("semantic_backend"):
                score_bits.append(f"backend={metadata['semantic_backend']}")
            if score_bits:
                parts.append(f" ({', '.join(score_bits)})")
            lines.append("".join(parts))
    return "\n".join(lines)


def format_domain_profiles_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    profiles = payload.get("profiles") or []
    return _render_table(
        ["ID", "Label", "Scope", "Example", "Description"],
        [
            [
                item.get("id") or item.get("name") or "",
                item.get("label") or "",
                item.get("scope") or "",
                "Y" if item.get("is_example") else "",
                _truncate(item.get("description") or "", 72),
            ]
            for item in profiles
        ],
    )


def format_run_list(items: list[dict[str, Any]], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(items, indent=2, ensure_ascii=False)
    headers = ["Run ID", "Kind", "Saved At", "Results", "Query/DOI"]
    rows = []
    for item in items:
        rows.append(
            [
                item.get("id") or "",
                item.get("kind") or "",
                item.get("saved_at") or "",
                str(item.get("result_count") or ""),
                _truncate(str(item.get("query") or item.get("doi") or ""), 64),
            ]
        )
    return _render_table(headers, rows)


def format_libraries_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    libraries = payload.get("libraries") or []
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return _render_table(
        ["Library ID", "Name", "Active", "Total", "Tags", "Archived"],
        [
            [
                str(item.get("id") or ""),
                _truncate(str(item.get("name") or ""), 34),
                str(item.get("active_item_count") or 0),
                str(item.get("item_count") or 0),
                _truncate(",".join(item.get("tags") or []), 28),
                "Y" if item.get("archived") else "",
            ]
            for item in libraries
        ],
    )


def format_library_detail_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    library = payload.get("library") or {}
    lines = [
        f"status: {payload.get('status', '')}",
        f"library_id: {library.get('id', '')}",
        f"name: {library.get('name', '')}",
        f"root_path: {library.get('root_path', '')}",
        f"tags: {', '.join(library.get('tags') or [])}",
        "",
        _render_table(
            ["Rank", "Title", "Year", "Source", "Fav", "Archived"],
            [
                [
                    str(item.get("rank") or ""),
                    _truncate(str(item.get("effective_title") or ""), 60),
                    str(item.get("year") or ""),
                    str(item.get("source") or ""),
                    "Y" if item.get("favorite") else "",
                    "Y" if item.get("archived") else "",
                ]
                for item in (payload.get("items") or [])
            ],
        ),
    ]
    bundles = payload.get("bundles") or []
    if bundles:
        lines.extend(
            [
                "",
                "Bundles:",
                _render_table(
                    ["Bundle ID", "Name", "Items", "Updated"],
                    [
                        [
                            str(bundle.get("id") or ""),
                            _truncate(str(bundle.get("name") or ""), 32),
                            str(bundle.get("item_count") or 0),
                            str(bundle.get("updated_at") or ""),
                        ]
                        for bundle in bundles
                    ],
                ),
            ]
        )
    return "\n".join(lines)


def format_mutation_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    lines = [
        f"status: {payload.get('status', '')}",
        f"message: {payload.get('message', '')}",
    ]
    if payload.get("library"):
        lines.append(f"library_id: {payload['library'].get('id', '')}")
        lines.append(f"library_name: {payload['library'].get('name', '')}")
    if payload.get("item"):
        lines.append(f"item_id: {payload['item'].get('id', '')}")
        lines.append(f"item_title: {payload['item'].get('effective_title', '')}")
    if payload.get("bundle"):
        lines.append(f"bundle_id: {payload['bundle'].get('id', '')}")
        lines.append(f"bundle_name: {payload['bundle'].get('name', '')}")
    return "\n".join(lines)


def format_context_bundle_response(payload: dict[str, Any], *, fmt: str = "table") -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    bundle = payload.get("bundle") or {}
    lines = [
        f"status: {payload.get('status', '')}",
        f"bundle_id: {bundle.get('id', '')}",
        f"name: {bundle.get('name', '')}",
        f"library_id: {bundle.get('library_id', '')}",
        f"resource_uri: {bundle.get('resource_uri', '')}",
        "",
        payload.get("text") or "",
    ]
    return "\n".join(lines).strip()


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    header_line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    divider = "  ".join("-" * widths[index] for index in range(len(headers)))
    body = ["  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) for row in rows]
    return "\n".join([header_line, divider, *body])


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: width - 1] + "…"


def _clean(value: str) -> str:
    return " ".join(value.split())
