import os
import re
import json
import logging
from pathlib import Path
from html import unescape
from datetime import datetime
from .utilities import *

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------

logger = logging.getLogger(__name__)

def configure_logging(log_path="opinion_pipeline.log", level=logging.INFO):
    logging.basicConfig(
        filename=log_path,
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

# -------------------------------------------------------------------
# Field preference
# -------------------------------------------------------------------

TEXT_FIELD_PREFERENCE = [
    "plain_text",
    "html_with_citations",
    "html_columbia",
    "html_lawbox",
    "html_anon_2020",
    "xml_harvard",
    "xml_scan",
    "html",
]

DATE_STRICT_FIELD_PREFERENCE = [
    "html_with_citations",
    "html_columbia",
    "html_lawbox",
    "html_anon_2020",
    "html",
    "xml_harvard",
    "xml_scan",
]

DATE_RELAXED_FIELD_PREFERENCE = [
    *DATE_STRICT_FIELD_PREFERENCE,
    "plain_text",
]

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def resolve_person_id(subdir_name, opinion):
    """
    Rule:
    - use opinion['person_id'] if present
    - otherwise use opinion['author_id'] if present
    - otherwise fall back to subdir_name
    """
    if opinion.get("person_id") is not None:
        return str(opinion["person_id"])

    if opinion.get("author_id") is not None:
        return str(opinion["author_id"])

    return str(subdir_name)


def get_preferred_text_field(opinion):
    """
    Return (field_name, value) for the first non-empty preferred text field.
    """
    for field in TEXT_FIELD_PREFERENCE:
        value = opinion.get(field)
        if isinstance(value, str) and value.strip():
            return field, value
    return None, None


def get_text_by_field_priority(opinion, priority_list):
    """
    Return (field_name, value) for the first non-empty field in priority_list.
    """
    for field in priority_list:
        value = opinion.get(field)
        if isinstance(value, str) and value.strip():
            return field, value
    return None, None


def normalize_plain_text(text):
    if not isinstance(text, str):
        return ""
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_markup(text):
    """
    Remove HTML/XML markup and return visible text only.
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "lxml")

        for tag in soup(["script", "style"]):
            tag.decompose()

        cleaned = soup.get_text(separator=" ", strip=True)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    except Exception:
        cleaned = text

        cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<script.*?>.*?</script>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<style.*?>.*?</style>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<!\[CDATA\[.*?\]\]>", " ", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned


def extract_visible_text(field_name, raw_value):
    if field_name is None or raw_value is None:
        return ""

    if field_name == "plain_text":
        return normalize_plain_text(raw_value)

    return strip_markup(raw_value)


def count_words(text):
    if not text:
        return 0

    words = re.findall(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b", text)
    return len(words)


def count_citations(opinion):
    citations = opinion.get("opinions_cited")

    if isinstance(citations, list):
        return len(citations)

    return 0

# -------------------------------------------------------------------
# Date extraction
# -------------------------------------------------------------------

MONTH_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)"
)

FULL_DATE_PATTERNS = [
    re.compile(rf"\b{MONTH_PATTERN}\s+\d{{1,2}},\s+\d{{4}}\b", re.IGNORECASE),
    re.compile(rf"\b\d{{1,2}}\s+{MONTH_PATTERN}\s+\d{{4}}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b"),
]

MONTH_YEAR_PATTERNS = [
    re.compile(rf"\b{MONTH_PATTERN}\s+\d{{4}}\b", re.IGNORECASE),
    re.compile(rf"\b\d{{4}}\s+{MONTH_PATTERN}\b", re.IGNORECASE),
]

YEAR_PATTERN = re.compile(r"\b(16\d{2}|17\d{2}|18\d{2}|19\d{2}|20\d{2}|21\d{2})\b")


def extract_header_candidate(raw_text):
    """
    Optional header-focused extraction similar to your Stata logic.
    This should run on raw text before markup stripping if you want
    to capture dates sitting in header tags.
    """
    if not raw_text:
        return None

    match = re.search(r"</p>\s*(.*?)\s*</center>", raw_text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        candidate = match.group(1)
        candidate = re.sub(r"<[^>]+>", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        return candidate

    return None


def normalize_date_string(date_str, precision):
    """
    Return standardized YYYY-MM-DD string.
    Missing components default to 01.
    """
    if precision == "day":
        formats = [
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m-%d-%Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date().isoformat()
            except ValueError:
                continue

    elif precision == "month":
        formats = [
            "%B %Y",
            "%b %Y",
            "%Y %B",
            "%Y %b",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return f"{dt.year:04d}-{dt.month:02d}-01"
            except ValueError:
                continue

    elif precision == "year":
        year_match = re.search(r"\b(\d{4})\b", date_str)
        if year_match:
            year = int(year_match.group(1))
            return f"{year:04d}-01-01"

    return None


def extract_standardized_date(text, raw_text=None):
    """
    Returns:
        (standardized_date, date_precision, matched_string, extraction_region)

    standardized_date: YYYY-MM-DD or None
    date_precision: 'day', 'month', 'year', or None
    matched_string: original matched text fragment or None
    extraction_region: 'header_candidate', 'visible_text', 'plain_text', or None
    """
    if not text and not raw_text:
        return None, None, None, None

    search_regions = []

    if raw_text:
        header_candidate = extract_header_candidate(raw_text)
        if header_candidate:
            search_regions.append(("header_candidate", header_candidate))

    if text:
        search_regions.append(("visible_text", text))

    for region_type, region in search_regions:
        for pattern in FULL_DATE_PATTERNS:
            match = pattern.search(region)
            if match:
                matched = match.group(0)
                standardized = normalize_date_string(matched, "day")
                if standardized:
                    return standardized, "day", matched, region_type

        for pattern in MONTH_YEAR_PATTERNS:
            match = pattern.search(region)
            if match:
                matched = match.group(0)
                standardized = normalize_date_string(matched, "month")
                if standardized:
                    return standardized, "month", matched, region_type

        match = YEAR_PATTERN.search(region)
        if match:
            matched = match.group(0)
            standardized = normalize_date_string(matched, "year")
            if standardized:
                return standardized, "year", matched, region_type

    return None, None, None, None


def extract_strict_date(opinion):
    """
    Strict date extraction:
    - searches preferred HTML/XML regions only
    - allows only full day-level date patterns
    - supports optional header-candidate scan from raw markup
    """
    strict_date_field, strict_date_raw = get_text_by_field_priority(
        opinion,
        DATE_STRICT_FIELD_PREFERENCE,
    )
    strict_date_text = extract_visible_text(strict_date_field, strict_date_raw)

    if not strict_date_text and not strict_date_raw:
        return None, None, None, strict_date_field, None

    search_regions = []
    if strict_date_raw:
        header_candidate = extract_header_candidate(strict_date_raw)
        if header_candidate:
            search_regions.append(("header_candidate", header_candidate))
    if strict_date_text:
        visible_region = "plain_text" if strict_date_field == "plain_text" else "visible_text"
        search_regions.append((visible_region, strict_date_text))

    for region_type, region in search_regions:
        for pattern in FULL_DATE_PATTERNS:
            match = pattern.search(region)
            if not match:
                continue
            matched = match.group(0)
            standardized = normalize_date_string(matched, "day")
            if standardized:
                return standardized, "day", matched, strict_date_field, region_type

    return None, None, None, strict_date_field, None


def extract_relaxed_date(opinion):
    """
    Relaxed date extraction:
    - searches broader preferred fields (includes plain_text)
    - allows day/month/year precision patterns
    """
    relaxed_date_field, relaxed_date_raw = get_text_by_field_priority(
        opinion,
        DATE_RELAXED_FIELD_PREFERENCE,
    )
    relaxed_date_text = extract_visible_text(relaxed_date_field, relaxed_date_raw)

    standardized, precision, matched, extraction_region = extract_standardized_date(
        text=relaxed_date_text,
        raw_text=relaxed_date_raw,
    )
    if extraction_region == "visible_text" and relaxed_date_field == "plain_text":
        extraction_region = "plain_text"
    return standardized, precision, matched, relaxed_date_field, extraction_region


def extract_dual_dates(opinion):
    """
    Returns:
      - opinion_date_confident (+ metadata)
      - opinion_date_relaxed (+ metadata)
    """
    confident_date, confident_precision, confident_match, confident_source, confident_region = extract_strict_date(opinion)
    relaxed_date, relaxed_precision, relaxed_match, relaxed_source, relaxed_region = extract_relaxed_date(opinion)

    return {
        "opinion_date_confident": confident_date,
        "opinion_date_confident_precision": confident_precision,
        "opinion_date_confident_matched_text": confident_match,
        "opinion_date_confident_source_field": confident_source,
        "opinion_date_confident_extraction_region": confident_region,
        "opinion_date_confident_confidence_label": "confident",
        "opinion_date_relaxed": relaxed_date,
        "opinion_date_relaxed_precision": relaxed_precision,
        "opinion_date_relaxed_matched_text": relaxed_match,
        "opinion_date_relaxed_source_field": relaxed_source,
        "opinion_date_relaxed_extraction_region": relaxed_region,
        "opinion_date_relaxed_confidence_label": "relaxed",
    }

# -------------------------------------------------------------------
# Record processing
# -------------------------------------------------------------------

def process_opinion_record(subdir_name, file_path, opinion):
    person_id = resolve_person_id(subdir_name, opinion)

    selected_field, raw_text = get_preferred_text_field(opinion)
    cleaned_text = extract_visible_text(selected_field, raw_text)

    word_count = count_words(cleaned_text)
    citation_count = count_citations(opinion)

    dual_dates = extract_dual_dates(opinion)

    # Backward compatibility for downstream consumers still expecting legacy fields.
    opinion_date = dual_dates["opinion_date_confident"] or dual_dates["opinion_date_relaxed"]
    date_precision = (
        dual_dates["opinion_date_confident_precision"]
        or dual_dates["opinion_date_relaxed_precision"]
    )
    matched_date_text = (
        dual_dates["opinion_date_confident_matched_text"]
        or dual_dates["opinion_date_relaxed_matched_text"]
    )
    date_source_field = (
        dual_dates["opinion_date_confident_source_field"]
        if dual_dates["opinion_date_confident"]
        else dual_dates["opinion_date_relaxed_source_field"]
    )
    date_extraction_region = (
        dual_dates["opinion_date_confident_extraction_region"]
        if dual_dates["opinion_date_confident"]
        else dual_dates["opinion_date_relaxed_extraction_region"]
    )
    date_confidence_label = (
        dual_dates["opinion_date_confident_confidence_label"]
        if dual_dates["opinion_date_confident"]
        else dual_dates["opinion_date_relaxed_confidence_label"]
    )

    return {
        "person_id": person_id,
        "file_path": str(file_path),
        "opinion_id": opinion.get("id"),
        "cluster_id": opinion.get("cluster_id"),
        "selected_field": selected_field,
        "word_count": word_count,
        "citation_count": citation_count,
        **dual_dates,
        "opinion_date": opinion_date,
        "date_precision": date_precision,
        "matched_date_text": matched_date_text,
        "date_source_field": date_source_field,
        "date_extraction_region": date_extraction_region,
        "date_confidence_label": date_confidence_label,
        "has_text": bool(cleaned_text),
    }

# -------------------------------------------------------------------
# Full pipeline
# -------------------------------------------------------------------

def build_opinion_records(data_subdir, base_env_var="DATA"):
    """
    Iterate through opinion JSON files and return a list of records with:
    - word count
    - citation count
    - inferred opinion dates from two paths:
      * opinion_date_confident: strict HTML/XML day-level extraction only.
      * opinion_date_relaxed: broader fallback extraction supporting day/month/year.
    - provenance metadata for each extracted date:
      * *_source_field: originating input field (e.g., html_with_citations, plain_text)
      * *_extraction_region: header_candidate, visible_text, or plain_text
      * *_confidence_label: confident (strict path) or relaxed (fallback path)
    - legacy rolled-up date fields (opinion_date/date_precision/matched_date_text)
      with corresponding provenance (date_source_field/date_extraction_region/date_confidence_label)
    """
    records = []

    for subdir_name, file_path, opinion in iter_json_data(data_subdir, base_env_var):
        person_id = None

        try:
            person_id = resolve_person_id(subdir_name, opinion)
            record = process_opinion_record(subdir_name, file_path, opinion)
            records.append(record)

        except Exception as e:
            fallback_person_id = person_id if person_id is not None else str(subdir_name)

            logger.exception(
                "Error processing opinion | person_id=%s | file=%s",
                fallback_person_id,
                file_path,
            )

            log_error(fallback_person_id, e)
            continue

    return records
