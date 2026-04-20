# 使用示例

## 最小搜索

```bash
scibudy search "simulation-based calibration"
```

## 建立本地文献库

```bash
scibudy collect "simulation-based calibration" --target-dir ~/Desktop/sbc-library
```

## Agent 工作流

当 Codex 或其他 agent 需要一次性完成检索、建库、可选 ingest 和 synthesis 时使用：

```bash
scibudy workflow "calibration methods in simulation-based inference" \
  --mode general \
  --limit 50 \
  --topic "calibration in simulation-based inference"
```

## 做主题分析

```bash
scibudy ingest-library <library_id>
scibudy analyze-topic <library_id> calibration
```

## 搜索证据

```bash
scibudy search-evidence <library_id> "posterior coverage"
```

## 打开本地界面

```bash
scibudy ui --open
```

## Codex 提示词示例

```text
Use research_workflow with query="calibration methods in simulation-based inference", mode="general", limit=50, synthesize=true.
```
