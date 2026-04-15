# 使用示例

## 最小搜索

```bash
scibudy search "simulation-based calibration"
```

## 建立本地文献库

```bash
scibudy collect "simulation-based calibration" --target-dir ~/Desktop/sbc-library
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
Use search_literature to find recent papers on simulation-based calibration, then organize the strongest ones into a local library.
```
