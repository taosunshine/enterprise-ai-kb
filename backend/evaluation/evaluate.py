from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import settings

INSUFFICIENT_MARKERS = (
    "资料不足",
    "无法确认",
    "无法依据",
    "未提供",
    "没有提供",
    "没有关于",
    "没有提及",
    "不包含",
    "未包含",
    "未说明",
)
METRIC_VERSION = "2.1"
SUPPORTED_DOCUMENT_SUFFIXES = {
    ".pdf",
    ".docx",
    ".md",
    ".txt",
    ".csv",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".html": "text/html",
    ".htm": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
STOP_TOKENS = {
    "什么",
    "哪些",
    "如何",
    "分别",
    "以及",
    "提供",
    "支持",
    "华为",
    "资料",
    "根据",
    "问题",
    "回答",
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def tokens(text: str) -> set[str]:
    normalized = normalize(text)
    values = set(re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", normalized))
    values.update(re.findall(r"\d+(?:\.\d+)?(?:万|亿|天|年|个|小时|工作日)?", normalized))
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        values.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return {value for value in values if value not in STOP_TOKENS}


def contains_any(text: str, values: list[str]) -> bool:
    normalized = normalize(text)
    return any(normalize(value) in normalized for value in values)


def citation_is_relevant(citation: dict, case: dict) -> bool:
    page_hit = citation.get("page_number") in case.get("expected_pages", [])
    evidence_hit = contains_any(citation.get("excerpt", ""), case.get("expected_evidence_keywords", []))
    expected_documents = case.get("expected_documents", [])
    document_hit = not expected_documents or citation.get("filename") in expected_documents
    return document_hit and (page_hit or evidence_hit)


def retrieval_hit(citations: list[dict], answer: str, case: dict) -> float:
    if case.get("expected_behavior") == "insufficient":
        return float(contains_any(answer, list(INSUFFICIENT_MARKERS)))
    return float(any(citation_is_relevant(citation, case) for citation in citations))


def citation_accuracy(citations: list[dict], case: dict) -> float | None:
    if case.get("expected_behavior") == "insufficient":
        return None
    if not citations:
        return 0.0
    relevant = sum(citation_is_relevant(citation, case) for citation in citations)
    return relevant / len(citations)


def answer_keyword_coverage(answer: str, case: dict) -> float | None:
    expected = case.get("expected_answer_keywords", [])
    if not expected:
        return None
    normalized = normalize(answer)
    return sum(normalize(keyword) in normalized for keyword in expected) / len(expected)


def fact_numbers(text: str) -> set[str]:
    without_references = re.sub(r"【[^】]*】|\[Source\s+\d+\]", "", text, flags=re.IGNORECASE)
    normalized = normalize(without_references)
    values = set(re.findall(r"\d+(?:\.\d+)?(?:万|亿|天|年|个|小时|工作日)", normalized))
    values.update(re.findall(r"(?<![\d.])\d{5,}(?![\d.])", normalized))
    return values


def faithfulness(answer: str, citations: list[dict], case: dict) -> float:
    if case.get("expected_behavior") == "insufficient":
        return float(contains_any(answer, list(INSUFFICIENT_MARKERS)))
    if not any(citation_is_relevant(citation, case) for citation in citations):
        return 0.0
    coverage = answer_keyword_coverage(answer, case) or 0.0
    reference = " ".join(
        case.get("expected_answer_keywords", []) + case.get("expected_evidence_keywords", [])
    )
    answer_numbers = fact_numbers(answer)
    reference_numbers = fact_numbers(reference)
    number_precision = (
        len(answer_numbers & reference_numbers) / len(answer_numbers) if answer_numbers else 1.0
    )
    return coverage * 0.75 + number_precision * 0.25


def mean(values: list[float | None]) -> float:
    included = [value for value in values if value is not None]
    return sum(included) / len(included) if included else 0.0


def summarize_results(results: list[dict]) -> dict:
    return {
        "case_count": len(results),
        "retrieval_hit_rate": mean([item["scores"]["retrieval_hit"] for item in results]),
        "citation_accuracy": mean([item["scores"]["citation_accuracy"] for item in results]),
        "faithfulness": mean([item["scores"]["faithfulness"] for item in results]),
        "answer_keyword_coverage": mean(
            [item["scores"]["answer_keyword_coverage"] for item in results]
        ),
        "average_latency_seconds": mean([item["latency_seconds"] for item in results]),
    }


def summarize_rounds(round_summaries: list[dict]) -> dict:
    metrics = (
        "retrieval_hit_rate",
        "citation_accuracy",
        "faithfulness",
        "answer_keyword_coverage",
        "average_latency_seconds",
    )
    return {
        "round_count": len(round_summaries),
        "case_count": round_summaries[0]["case_count"],
        **{
            metric: {
                "average": mean([summary[metric] for summary in round_summaries]),
                "minimum": min(summary[metric] for summary in round_summaries),
                "maximum": max(summary[metric] for summary in round_summaries),
                "range": max(summary[metric] for summary in round_summaries)
                - min(summary[metric] for summary in round_summaries),
            }
            for metric in metrics
        },
    }


def authenticate(client: httpx.Client, email: str | None, password: str) -> tuple[str, str]:
    if email:
        response = client.post("/auth/login", json={"email": email, "password": password})
        response.raise_for_status()
        return response.json()["access_token"], email
    email = f"rag-eval-{uuid4().hex[:12]}@example.com"
    response = client.post("/auth/register", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"], email


def post_with_rate_limit_retry(
    client: httpx.Client,
    url: str,
    *,
    attempts: int = 3,
    **kwargs,
) -> httpx.Response:
    for attempt in range(attempts):
        response = client.post(url, **kwargs)
        if response.status_code != 429 or attempt == attempts - 1:
            return response
        time.sleep(max(1, int(response.headers.get("Retry-After", "1"))))
    return response


def prepare_knowledge_base(
    client: httpx.Client,
    headers: dict[str, str],
    knowledge_base_id: int | None,
    documents: list[Path],
) -> int:
    if knowledge_base_id:
        return knowledge_base_id
    if not documents:
        raise ValueError("--document or --documents-dir is required when --knowledge-base-id is not provided")
    created = client.post(
        "/knowledge-bases",
        headers=headers,
        json={"name": "企业 RAG 持续评估", "description": "自动创建的隔离评估知识库"},
    )
    created.raise_for_status()
    knowledge_base_id = created.json()["id"]
    document_ids = []
    for document in documents:
        with document.open("rb") as file:
            uploaded = post_with_rate_limit_retry(
                client,
                f"/documents/upload?knowledge_base_id={knowledge_base_id}",
                headers=headers,
                files={
                    "file": (
                        document.name,
                        file,
                        CONTENT_TYPES.get(document.suffix.lower(), "application/octet-stream"),
                    )
                },
            )
        uploaded.raise_for_status()
        document_ids.append(uploaded.json()["id"])
    for _ in range(max(120, len(document_ids) * 60)):
        listed = client.get(
            f"/documents?knowledge_base_id={knowledge_base_id}", headers=headers
        )
        listed.raise_for_status()
        items = {item["id"]: item for item in listed.json() if item["id"] in document_ids}
        failed = [item for item in items.values() if item["status"] == "failed"]
        if failed:
            item = failed[0]
            raise RuntimeError(
                f"Document processing failed for {item['filename']}: {item['error_message']}"
            )
        if len(items) == len(document_ids) and all(item["status"] == "ready" for item in items.values()):
            return knowledge_base_id
        time.sleep(1)
    raise TimeoutError("Document processing did not finish before the evaluation timeout")


def collect_documents(document_args: list[Path], documents_dir: Path | None) -> list[Path]:
    documents = [path.resolve() for path in document_args]
    if documents_dir:
        documents.extend(
            sorted(
                path.resolve()
                for path in documents_dir.iterdir()
                if path.is_file() and path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES
            )
        )
    unique = list(dict.fromkeys(documents))
    invalid = [path for path in unique if not path.is_file() or path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES]
    if invalid:
        raise ValueError(f"Unsupported or missing documents: {', '.join(map(str, invalid))}")
    return unique


def evaluate_case(client: httpx.Client, headers: dict[str, str], kb_id: int, case: dict) -> dict:
    started = time.perf_counter()
    response = post_with_rate_limit_retry(
        client,
        "/chat/ask",
        headers=headers,
        json={"knowledge_base_id": kb_id, "question": case["question"]},
    )
    response.raise_for_status()
    payload = response.json()
    citations = payload["citations"]
    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "answer": payload["answer"],
        "citations": citations,
        "latency_seconds": round(time.perf_counter() - started, 3),
        "scores": {
            "retrieval_hit": retrieval_hit(citations, payload["answer"], case),
            "citation_accuracy": citation_accuracy(citations, case),
            "faithfulness": faithfulness(payload["answer"], citations, case),
            "answer_keyword_coverage": answer_keyword_coverage(payload["answer"], case),
        },
    }


def markdown_report(report: dict) -> str:
    summary = report["summary"]
    def metric(name: str) -> dict:
        return summary[name]

    lines = [
        f"# RAG 评估报告：{report['dataset']['name']}",
        "",
        f"- 时间：{report['created_at']}",
        f"- 轮次：{summary['round_count']}；每轮问题数：{summary['case_count']}",
        f"- 检索命中率：平均 {metric('retrieval_hit_rate')['average']:.1%}；"
        f"最低 {metric('retrieval_hit_rate')['minimum']:.1%}",
        f"- 引用准确率：平均 {metric('citation_accuracy')['average']:.1%}；"
        f"最低 {metric('citation_accuracy')['minimum']:.1%}",
        f"- 回答忠实度：平均 {metric('faithfulness')['average']:.1%}；"
        f"最低 {metric('faithfulness')['minimum']:.1%}",
        f"- 答案关键词覆盖率：平均 {metric('answer_keyword_coverage')['average']:.1%}",
        f"- 回答延迟：平均 {metric('average_latency_seconds')['average']:.2f}s；"
        f"最高 {metric('average_latency_seconds')['maximum']:.2f}s",
    ]
    if report.get("trend"):
        trend = report["trend"]
        lines.extend(
            [
                f"- 相比上次命中率变化：{trend['retrieval_hit_rate']:+.1%}",
                f"- 相比上次引用准确率变化：{trend['citation_accuracy']:+.1%}",
                f"- 相比上次忠实度变化：{trend['faithfulness']:+.1%}",
            ]
        )
    lines.extend(
        [
        "",
        "| 问题 | 分类 | 命中 | 引用准确率 | 忠实度 | 关键词覆盖 |",
        "|---|---|---:|---:|---:|---:|",
        ]
    )
    for item in report["rounds"][-1]["results"]:
        scores = item["scores"]
        citation = scores["citation_accuracy"]
        coverage = scores["answer_keyword_coverage"]
        citation_text = f"{citation:.0%}" if citation is not None else "N/A"
        coverage_text = f"{coverage:.0%}" if coverage is not None else "N/A"
        lines.append(
            f"| {item['question']} | {item['category']} | {scores['retrieval_hit']:.0%} | "
            f"{citation_text} | {scores['faithfulness']:.0%} | {coverage_text} |"
        )
    return "\n".join(lines) + "\n"


def previous_summary(output_dir: Path) -> dict | None:
    for report_path in reversed(sorted(output_dir.glob("rag-eval-*.json"))):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("metric_version") == METRIC_VERSION:
                return report["summary"]
        except (KeyError, json.JSONDecodeError):
            continue
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the enterprise RAG evaluation set.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "datasets" / "huawei_public_2026_06_13.json")
    parser.add_argument("--document", type=Path, action="append", default=[])
    parser.add_argument("--documents-dir", type=Path)
    parser.add_argument("--email")
    parser.add_argument("--password", default="Evaluation123!")
    parser.add_argument("--knowledge-base-id", type=int)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "reports")
    parser.add_argument("--fail-under", action="store_true")
    parser.add_argument("--rounds", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    documents = collect_documents(args.document, args.documents_dir)
    with httpx.Client(base_url=args.base_url, timeout=180) as client:
        token, email = authenticate(client, args.email, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        kb_id = prepare_knowledge_base(client, headers, args.knowledge_base_id, documents)
        rounds = []
        for round_number in range(1, args.rounds + 1):
            results = [
                evaluate_case(client, headers, kb_id, case)
                for case in dataset["cases"]
            ]
            rounds.append(
                {
                    "round": round_number,
                    "summary": summarize_results(results),
                    "results": results,
                }
            )
    summary = summarize_rounds([item["summary"] for item in rounds])
    previous = previous_summary(args.output_dir)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "metric_version": METRIC_VERSION,
        "dataset": {
            "name": dataset["name"],
            "version": dataset["version"],
            "documents": [path.name for path in documents],
        },
        "target": {"base_url": args.base_url, "email": email, "knowledge_base_id": kb_id},
        "configuration": {
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "rerank_provider": settings.rerank_provider,
            "rerank_model": settings.rerank_model,
            "retrieval_top_k": settings.retrieval_top_k,
            "rerank_top_k": settings.rerank_top_k,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
        },
        "summary": summary,
        "rounds": rounds,
    }
    if previous:
        report["trend"] = {
            metric: summary[metric]["average"] - previous[metric]["average"]
            for metric in ("retrieval_hit_rate", "citation_accuracy", "faithfulness")
        }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = args.output_dir / f"rag-eval-{stamp}.json"
    markdown_path = args.output_dir / f"rag-eval-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"summary": summary, "json_report": str(json_path), "markdown_report": str(markdown_path)}, ensure_ascii=False, indent=2))
    if args.fail_under:
        thresholds = dataset.get(
            "thresholds",
            {
                "retrieval_hit_rate": 0.90,
                "citation_accuracy": 0.80,
                "faithfulness": 0.80,
                "maximum_average_latency_seconds": 15,
            },
        )
        passed = (
            summary["retrieval_hit_rate"]["minimum"] >= thresholds["retrieval_hit_rate"]
            and summary["citation_accuracy"]["minimum"] >= thresholds["citation_accuracy"]
            and summary["faithfulness"]["minimum"] >= thresholds["faithfulness"]
            and summary["average_latency_seconds"]["maximum"]
            <= thresholds["maximum_average_latency_seconds"]
        )
        return 0 if passed else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
