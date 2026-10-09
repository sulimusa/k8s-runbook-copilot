from runbook_copilot.ingest.chunk import chunk_document
from runbook_copilot.ingest.parse import parse_markdown

RAW = """---
title: Debug Pods
weight: 10
---
<!-- overview -->
{{< note >}}
Keep calm.
{{< /note >}}
Use {{< glossary_tooltip text="Pods" term_id="pod" >}} wisely.

## Section A
""" + "word " * 80 + """

```bash
# not a heading
kubectl get pods
```

## Section B
tiny

## Section C
""" + "text " * 90


def test_parse_strips_shortcodes_and_reads_title():
    d = parse_markdown(RAW, "tasks/debug.md")
    assert d.title == "Debug Pods"
    assert "{{" not in d.body and "<!--" not in d.body
    assert "Use Pods wisely." in d.body


def test_chunk_headings_ids_and_fence():
    d = parse_markdown(RAW, "tasks/debug.md")
    cs = chunk_document(d, source_id="k8s-docs", url="u", license="CC-BY-4.0", commit_sha="s", min_words=30)
    assert cs[0].chunk_id == "k8s-docs:tasks/debug#00"
    assert all(c.chunk_id.startswith("k8s-docs:tasks/debug#") for c in cs)
    joined = "\n".join(c.text for c in cs)
    assert "# not a heading" in joined  # fenced comment was not treated as a heading
    assert any("Section A" in c.heading_path for c in cs)
    # the tiny "Section B" is merged into a neighbour, not emitted alone
    assert not any(c.text.strip() in ("## Section B\ntiny",) for c in cs)


def test_big_section_is_split():
    body = "## Big\n" + "\n\n".join(["paragraph " * 100 for _ in range(6)])
    d = parse_markdown(body, "x.md")
    cs = chunk_document(d, source_id="s", url="u", license="l", commit_sha="c", max_words=250)
    assert len(cs) >= 3
    assert all(len(c.text.split()) <= 500 for c in cs)
