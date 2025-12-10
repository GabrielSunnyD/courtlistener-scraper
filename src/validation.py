import pandas as pd
from datetime import datetime as dt


def earliest_start_date(date_ranges: list) -> str | None:
    earliest_date_dt = None
    for start_date, end_date in date_ranges:
        if start_date:
            start_date_dt = dt.strptime(start_date, "%Y-%m-%d")
            if earliest_date_dt is None or start_date_dt < earliest_date_dt:
                earliest_date_dt = start_date_dt
    return earliest_date_dt.strftime("%Y-%m-%d") if earliest_date_dt else None


def latest_end_date(date_ranges: list) -> str | None:

    latest_date_dt = None

    for start_date, end_date in date_ranges:
        if end_date:

            end_date_dt = dt.strptime(end_date, "%Y-%m-%d")

            if latest_date_dt is None or end_date_dt > latest_date_dt:
                latest_date_dt = end_date_dt

    return latest_date_dt.strftime("%Y-%m-%d") if latest_date_dt else None


def time_in_office(date_ranges: list) -> int | None:
    start_date_str = earliest_start_date(date_ranges)
    end_date_str = latest_end_date(date_ranges)

    if not start_date_str:
        return None

    start_date_dt = dt.strptime(start_date_str, "%Y-%m-%d")

    if end_date_str:
        end_date_dt = dt.strptime(end_date_str, "%Y-%m-%d")
    else:
        end_date_dt = dt.now()

    delta = end_date_dt - start_date_dt

    return delta.days


def docket_count(dockets_list: list) -> int:
    if not isinstance(dockets_list, list):
        return 0
    return len(dockets_list)


def 