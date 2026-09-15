from __future__ import annotations

import bz2
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from ingest.wikidata.config import WDQS_REQUEST_TIMEOUT, wdqs_user_agent
from ingest.wikidata.storage import PostgresWikidataStore


logger = logging.getLogger(__name__)
_DUMP_BASE_URL = "https://dumps.wikimedia.org/other/pageview_complete/monthly"
_DATA_DIRECTORY = Path(__file__).resolve().parents[4] / "data" / "wikimedia_pageviews"


@dataclass(frozen=True)
class MonthlyPageviewDump:
    month: date
    compressed_path: Path
    extracted_path: Path
    aggregate_path: Path


def previous_month(today: date) -> date:
    return date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)


def monthly_dump(month: date, data_directory: Path = _DATA_DIRECTORY) -> MonthlyPageviewDump:
    filename = f"pageviews-{month:%Y%m}-user.bz2"
    return MonthlyPageviewDump(
        month=month,
        compressed_path=data_directory / filename,
        extracted_path=data_directory / filename.removesuffix(".bz2"),
        aggregate_path=data_directory / f"pageviews-{month:%Y%m}-en.wikipedia.tsv",
    )


async def download_and_extract_monthly_pageviews(month: date | None = None) -> MonthlyPageviewDump:
    dump = monthly_dump(month or previous_month(date.today()))
    dump.compressed_path.parent.mkdir(parents=True, exist_ok=True)

    if dump.compressed_path.exists():
        logger.info("Using existing monthly pageview dump: %s", dump.compressed_path)
    else:
        await _download_dump(dump)

    if dump.extracted_path.exists():
        logger.info("Using existing extracted monthly pageviews: %s", dump.extracted_path)
    else:
        _extract_dump(dump)

    return dump


def aggregate_enwiki_monthly_pageviews(dump: MonthlyPageviewDump) -> Path:
    if dump.aggregate_path.exists():
        logger.info("Using existing aggregated English Wikipedia pageviews: %s", dump.aggregate_path)
        return dump.aggregate_path

    partial_path = dump.aggregate_path.with_suffix(".part")
    partial_path.unlink(missing_ok=True)
    total_bytes = dump.extracted_path.stat().st_size
    processed_bytes = next_log_at = 0
    rows = articles = 0
    current_title: str | None = None
    current_total = 0

    logger.info("Aggregating English Wikipedia pageviews from: %s", dump.extracted_path)
    with dump.extracted_path.open("rb") as source, partial_path.open("w", encoding="utf-8") as output:
        for raw_line in source:
            processed_bytes += len(raw_line)
            rows += 1
            parsed = parse_monthly_pageview_line(raw_line)
            if parsed is not None:
                project, title, _, _, daily_total = parsed
                if project == "en.wikipedia":
                    if current_title is not None and title != current_title:
                        output.write(f"{current_title}\t{current_total}\n")
                        articles += 1
                        current_total = 0
                    current_title = title
                    current_total += daily_total

            if processed_bytes >= next_log_at:
                logger.info(
                    "Monthly pageview aggregation: %.1f%% scanned, %d English Wikipedia articles aggregated",
                    processed_bytes / total_bytes * 100,
                    articles,
                )
                next_log_at += 1024 * 1024 * 1024

        if current_title is not None:
            output.write(f"{current_title}\t{current_total}\n")
            articles += 1

    partial_path.replace(dump.aggregate_path)
    logger.info(
        "Aggregated %d English Wikipedia articles from %d rows into %s",
        articles,
        rows,
        dump.aggregate_path,
    )
    return dump.aggregate_path


def parse_monthly_pageview_line(line: bytes) -> tuple[str, str, str, str, int] | None:
    try:
        project_and_title_and_page_id, access, daily_total, _ = line.decode("utf-8").rstrip("\n").rsplit(" ", 3)
        project_and_title, page_id = project_and_title_and_page_id.rsplit(" ", 1)
        project, title = project_and_title.split(" ", 1)
        return project, title, page_id, access, int(daily_total)
    except (UnicodeDecodeError, ValueError):
        return None


async def ingest_monthly_pageviews(store: PostgresWikidataStore, dump: MonthlyPageviewDump) -> None:
    entity_ids_by_title = await store.enwiki_sitelink_entity_ids()
    if not entity_ids_by_title:
        logger.warning("No English Wikipedia sitelinks are available to match against the monthly pageview dump")
        return

    logger.info(
        "Matching %d English Wikipedia sitelinks against %s",
        len(entity_ids_by_title),
        dump.aggregate_path,
    )
    matched = scanned = 0
    batch: list[tuple[str, int]] = []
    with dump.aggregate_path.open(encoding="utf-8") as source:
        for line in source:
            scanned += 1
            try:
                title, views = line.rstrip("\n").rsplit("\t", 1)
                entity_id = entity_ids_by_title.get(title)
                if entity_id is not None:
                    batch.append((entity_id, int(views)))
                    matched += 1
            except ValueError:
                logger.warning("Skipping invalid aggregated pageview row: %r", line[:200])

            if len(batch) == 1_000:
                await store.upsert_monthly_wikipedia_pageviews(dump.month, batch)
                batch.clear()
            if scanned % 1_000_000 == 0:
                logger.info("Monthly pageview DB ingest: %d rows scanned, %d entities matched", scanned, matched)

    await store.upsert_monthly_wikipedia_pageviews(dump.month, batch)
    logger.info("Monthly pageview DB ingest complete: %d rows scanned, %d entities matched", scanned, matched)


async def _download_dump(dump: MonthlyPageviewDump) -> None:
    url = f"{_DUMP_BASE_URL}/{dump.month:%Y}/{dump.month:%Y-%m}/{dump.compressed_path.name}"
    partial_path = dump.compressed_path.with_suffix(dump.compressed_path.suffix + ".part")
    partial_path.unlink(missing_ok=True)
    logger.info("Downloading monthly pageview dump: %s", url)

    async with httpx.AsyncClient(
        headers={"User-Agent": wdqs_user_agent()}, timeout=WDQS_REQUEST_TIMEOUT
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_length = int(response.headers.get("content-length", 0))
            downloaded = 0
            next_log_at = 100 * 1024 * 1024
            with partial_path.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_log_at:
                        if content_length:
                            logger.info("Downloaded %.1f%% of monthly pageview dump", downloaded / content_length * 100)
                        else:
                            logger.info("Downloaded %.1f MiB of monthly pageview dump", downloaded / 1024 / 1024)
                        next_log_at += 100 * 1024 * 1024

    partial_path.replace(dump.compressed_path)
    logger.info("Downloaded monthly pageview dump: %.1f MiB", dump.compressed_path.stat().st_size / 1024 / 1024)


def _extract_dump(dump: MonthlyPageviewDump) -> None:
    partial_path = dump.extracted_path.with_suffix(".part")
    partial_path.unlink(missing_ok=True)
    logger.info("Extracting monthly pageview dump: %s", dump.compressed_path)
    with bz2.open(dump.compressed_path, "rb") as compressed, partial_path.open("wb") as extracted:
        while chunk := compressed.read(1024 * 1024):
            extracted.write(chunk)
    partial_path.replace(dump.extracted_path)
    logger.info("Extracted monthly pageviews: %.1f MiB", dump.extracted_path.stat().st_size / 1024 / 1024)
