# Based on
# https://github.com/jonatasgrosman/findpapers/blob/master/findpapers/searchers/arxiv_searcher.py
# https://info.arxiv.org/help/api/user-manual.html

from typing import Optional, Literal, List, Dict, Any, Union
from datetime import datetime, date
from urllib3.util.retry import Retry

import requests
from requests.adapters import HTTPAdapter
import xmltodict
from jinja2 import Template

BASE_URL = "http://export.arxiv.org"
URL_TEMPLATE = "{base_url}/api/query?search_query={query}&start={start}&sortBy={sort_by}&sortOrder={sort_order}&max_results={limit}"
SORT_BY_OPTIONS = ("relevance", "lastUpdatedDate", "submittedDate")
SORT_ORDER_OPTIONS = ("ascending", "descending")
ENTRY_TEMPLATE = """==== Entry {{index}} ====
Paper ID: {{entry["id"]}}
Title: {{entry["title"]}}
Authors: {{entry["authors"]}}
Summary: {{entry["summary"]}}{% if entry["comment"] %}
Comment: {{entry["comment"]}}{% endif %}
Publication date: {{entry["published"]}}{% if entry["published"] != entry["updated"] %}
Date of last update: {{entry["updated"]}}{% endif %}
Categories: {{entry["categories"]}}"""


def _format_id(url: str) -> str:
    return url.split("/")[-1]


def _format_text_field(text: str) -> str:
    text = " ".join([line.strip() for line in text.split() if line.strip()])
    return text


def _format_authors(authors: Union[List[Dict[str, str]], Dict[str, str]]) -> str:
    if not authors:
        return ""
    if isinstance(authors, dict):
        authors = [authors]
    names = [author["name"] for author in authors]
    result = ", ".join(names[:3])
    if len(names) > 3:
        result += " et al."
    return result


def _format_categories(categories: Union[List[Dict[str, Any]], Dict[str, Any]]) -> str:
    if not categories:
        return ""
    if isinstance(categories, dict):
        categories = [categories]
    clean_categories = [c.get("@term", "") for c in categories]
    clean_categories = [c.strip() for c in clean_categories if c.strip()]
    return ", ".join(clean_categories)


def _format_date(date: str) -> str:
    dt = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    return dt.strftime("%B %d, %Y")


def _clean_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _format_id(entry["id"]),
        "title": _format_text_field(entry["title"]),
        "authors": _format_authors(entry["author"]),
        "summary": _format_text_field(entry["summary"]),
        "published": _format_date(entry["published"]),
        "updated": _format_date(entry["updated"]),
        "categories": _format_categories(entry.get("category", {})),
        "comment": _format_text_field(entry.get("arxiv:comment", {}).get("#text", "")),
    }


def _convert_to_yyyymmddtttt(date_str: str) -> str:
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%Y%m%d") + "0000"
    except ValueError as e:
        raise ValueError("Invalid date format. Please use YYYY-MM-DD format.") from e


def _compose_query(
    orig_query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    query: str = orig_query.replace(" AND NOT ", " ANDNOT ")
    if start_date or end_date:
        if not start_date:
            start_date = "1900-01-01"
        if not end_date:
            today = date.today()
            end_date = today.strftime("%Y-%m-%d")
        date_filter = f"[{_convert_to_yyyymmddtttt(start_date)} TO {_convert_to_yyyymmddtttt(end_date)}]"
        query = f"({query}) AND submittedDate:{date_filter}"

    query = query.replace("-", " ")
    query = query.replace(" ", "+")
    query = query.replace('"', "%22")
    query = query.replace("(", "%28")
    query = query.replace(")", "%29")
    return query


def _format_entries(entries: List[Dict[str, Any]], start_index: int) -> str:
    final_entries = []
    for entry_num, entry in enumerate(entries):
        index = start_index + entry_num
        template = Template(ENTRY_TEMPLATE)
        fixed_entry = _clean_entry(entry)
        final_entries.append(
            template.render(
                index=index,
                entry=fixed_entry,
            )
        )
    return "\n".join(final_entries)


def _get_results(url: str) -> requests.Response:
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)

    try:
        response = session.get(url, timeout=30)
        return response
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.RequestException,
    ) as e:
        print(f"Failed after {retry_strategy.total} retries: {str(e)}")
        raise

    return response


def arxiv_search(
    query: str,
    offset: Optional[int] = 0,
    limit: Optional[int] = 3,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sort_by: Optional[str] = "relevance",
    sort_order: Optional[str] = "descending",
) -> str:
    """
    Search arXiv papers with field-specific queries.

    Fields that can be searched:
        ti: (title), au: (author), abs: (abstract),
        cat: (category), id: (ID)

    Operatore that can be used:
        AND, OR, ANDNOT

    Please always specify the fields. Search should be always field-specific.
    You can include entire phrases by enclosing the phrase in double quotes.
    Note, that boolean operators are strict. Do not overuse AND.
    Names of authors should be in Latin script.
    For example, search "Ilya Gusev" instead of "Илья Гусев".

    Example queries:
        abs:"machine learning"
        au:"del maestro"
        au:vaswani AND ti:"attention is all"
        (au:vaswani OR au:"del maestro") ANDNOT ti:attention

    Returns a text containing papers' metadata including "Paper ID", "Title", "Authors",
    "Summary", "Comment", "Publication date", "Date of last update", "Categories"

    Args:
        query: The search query, required.
        offset: The offset in search results. If it is 10, first 10 items will be skipped. 0 by default.
        limit: The maximum number of items that will be returned. 3 by default.
        start_date: Start date in %Y-%m-%d format. None by default.
        end_date: End date in %Y-%m-%d format. None by default.
        sort_by: 3 options to sort by: relevance, lastUpdatedDate, submittedDate. relevance by default.
        sort_order: 2 sort orders: ascending, descending. descending by default.
    """

    assert isinstance(query, str), "Error: Your search query must be a string"
    assert isinstance(offset, int), "Error: offset should be an integer"
    assert isinstance(limit, int), "Error: limit should be an integer"
    assert isinstance(sort_by, str), "Error: sort_by should be a string"
    assert isinstance(sort_order, str), "Error: sort_order should be a string"
    assert query.strip(), "Error: Your query should not be empty"
    assert (
        sort_by in SORT_BY_OPTIONS
    ), f"Error: sort_by should be one of {SORT_BY_OPTIONS}"
    assert (
        sort_order in SORT_ORDER_OPTIONS
    ), f"Error: sort_order should be one of {SORT_ORDER_OPTIONS}"
    assert offset >= 0, "Error: offset must be 0 or positive number"
    assert limit < 100, "Error: limit is too large, it should be less than 100"
    assert limit > 0, "Error: limit should be greater than 0"

    fixed_query: str = _compose_query(query, start_date, end_date)
    url = URL_TEMPLATE.format(
        base_url=BASE_URL,
        query=fixed_query,
        start=offset,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    response = _get_results(url)
    content = response.content
    parsed_content = xmltodict.parse(content)

    feed = parsed_content.get("feed", {})
    total_results = int(feed.get("opensearch:totalResults", {}).get("#text", 0))
    start_index = int(feed.get("opensearch:startIndex", {}).get("#text", 0))
    entries = feed.get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    formatted_entries = _format_entries(entries, start_index=start_index)
    return f"Found {total_results} papers\nOffset: {offset}\n{formatted_entries}"
