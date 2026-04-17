from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


FRONTEND_ARTIFACT_TYPES = {"interactive", "mermaid", "image", "table", "markdown", "code", "html", "json"}


def normalize_response_contract(payload: dict[str, Any]) -> dict[str, Any]:
    citations = [normalize_citation(citation) for citation in payload.get("citations", [])]
    artifacts = [
        normalize_artifact(artifact, index=index)
        for index, artifact in enumerate(payload.get("artifacts", []), start=1)
    ]
    artifacts = _validate_image_artifacts(artifacts, citations)
    normalized = {
        "answer_markdown": str(payload.get("answer_markdown", "") or ""),
        "citations": citations,
        "artifacts": artifacts,
        "tool_results": payload.get("tool_results", {}) if isinstance(payload.get("tool_results", {}), dict) else {},
        "safety_flags": _normalize_flags(payload.get("safety_flags", [])),
    }
    for key, value in payload.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def _validate_image_artifacts(
    artifacts: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for art in artifacts:
        if art.get("type") != "image":
            kept.append(art)
            continue
        url = str(art.get("content", ""))
        if _image_exists(url):
            kept.append(art)
            continue
        repaired = _repair_image_from_citations(citations)
        if repaired:
            art["content"] = repaired
            kept.append(art)
        # else: drop broken image silently (logged via tool_results if needed)
    return kept


def _image_exists(url: str) -> bool:
    if not url or url.startswith(("http://", "https://")):
        return bool(url)
    rel = url.lstrip("/")
    if rel.startswith("knowledge/"):
        rel = rel[len("knowledge/"):]
    candidate = (_PROJECT_ROOT / rel).resolve()
    try:
        candidate.relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        return False
    return candidate.is_file()


def _repair_image_from_citations(citations: list[dict[str, Any]]) -> str | None:
    for c in citations:
        page_image = c.get("page_image")
        if page_image:
            url = _image_url(page_image)
            if _image_exists(url):
                return url
    return None


def citation_from_search_result(result: dict[str, Any]) -> dict[str, Any]:
    return normalize_citation(
        {
            "doc_id": result.get("doc_id"),
            "source_doc": result.get("source_doc"),
            "page": result.get("page"),
            "element_id": result.get("element_id"),
            "source_kind": result.get("source_kind"),
            "page_image": result.get("page_image"),
            "target_path": result.get("target_path"),
            "avg_confidence": result.get("avg_confidence"),
            "excerpt": result.get("text"),
        }
    )


def citation_from_source_ref(source_ref: dict[str, Any], **extras: Any) -> dict[str, Any]:
    return normalize_citation({**source_ref, **extras})


def manual_image_artifact(image: dict[str, Any]) -> dict[str, Any]:
    source_ref = image.get("source_ref", {})
    title = str(image.get("title", "Manual Image"))
    summary = str(image.get("description") or f"Relevant manual image from {source_ref.get('source_doc', 'manual')}.")
    url = _image_url(image.get("path"))
    return normalize_artifact(
        {
            "type": "image",
            "title": title,
            "summary": summary,
            "content": url,
            "source_ref": citation_from_source_ref(
                source_ref,
                source_kind="visual",
                page_image=image.get("path"),
            )
            if source_ref
            else None,
        },
        index=1,
    )


def duty_cycle_artifact(result: dict[str, Any], process: str) -> dict[str, Any]:
    headers = ["Process", "Input Voltage", "Amperage", "Duty Cycle"]
    rows = [[process, result.get("input_voltage", ""), f"{result.get('amperage', '')}A", f"{result.get('duty_cycle_percent', '')}%"]]
    content = json.dumps({"headers": headers, "rows": rows})
    source_ref = result.get("source_ref", {})
    return normalize_artifact(
        {
            "type": "table",
            "title": f"{process} duty cycle",
            "summary": f"{process} at {result.get('amperage')}A on {result.get('input_voltage')}",
            "content": content,
            "source_ref": citation_from_source_ref(source_ref, source_kind="table") if source_ref else None,
        },
        index=1,
    )


def normalize_citation(citation: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in ["doc_id", "source_doc", "page", "element_id"]:
        value = citation.get(key)
        if value is not None:
            normalized[key] = value
    for key in ["source_kind", "page_image", "target_path", "excerpt"]:
        value = citation.get(key)
        if value:
            normalized[key] = value
    avg_confidence = citation.get("avg_confidence")
    if avg_confidence is not None:
        normalized["avg_confidence"] = avg_confidence
    return normalized


def normalize_artifact(artifact: dict[str, Any], *, index: int) -> dict[str, Any]:
    raw_type = str(artifact.get("type", "markdown"))
    artifact_type = _coerce_type(raw_type)
    title = str(artifact.get("title", "Artifact"))
    summary = str(artifact.get("summary", title))
    content = _coerce_content(artifact, artifact_type)
    normalized: dict[str, Any] = {
        "id": str(artifact.get("id") or _artifact_id(artifact_type, title, index)),
        "type": artifact_type,
        "title": title,
        "summary": summary,
        "content": content,
    }
    language = artifact.get("language")
    if language:
        normalized["language"] = str(language)
    source_ref = artifact.get("source_ref")
    if isinstance(source_ref, dict):
        normalized["source_ref"] = normalize_citation(source_ref)
    return normalized


def _coerce_type(raw_type: str) -> str:
    mapping = {
        "manual_image": "image",
        "setup_diagram": "image",
        "duty_cycle_result": "table",
        "troubleshooting_flow": "mermaid",
        "interactive_html": "interactive",
    }
    if raw_type in FRONTEND_ARTIFACT_TYPES:
        return raw_type
    return mapping.get(raw_type, "markdown")


def _coerce_content(artifact: dict[str, Any], artifact_type: str) -> str:
    content = artifact.get("content")
    if isinstance(content, str) and content:
        if artifact_type == "image":
            return _image_url(content)
        return content
    if isinstance(content, (dict, list)):
        return json.dumps(content)
    payload = artifact.get("payload")
    if isinstance(payload, dict):
        if artifact_type == "image":
            path = payload.get("path") or payload.get("image_path") or payload.get("url")
            return _image_url(path) if path else ""
        if artifact_type == "table":
            if "headers" in payload and "rows" in payload:
                return json.dumps({"headers": payload["headers"], "rows": payload["rows"]})
            return json.dumps(payload)
        if artifact_type == "mermaid":
            return str(payload.get("source") or payload.get("mermaid") or "")
        return json.dumps(payload)
    if payload is not None:
        return str(payload)
    return ""


def _image_url(path: Any) -> str:
    if not path:
        return ""
    value = str(path)
    if value.startswith(("http://", "https://", "/knowledge/", "/images/")):
        return value
    return f"/knowledge/{value.lstrip('/')}"


def _normalize_flags(flags: Any) -> list[str]:
    if not isinstance(flags, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in flags:
        if not isinstance(value, str):
            continue
        flag = value.strip()
        if not flag or flag in seen:
            continue
        seen.add(flag)
        result.append(flag)
    return result


def _artifact_id(artifact_type: str, title: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"artifact-{index}"
    return f"{artifact_type}:{slug}:{index}"
