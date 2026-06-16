# doc-chunk-viewer

本机调试 UI：上传 Word/PDF → doc_chunk pipeline → 左侧 outline 树 + 右侧章节 Markdown。

## 安装

```bash
cd tender_skills
pip install -e ".[dev]"
pip install -e "./viewer[dev]"
```

## 启动

```bash
python -m viewer
# → http://127.0.0.1:8765
```

环境变量 `DOC_CHUNK_VIEWER_DATA` 可覆盖数据目录（默认 `~/.doc-chunk-viewer/`）。
