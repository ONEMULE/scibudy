import React, { useEffect, useMemo, useState } from "react";

function getHostBootstrap() {
  const openai = window.openai;
  if (!openai) {
    return null;
  }
  const meta = openai.toolResponseMetadata || {};
  if (meta.bootstrap) {
    return meta.bootstrap;
  }
  return null;
}

async function apiTool(name, args) {
  if (window.openai?.callTool) {
    return window.openai.callTool(name, args);
  }
  const response = await fetch(`/api/tool/${name}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(args || {}),
  });
  if (!response.ok) {
    throw new Error(`API ${name} failed with ${response.status}`);
  }
  return response.json();
}

async function loadBootstrap(libraryId, includeArchived) {
  const hostBootstrap = getHostBootstrap();
  if (hostBootstrap && !libraryId) {
    return hostBootstrap;
  }
  const params = new URLSearchParams();
  if (libraryId) params.set("library_id", libraryId);
  if (includeArchived) params.set("include_archived", "true");
  const response = await fetch(`/api/bootstrap?${params.toString()}`);
  if (!response.ok) throw new Error(`Bootstrap failed with ${response.status}`);
  return response.json();
}

function textValue(value, fallback = "") {
  return value == null ? fallback : String(value);
}

export default function App() {
  const [bootstrap, setBootstrap] = useState(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selectedLibraryId, setSelectedLibraryId] = useState(null);
  const [selectedBundle, setSelectedBundle] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [importPath, setImportPath] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [tagValue, setTagValue] = useState("");
  const [topicValue, setTopicValue] = useState("calibration");
  const [analysisResult, setAnalysisResult] = useState(null);
  const [analysisSettings, setAnalysisSettings] = useState(null);
  const [analysisReports, setAnalysisReports] = useState([]);
  const [selectedItemIds, setSelectedItemIds] = useState([]);
  const [synthesisProfile, setSynthesisProfile] = useState("auto");

  useEffect(() => {
    refresh();
  }, [includeArchived]);

  async function refresh(libraryId = selectedLibraryId) {
    try {
      setBusy(true);
      setError("");
      const data = await loadBootstrap(libraryId, includeArchived);
      setBootstrap(data);
      const nextLibraryId =
        libraryId ||
        data?.selected_library?.library?.id ||
        data?.libraries?.[0]?.id ||
        null;
      setSelectedLibraryId(nextLibraryId);
      setSelectedBundle(null);
      setAnalysisResult(null);
      setSelectedItemIds([]);
      setRenameValue(data?.selected_library?.library?.name || "");
      setTagValue((data?.selected_library?.library?.tags || []).join(", "));
      setAnalysisSettings(data?.analysis_settings || null);
      if (data?.analysis_reports && nextLibraryId === data?.selected_library?.library?.id) {
        setAnalysisReports(data.analysis_reports || []);
      } else if (nextLibraryId) {
        const reports = await apiTool("list_analysis_reports", { library_id: nextLibraryId });
        setAnalysisReports(reports.reports || []);
      } else {
        setAnalysisReports([]);
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function openLibrary(libraryId) {
    await refresh(libraryId);
  }

  async function mutateTool(name, args, onSuccess) {
    try {
      setBusy(true);
      setError("");
      const result = await apiTool(name, args);
      if (result.status && result.status !== "ok") {
        throw new Error(result.message || `${name} failed`);
      }
      if (onSuccess) {
        await onSuccess(result);
      } else {
        await refresh(selectedLibraryId);
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  const libraries = bootstrap?.libraries || [];
  const selectedLibrary = bootstrap?.selected_library?.library || null;
  const items = bootstrap?.selected_library?.items || [];
  const bundles = bootstrap?.selected_library?.bundles || [];

  const summaryStats = useMemo(() => {
    if (!selectedLibrary) return null;
    return {
      items: selectedLibrary.item_count,
      active: selectedLibrary.active_item_count,
      favorites: selectedLibrary.favorite_count,
    };
  }, [selectedLibrary]);

  async function loadAnalysis(action, args) {
    await mutateTool(action, args, async (result) => {
      setAnalysisResult(result);
      await refresh(selectedLibraryId);
    });
  }

  function toggleSelectedItem(itemId) {
    setSelectedItemIds((current) =>
      current.includes(itemId) ? current.filter((value) => value !== itemId) : [...current, itemId]
    );
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebarHeader">
          <div>
            <div className="eyebrow">Research MCP</div>
            <h1>Library Manager</h1>
          </div>
          <button onClick={() => refresh()} disabled={busy}>
            Refresh
          </button>
        </div>

        <label className="toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          Include archived
        </label>

        <div className="importCard">
          <div className="cardTitle">Import existing library</div>
          <input
            value={importPath}
            onChange={(e) => setImportPath(e.target.value)}
            placeholder="/abs/path/to/library-or-manifest"
          />
          <button
            onClick={() =>
              mutateTool("import_library", { path: importPath }, async (result) => {
                setImportPath("");
                await refresh(result.library?.id || selectedLibraryId);
              })
            }
            disabled={!importPath || busy}
          >
            Import
          </button>
        </div>

        <div className="libraryList">
          {libraries.map((library) => (
            <button
              key={library.id}
              className={`libraryCard ${selectedLibraryId === library.id ? "selected" : ""}`}
              onClick={() => openLibrary(library.id)}
            >
              <div className="libraryName">{library.name}</div>
              <div className="libraryMeta">
                <span>{library.active_item_count}/{library.item_count}</span>
                {library.archived ? <span>archived</span> : null}
              </div>
              <div className="tagRow">
                {(library.tags || []).slice(0, 3).map((tag) => (
                  <span key={tag} className="tag">
                    {tag}
                  </span>
                ))}
              </div>
            </button>
          ))}
          {!libraries.length ? <div className="empty">No libraries yet.</div> : null}
        </div>
      </aside>

      <main className="main">
        {error ? <div className="errorBanner">{error}</div> : null}
        {!selectedLibrary ? (
          <div className="empty hero">Select or import a library to begin.</div>
        ) : (
          <>
            <section className="panel">
              <div className="panelHeader">
                <div>
                  <div className="eyebrow">{selectedLibrary.source_kind}</div>
                  <h2>{selectedLibrary.name}</h2>
                </div>
                <div className="actions">
                  <button
                    onClick={() =>
                      mutateTool("archive_library", { library_id: selectedLibrary.id }, () =>
                        refresh()
                      )
                    }
                    disabled={busy || selectedLibrary.archived}
                  >
                    Archive
                  </button>
                  <button
                    onClick={() =>
                      mutateTool("restore_library", { library_id: selectedLibrary.id }, () =>
                        refresh(selectedLibrary.id)
                      )
                    }
                    disabled={busy || !selectedLibrary.archived}
                  >
                    Restore
                  </button>
                </div>
              </div>
              <div className="statGrid">
                <div><strong>{summaryStats?.items || 0}</strong><span>Total items</span></div>
                <div><strong>{summaryStats?.active || 0}</strong><span>Active items</span></div>
                <div><strong>{summaryStats?.favorites || 0}</strong><span>Favorites</span></div>
              </div>
              <div className="formGrid">
                <label>
                  Rename library
                  <input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} />
                </label>
                <button
                  onClick={() =>
                    mutateTool("rename_library", { library_id: selectedLibrary.id, new_name: renameValue })
                  }
                  disabled={busy || !renameValue}
                >
                  Save name
                </button>
                <label>
                  Tags
                  <input value={tagValue} onChange={(e) => setTagValue(e.target.value)} placeholder="tag1, tag2" />
                </label>
                <button
                  onClick={() =>
                    mutateTool("tag_library", {
                      library_id: selectedLibrary.id,
                      tags: tagValue.split(",").map((t) => t.trim()).filter(Boolean),
                    })
                  }
                  disabled={busy}
                >
                  Save tags
                </button>
              </div>
              <div className="pathList">
                <a href={selectedLibrary.root_path} onClick={(e) => e.preventDefault()}>
                  {selectedLibrary.root_path}
                </a>
              </div>
            </section>

            <section className="panel">
              <div className="panelHeader">
                <h3>Analysis settings</h3>
                <button
                  onClick={() =>
                    mutateTool("update_analysis_settings", {
                      analysis_mode: analysisSettings?.analysis_mode,
                      compute_backend: analysisSettings?.compute_backend,
                      chunk_size: analysisSettings?.chunk_size,
                      chunk_overlap: analysisSettings?.chunk_overlap,
                      max_summary_depth: analysisSettings?.max_summary_depth,
                      forum_enrichment_enabled: analysisSettings?.forum_enrichment_enabled,
                      forum_source_profile: analysisSettings?.forum_source_profile,
                      forum_sources: textValue(analysisSettings?.forum_sources, "")
                        .split(",")
                        .map((value) => value.trim())
                        .filter(Boolean),
                      openai_embedding_model: analysisSettings?.openai_embedding_model,
                      openai_summary_model: analysisSettings?.openai_summary_model,
                      local_embedding_model: analysisSettings?.local_embedding_model,
                      local_embedding_dimension: analysisSettings?.local_embedding_dimension,
                      local_embedding_env: analysisSettings?.local_embedding_env,
                      local_reranker_model: analysisSettings?.local_reranker_model,
                      local_reranker_env: analysisSettings?.local_reranker_env,
                    }, async (result) => {
                      setAnalysisSettings(result);
                      await refresh(selectedLibraryId);
                    })
                  }
                  disabled={busy || !analysisSettings}
                >
                  Save analysis defaults
                </button>
              </div>
              {analysisSettings ? (
                <div className="formGrid four">
                  <label>
                    Analysis mode
                    <select
                      value={analysisSettings.analysis_mode}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, analysis_mode: e.target.value })}
                    >
                      <option value="rules">rules</option>
                      <option value="hybrid">hybrid</option>
                      <option value="semantic_heavy">semantic_heavy</option>
                    </select>
                  </label>
                  <label>
                    Compute backend
                    <select
                      value={analysisSettings.compute_backend}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, compute_backend: e.target.value })}
                    >
                      <option value="auto">auto</option>
                      <option value="local">local</option>
                      <option value="openai">openai</option>
                    </select>
                  </label>
                  <label>
                    Summary depth
                    <select
                      value={analysisSettings.max_summary_depth}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, max_summary_depth: e.target.value })}
                    >
                      <option value="shallow">shallow</option>
                      <option value="standard">standard</option>
                      <option value="deep">deep</option>
                    </select>
                  </label>
                  <label>
                    Forum enrichment
                    <select
                      value={String(analysisSettings.forum_enrichment_enabled)}
                      onChange={(e) =>
                        setAnalysisSettings({
                          ...analysisSettings,
                          forum_enrichment_enabled: e.target.value === "true",
                        })
                      }
                    >
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  </label>
                  <label>
                    Forum trust profile
                    <select
                      value={analysisSettings.forum_source_profile}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, forum_source_profile: e.target.value })}
                    >
                      <option value="high_trust">high_trust</option>
                      <option value="extended">extended</option>
                      <option value="experimental">experimental</option>
                    </select>
                  </label>
                  <label>
                    Forum sources
                    <input
                      value={textValue(analysisSettings.forum_sources, "")}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, forum_sources: e.target.value })}
                      placeholder="openreview,github"
                    />
                  </label>
                  <label>
                    Chunk size
                    <input
                      type="number"
                      value={analysisSettings.chunk_size}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, chunk_size: Number(e.target.value || 0) })}
                    />
                  </label>
                  <label>
                    Chunk overlap
                    <input
                      type="number"
                      value={analysisSettings.chunk_overlap}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, chunk_overlap: Number(e.target.value || 0) })}
                    />
                  </label>
                  <label>
                    OpenAI embedding model
                    <input
                      value={analysisSettings.openai_embedding_model}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, openai_embedding_model: e.target.value })}
                    />
                  </label>
                  <label>
                    OpenAI summary model
                    <input
                      value={analysisSettings.openai_summary_model}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, openai_summary_model: e.target.value })}
                    />
                  </label>
                  <label>
                    Local embedding model
                    <input
                      value={analysisSettings.local_embedding_model}
                      onChange={(e) => setAnalysisSettings({ ...analysisSettings, local_embedding_model: e.target.value })}
                    />
                  </label>
                  <label>
                    Local embedding env
                    <input
                      value={analysisSettings.local_embedding_env}
                      disabled
                    />
                  </label>
                  <label>
                    Local reranker model
                    <input
                      value={analysisSettings.local_reranker_model}
                      disabled
                    />
                  </label>
                  <label>
                    Local reranker env
                    <input
                      value={analysisSettings.local_reranker_env}
                      disabled
                    />
                  </label>
                  <label>
                    Local embedding dimension
                    <input
                      type="number"
                      value={analysisSettings.local_embedding_dimension}
                      onChange={(e) =>
                        setAnalysisSettings({
                          ...analysisSettings,
                          local_embedding_dimension: Number(e.target.value || 0),
                        })
                      }
                    />
                  </label>
                </div>
              ) : null}
            </section>

            <section className="split">
              <div className="panel grow">
                <div className="panelHeader">
                  <h3>Items</h3>
                  <div className="rowActions">
                    <button
                      onClick={() =>
                        loadAnalysis("ingest_library", {
                          library_id: selectedLibrary.id,
                          include_forums: true,
                          reingest: false,
                        })
                      }
                      disabled={busy}
                    >
                      Ingest library
                    </button>
                    <button
                      onClick={() =>
                        loadAnalysis("summarize_library", {
                          library_id: selectedLibrary.id,
                          topic: topicValue || null,
                        })
                      }
                      disabled={busy}
                    >
                      Summarize
                    </button>
                    <button
                      onClick={() =>
                        loadAnalysis("compare_library_items", {
                          item_ids: selectedItemIds,
                          topic: topicValue || null,
                        })
                      }
                      disabled={busy || selectedItemIds.length < 2}
                    >
                      Compare selected
                    </button>
                    <button
                      onClick={() =>
                        loadAnalysis("build_research_synthesis", {
                          library_id: selectedLibrary.id,
                          topic: topicValue || "calibration",
                          max_items: 50,
                          profile: synthesisProfile,
                        })
                      }
                      disabled={busy}
                    >
                      Synthesize
                    </button>
                  </div>
                </div>
                <div className="topicBar">
                  <input value={topicValue} onChange={(e) => setTopicValue(e.target.value)} placeholder="Topic for synthesis, e.g. calibration or posterior coverage" />
                  <select value={synthesisProfile} onChange={(e) => setSynthesisProfile(e.target.value)}>
                    <option value="auto">Auto profile</option>
                    <option value="general">General</option>
                    <option value="sbi_calibration">SBI calibration example</option>
                  </select>
                  <button
                      onClick={() =>
                        loadAnalysis("analyze_library_topic", {
                          library_id: selectedLibrary.id,
                          topic: topicValue || "calibration",
                        })
                      }
                      disabled={busy}
                    >
                      Analyze topic
                    </button>
                    <button
                      onClick={() =>
                        loadAnalysis("search_library_evidence", {
                          library_id: selectedLibrary.id,
                          query: topicValue || "calibration",
                          max_hits: 8,
                        })
                      }
                      disabled={busy}
                    >
                      Search evidence
                    </button>
                </div>
                <div className="tableWrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Pick</th>
                        <th>Rank</th>
                        <th>Title</th>
                        <th>Source</th>
                        <th>Tags</th>
                        <th>Fav</th>
                        <th>State</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.id} className={selectedItemIds.includes(item.id) ? "rowSelected" : ""}>
                          <td>
                            <input
                              type="checkbox"
                              checked={selectedItemIds.includes(item.id)}
                              onChange={() => toggleSelectedItem(item.id)}
                            />
                          </td>
                          <td>{item.rank}</td>
                          <td>
                            <div className="titleCell">{item.effective_title}</div>
                            {item.doi ? <div className="subtle">{item.doi}</div> : null}
                          </td>
                          <td>{item.source}</td>
                          <td>{(item.tags || []).join(", ")}</td>
                          <td>{item.favorite ? "★" : ""}</td>
                          <td>{item.archived ? "archived" : "active"}</td>
                          <td>
                            <div className="rowActions">
                              <button
                                onClick={() =>
                                  mutateTool("update_library_item", {
                                    item_id: item.id,
                                    favorite: !item.favorite,
                                  })
                                }
                                disabled={busy}
                              >
                                {item.favorite ? "Unfav" : "Fav"}
                              </button>
                              <button
                                onClick={() =>
                                  mutateTool(item.archived ? "restore_library_item" : "archive_library_item", {
                                    item_id: item.id,
                                  })
                                }
                                disabled={busy}
                              >
                                {item.archived ? "Restore" : "Archive"}
                              </button>
                              <button
                                onClick={() =>
                                  loadAnalysis("ingest_library_item", {
                                    item_id: item.id,
                                    include_forums: true,
                                    reingest: false,
                                  })
                                }
                                disabled={busy}
                              >
                                Ingest
                              </button>
                              <button
                                onClick={() =>
                                  loadAnalysis("summarize_library_item", {
                                    item_id: item.id,
                                    topic: topicValue || null,
                                  })
                                }
                                disabled={busy}
                              >
                                Analyze
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel sidePanel">
                <div className="panelHeader">
                  <h3>Context bundles</h3>
                  <button
                    onClick={() =>
                      mutateTool(
                        "generate_context_bundle",
                        { library_id: selectedLibrary.id, mode: "compact", max_items: 12 },
                        async (result) => {
                          setSelectedBundle(result);
                          await refresh(selectedLibrary.id);
                        }
                      )
                    }
                    disabled={busy}
                  >
                    Generate compact
                  </button>
                </div>
                <div className="bundleList">
                  {bundles.map((bundle) => (
                    <button
                      key={bundle.id}
                      className="bundleCard"
                      onClick={() =>
                        mutateTool("read_context_bundle", { bundle_id: bundle.id }, async (result) => {
                          setSelectedBundle(result);
                        })
                      }
                    >
                      <strong>{bundle.name}</strong>
                      <span>{bundle.item_count} items</span>
                    </button>
                  ))}
                </div>
                {selectedBundle?.text ? (
                  <div className="bundlePreview">
                    <div className="panelHeader compact">
                      <h4>Preview</h4>
                      <div className="rowActions">
                        <button
                          onClick={() => navigator.clipboard.writeText(selectedBundle.text)}
                        >
                          Copy
                        </button>
                        {window.openai?.sendFollowUpMessage ? (
                          <button
                            onClick={() =>
                              window.openai.sendFollowUpMessage({
                                prompt: selectedBundle.text,
                                scrollToBottom: true,
                              })
                            }
                          >
                            Insert into chat
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <pre>{selectedBundle.text}</pre>
                  </div>
                ) : (
                  <div className="empty">Generate a bundle to preview context injection.</div>
                )}
                {analysisResult?.summary ? (
                  <div className="bundlePreview">
                    <div className="panelHeader compact">
                      <h4>Analysis</h4>
                      <div className="rowActions">
                        <button onClick={() => navigator.clipboard.writeText(analysisResult.summary)}>Copy</button>
                        {analysisResult.report_path ? <span className="subtle">{analysisResult.report_path}</span> : null}
                      </div>
                    </div>
                    <pre>{analysisResult.summary + "\n\n" + (analysisResult.key_points || []).map((p) => `- ${p}`).join("\n")}</pre>
                    {analysisResult.structured_payload?.comparison_matrix?.length ? (
                      <div className="structuredPanel">
                        <div className="subtle">
                          requested profile={analysisResult.structured_payload.requested_profile || analysisResult.structured_payload.profile || "n/a"} | resolved profile={analysisResult.structured_payload.resolved_profile || analysisResult.structured_payload.profile || "n/a"}
                        </div>
                        <h4>Comparison matrix</h4>
                        <div className="tableWrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Paper</th>
                                <th>Method</th>
                                <th>Protocol</th>
                                <th>Limitations</th>
                              </tr>
                            </thead>
                            <tbody>
                              {analysisResult.structured_payload.comparison_matrix.slice(0, 8).map((row, index) => (
                                <tr key={`${row.title}-${index}`}>
                                  <td>{row.title}</td>
                                  <td>{row.method}</td>
                                  <td>{row.calibration_protocol}</td>
                                  <td>{row.limitations}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}
                    {analysisResult.structured_payload?.method_cards?.length ? (
                      <div className="structuredPanel">
                        <h4>Method cards</h4>
                        <div className="cardStack">
                          {analysisResult.structured_payload.method_cards.slice(0, 6).map((card) => (
                            <div key={card.item_id} className="methodCard">
                              <strong>{card.title}</strong>
                              <p>{card.method}</p>
                              <div className="subtle">Failure modes: {card.failure_modes}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {analysisResult.structured_payload?.claim_evidence_graph?.claims?.length ? (
                      <div className="structuredPanel">
                        <h4>Claim/evidence graph</h4>
                        <div className="subtle">
                          {analysisResult.structured_payload.claim_evidence_graph.claims.length} claims linked to{" "}
                          {analysisResult.structured_payload.claim_evidence_graph.edges?.length || 0} evidence edges.
                        </div>
                      </div>
                    ) : null}
                    {(analysisResult.evidence || []).length ? (
                      <div className="evidenceList">
                        {(analysisResult.evidence || []).map((ev) => (
                          <div key={ev.id} className="evidenceCard">
                            <strong>{ev.source_type}</strong>
                            <div className="subtle">
                              confidence={textValue(ev.confidence_score, "")}
                              {ev.relevance_score != null ? ` | relevance=${ev.relevance_score}` : ""}
                            </div>
                            <div>{ev.title || ev.url || ev.excerpt}</div>
                            {ev.metadata?.semantic_backend ? (
                              <div className="subtle">
                                lexical={textValue(ev.metadata.lexical_score, "")} | semantic={textValue(ev.metadata.semantic_score, "")} | backend={ev.metadata.semantic_backend}
                              </div>
                            ) : null}
                            {ev.url ? (
                              <a href={ev.url} target="_blank" rel="noreferrer">
                                Open source
                              </a>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {analysisReports.length ? (
                  <div className="bundlePreview">
                    <div className="panelHeader compact">
                      <h4>Saved reports</h4>
                    </div>
                    <div className="bundleList">
                      {analysisReports.slice(0, 8).map((report) => (
                        <button
                          key={report.id}
                          className="bundleCard"
                          onClick={() =>
                            mutateTool("read_analysis_report", { report_id: report.id }, async (result) => {
                              setAnalysisResult({
                                status: result.status,
                                report_id: result.report?.id,
                                report_path: result.report?.report_path,
                                title: result.report?.title,
                                analysis_mode: result.report?.analysis_mode,
                                compute_backend: result.report?.compute_backend,
                                topic: result.report?.topic,
                                summary: result.summary,
                                key_points: result.key_points || [],
                                evidence: result.evidence || [],
                                structured_payload: result.structured_payload || {},
                              });
                            })
                          }
                        >
                          <strong>{report.analysis_kind}</strong>
                          <span>{report.title}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
