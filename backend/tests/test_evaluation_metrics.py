from evaluation.evaluate import (
    answer_keyword_coverage,
    citation_is_relevant,
    collect_documents,
    citation_accuracy,
    fact_numbers,
    faithfulness,
    retrieval_hit,
)


CASE = {
    "expected_answer_keywords": ["7天退货", "15天换货"],
    "expected_evidence_keywords": ["7天退货", "15天换货"],
    "expected_pages": [3],
}


def test_retrieval_and_citation_metrics_use_expected_evidence():
    citations = [
        {"page_number": 3, "excerpt": "商城通常提供7天退货、15天换货。"},
        {"page_number": 1, "excerpt": "汇编封面。"},
    ]

    assert retrieval_hit(citations, "通常支持7天退货和15天换货。", CASE) == 1
    assert citation_accuracy(citations, CASE) == 0.5
    assert answer_keyword_coverage("通常支持7天退货和15天换货。", CASE) == 1


def test_faithfulness_penalizes_unsupported_fact_number():
    citations = [{"page_number": 3, "excerpt": "商城通常提供7天退货、15天换货。"}]

    supported = faithfulness("商城支持7天退货和15天换货。", citations, CASE)
    unsupported = faithfulness("商城支持30天退货和15天换货。", citations, CASE)

    assert supported > unsupported


def test_unanswerable_case_rewards_clear_insufficiency():
    case = {
        "expected_answer_keywords": [],
        "expected_evidence_keywords": [],
        "expected_pages": [],
        "expected_behavior": "insufficient",
    }

    assert retrieval_hit([], "资料未提供所有手机终身免费维修的承诺。", case) == 1
    assert faithfulness("现有资料不足，无法确认。", [], case) == 1
    assert citation_accuracy([], case) is None


def test_citation_relevance_requires_expected_document():
    case = {
        "expected_documents": ["orders.docx"],
        "expected_evidence_keywords": ["不能修改地址"],
        "expected_pages": [],
    }

    assert citation_is_relevant(
        {"filename": "orders.docx", "page_number": None, "excerpt": "不能修改地址"}, case
    )
    assert not citation_is_relevant(
        {"filename": "other.docx", "page_number": None, "excerpt": "不能修改地址"}, case
    )


def test_collect_documents_from_directory(tmp_path):
    (tmp_path / "a.docx").write_bytes(b"PK")
    (tmp_path / "b.md").write_text("body", encoding="utf-8")
    (tmp_path / "ignored.exe").write_bytes(b"no")

    documents = collect_documents([], tmp_path)

    assert [path.name for path in documents] == ["a.docx", "b.md"]


def test_fact_numbers_ignore_source_reference_ids():
    assert fact_numbers("支持7天退货【656853205201749†L152-L168】[Source 2]") == {"7天"}
