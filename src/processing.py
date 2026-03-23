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

DATE_PATTERNS = [
    # January 5, 2020 / Jan 5, 2020
    re.compile(rf"\b{MONTH_PATTERN}\s+\d{{1,2}},\s+\d{{4}}\b", re.IGNORECASE),

    # 5 January 2020 / 5 Jan 2020
    re.compile(rf"\b\d{{1,2}}\s+{MONTH_PATTERN}\s+\d{{4}}\b", re.IGNORECASE),

    # 2020-01-05
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),

    # 01/05/2020 or 1/5/2020
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),

    # 01-05-2020 or 1-5-2020
    re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b"),
]


def parse_date_string(date_str):
    """
    Try to normalize a matched date string into YYYY-MM-DD.
    If parsing fails, return the original match.
    """
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

    return date_str


def extract_first_date(text):
    """
    Search the cleaned text for the first date-like string and return it.
    Assumes the first date found is the opinion date.
    """
    if not text:
        return None

    earliest_match = None
    earliest_start = None

    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            if earliest_start is None or match.start() < earliest_start:
                earliest_match = match.group(0)
                earliest_start = match.start()

    if earliest_match is None:
        return None

    return parse_date_string(earliest_match)

# -------------------------------------------------------------------
# Record processing
# -------------------------------------------------------------------

def process_opinion_record(subdir_name, file_path, opinion):
    person_id = resolve_person_id(subdir_name, opinion)

    opinion_person_id = opinion.get("person_id")
    opinion_author_id = opinion.get("author_id")

    if opinion_person_id is not None and str(opinion_person_id) != str(subdir_name):
        logger.warning(
            "Directory/person_id mismatch | dir=%s | opinion.person_id=%s | file=%s",
            subdir_name,
            opinion_person_id,
            file_path,
        )

    if opinion_person_id is None and opinion_author_id is not None and str(opinion_author_id) != str(subdir_name):
        logger.warning(
            "Directory/author_id mismatch | dir=%s | opinion.author_id=%s | file=%s",
            subdir_name,
            opinion_author_id,
            file_path,
        )

    selected_field, raw_text = get_preferred_text_field(opinion)
    cleaned_text = extract_visible_text(selected_field, raw_text)

    word_count = count_words(cleaned_text)
    citation_count = count_citations(opinion)
    opinion_date = extract_first_date(cleaned_text)

    if selected_field is None:
        logger.info("No opinion text found | person_id=%s | file=%s", person_id, file_path)

    return {
        "person_id": person_id,
        "file_path": str(file_path),
        "opinion_id": opinion.get("id"),
        "cluster_id": opinion.get("cluster_id"),
        "selected_field": selected_field,
        "word_count": word_count,
        "citation_count": citation_count,
        "opinion_date": opinion_date,
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
    - inferred opinion date
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