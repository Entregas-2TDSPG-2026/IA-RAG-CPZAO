"""Coleta páginas públicas da disciplina e gera o índice vetorial do RAG."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

SITE_ROOT = "https://arnaldojr.github.io/DisruptiveArchitectures/"
SITEMAP_URL = SITE_ROOT + "sitemap.xml"
AI_PATH_PREFIXES = (
    "/DisruptiveArchitectures/aulas/IA/",
    "/DisruptiveArchitectures/aulas/genAI/",
)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_PATH = DATA_DIR / "corpus.json"
INDEX_PATH = Path(os.getenv("RAG_INDEX_PATH", DATA_DIR / "index.json"))
CONTENT_TAGS = {"h1", "h2", "h3", "h4", "p", "li", "pre", "tr", "blockquote"}
MAX_CHARS = 1450
OVERLAP_CHARS = 180
EMBED_BATCH_SIZE = 16
# Cada lote pode consumir cota por item de entrada (até 16 itens), não apenas
# por chamada HTTP. Mantém a taxa aproximada abaixo de 80 embeddings/minuto.
EMBED_MIN_INTERVAL_SECONDS = 12.0
EMBED_MAX_RETRIES = 8


def allowed_page(url: str) -> bool:
    parsed = urlparse(url)
    root = urlparse(SITE_ROOT)
    return (
        parsed.scheme == "https"
        and parsed.netloc == root.netloc
        and parsed.path.startswith(root.path)
        and (parsed.path.endswith("/") or parsed.path.endswith(".html"))
    )


def is_ai_page(url: str) -> bool:
    """Limita a base aos materiais de IA e IA generativa da disciplina."""
    path = urlparse(url).path.lower()
    return any(path.startswith(prefix.lower()) for prefix in AI_PATH_PREFIXES)


def fetch_sitemap(client: httpx.Client, url: str = SITEMAP_URL) -> list[str]:
    response = client.get(url)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    urls: list[str] = []
    for element in root.iter():
        if not element.tag.endswith("loc") or not element.text:
            continue
        location = element.text.strip()
        if location.endswith(".xml") and location.startswith(SITE_ROOT):
            urls.extend(fetch_sitemap(client, location))
        elif allowed_page(location) and is_ai_page(location):
            urls.append(urldefrag(location).url)
    return list(dict.fromkeys(urls))


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one(".md-content__inner") or soup.select_one("article")
    if article is None:
        return None
    for node in article.select(
        "script, style, nav, form, .headerlink, .md-content__button, "
        ".md-source-file, .md-feedback, .md-nav, .footnote-backref"
    ):
        node.decompose()
    title_node = article.find("h1")
    title = clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
    if not title:
        title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else url

    blocks: list[dict[str, str]] = []
    heading = title
    for node in article.find_all(CONTENT_TAGS):
        if not isinstance(node, Tag):
            continue
        if node.find_parent(CONTENT_TAGS) is not None:
            continue
        value = clean_text(node.get_text(" ", strip=True))
        if not value:
            continue
        if node.name in {"h1", "h2", "h3", "h4"}:
            heading = value
            continue
        if node.name == "pre" and len(value) > 2400:
            value = value[:2400] + "…"
        blocks.append({"heading": heading, "text": value})
    if not blocks:
        return None
    return {"title": title, "url": url, "blocks": blocks}


def fetch_page(client: httpx.Client, url: str) -> str:
    for attempt in range(3):
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("Falha inesperada na coleta.")


def split_long(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def chunk_page(page: dict) -> list[dict]:
    chunks: list[dict] = []
    current: list[str] = []
    current_heading = ""

    def flush() -> None:
        if not current:
            return
        content = "\n".join(current).strip()
        identifier = hashlib.sha256(
            f"{page['url']}\n{current_heading}\n{content}".encode("utf-8")
        ).hexdigest()[:16]
        chunks.append(
            {
                "id": identifier,
                "title": page["title"],
                "heading": current_heading,
                "url": page["url"],
                "text": content,
            }
        )

    for block in page["blocks"]:
        heading = block["heading"]
        for part in split_long(block["text"], MAX_CHARS - 200):
            if current and (
                heading != current_heading
                or len("\n".join(current)) + len(part) + 1 > MAX_CHARS
            ):
                previous = "\n".join(current)[-OVERLAP_CHARS:].strip()
                flush()
                current = [previous] if heading == current_heading and previous else []
            current_heading = heading
            current.append(part)
    flush()
    return chunks


def retry_delay_seconds(error: Exception, attempt: int) -> float:
    """Honor RetryInfo from Gemini and fall back to bounded exponential backoff."""
    details = getattr(error, "details", {})
    error_body = details.get("error", details) if isinstance(details, dict) else {}
    retry_delay = None
    if isinstance(error_body, dict):
        for detail in error_body.get("details", []):
            if not isinstance(detail, dict):
                continue
            if str(detail.get("@type", "")).endswith("RetryInfo"):
                value = str(detail.get("retryDelay", ""))
                match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", value)
                if match:
                    retry_delay = float(match.group(1))
                    break
    if retry_delay is None:
        message = getattr(error, "message", "") or str(error)
        match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)\s*s", message, re.I)
        retry_delay = float(match.group(1)) if match else min(2**attempt, 60)
    return min(max(retry_delay, 1.0) + random.uniform(0.2, 0.8), 90.0)


def collect() -> dict:
    with httpx.Client(
        timeout=25,
        follow_redirects=True,
        headers={"User-Agent": "DisruptiveArchitectures-RAG/1.0 (academic project)"},
    ) as client:
        urls = fetch_sitemap(client)
        if not urls:
            raise RuntimeError("O sitemap não retornou páginas da disciplina.")
        chunks: list[dict] = []
        seen_ids: set[str] = set()
        skipped: list[str] = []
        pages = 0
        for url in urls:
            try:
                page = extract_page(fetch_page(client, url), url)
                if page is None:
                    skipped.append(url)
                    continue
                page_chunks = chunk_page(page)
                if not page_chunks:
                    skipped.append(url)
                    continue
                pages += 1
                for chunk in page_chunks:
                    if chunk["id"] not in seen_ids:
                        chunks.append(chunk)
                        seen_ids.add(chunk["id"])
                print(f"{pages:02d} {len(page_chunks):02d} {url}", flush=True)
            except (httpx.HTTPError, ValueError) as exc:
                skipped.append(f"{url}: {exc}")
        if pages == 0 or not chunks:
            raise RuntimeError("Nenhuma página com conteúdo foi coletada.")
        if skipped:
            raise RuntimeError(
                f"Coleta incompleta: {len(skipped)} páginas falharam. "
                + "; ".join(skipped[:3])
            )
    corpus = {
        "site": SITE_ROOT,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "chunks": chunks,
        "skipped": skipped,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n")
    print(f"Corpus: {pages} páginas, {len(chunks)} trechos, {len(skipped)} ignoradas.")
    return corpus


def embed(corpus: dict) -> dict:
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY é necessária para gerar o índice.")
    model = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-2")
    client = genai.Client(api_key=key)
    indexed: list[dict] = []
    chunks = corpus["chunks"]
    last_request_at: float | None = None
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        contents = [
            types.Content(
                parts=[
                    types.Part.from_text(
                        text=(
                            f"title: {item['title']} | text: "
                            f"{item['heading']}\n{item['text']}"
                        )
                    )
                ]
            )
            for item in batch
        ]
        for attempt in range(EMBED_MAX_RETRIES):
            if last_request_at is not None:
                wait = EMBED_MIN_INTERVAL_SECONDS - (time.monotonic() - last_request_at)
                if wait > 0:
                    time.sleep(wait)
            last_request_at = time.monotonic()
            try:
                result = client.models.embed_content(
                    model=model,
                    contents=contents,
                    config=types.EmbedContentConfig(output_dimensionality=768),
                )
                break
            except Exception as exc:
                status_code = getattr(exc, "code", None)
                retryable = status_code in {408, 429} or (
                    isinstance(status_code, int) and 500 <= status_code < 600
                )
                if not retryable or attempt == EMBED_MAX_RETRIES - 1:
                    raise
                delay = retry_delay_seconds(exc, attempt)
                print(
                    f"Gemini limitou embeddings; nova tentativa em {delay:.1f}s "
                    f"(tentativa {attempt + 2}/{EMBED_MAX_RETRIES}).",
                    flush=True,
                )
                time.sleep(delay)
        if len(result.embeddings) != len(batch):
            raise RuntimeError("A API retornou quantidade inesperada de embeddings.")
        for item, embedding in zip(batch, result.embeddings, strict=True):
            if not embedding.values:
                raise RuntimeError(f"Embedding vazio no trecho {item['id']}.")
            indexed.append({**item, "vector": embedding.values})
        print(f"Embeddings: {len(indexed)}/{len(chunks)}", flush=True)
    index = {
        "site": corpus["site"],
        "collected_at": corpus["collected_at"],
        "pages": corpus["pages"],
        "embedding_model": model,
        "dimensions": 768,
        "chunks": indexed,
    }
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    print(f"Índice pronto: {INDEX_PATH} ({len(indexed)} trechos).")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--embed-only", action="store_true")
    args = parser.parse_args()
    if args.collect_only and args.embed_only:
        parser.error("Escolha apenas um modo.")
    corpus = (
        json.loads(CORPUS_PATH.read_text()) if args.embed_only else collect()
    )
    if not args.collect_only:
        embed(corpus)


if __name__ == "__main__":
    main()
