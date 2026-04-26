from pathlib import Path

from src.ingest.chunker import chunk_law

FIXTURE = Path(__file__).parent / "fixtures" / "sample_law.xml"


def test_chunk_law_emits_one_chunk_per_article() -> None:
    xml = FIXTURE.read_text(encoding="utf-8")
    chunks = chunk_law(xml)

    assert len(chunks) == 2
    assert chunks[0].article_no == "第一条"
    assert chunks[0].article_title == "（基本原則）"
    assert "信義に従い誠実" in chunks[0].body
    assert chunks[0].token_count > 0

    assert chunks[1].article_no == "第七百九条"
    assert chunks[1].article_title == "（不法行為による損害賠償）"
    assert "損害を賠償する責任" in chunks[1].body


def test_chunk_law_skips_articles_with_no_body() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Law>
  <LawBody>
    <MainProvision>
      <Article Num="1"><ArticleTitle>第一条</ArticleTitle></Article>
      <Article Num="2">
        <ArticleTitle>第二条</ArticleTitle>
        <Paragraph><ParagraphSentence><Sentence>本則。</Sentence></ParagraphSentence></Paragraph>
      </Article>
    </MainProvision>
  </LawBody>
</Law>
"""
    chunks = chunk_law(xml)
    # 第一条 has no Paragraph body → skipped (only ArticleTitle text); 第二条 kept
    titles = [c.article_no for c in chunks]
    assert "第二条" in titles
