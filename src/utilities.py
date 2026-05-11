import pandas as pd
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()
DATA = os.getenv("DATA")

def save_df_to_csv(df, file_name, index = False, **kwargs):
    df.to_csv(f"{DATA}/{file_name}", index=index, **kwargs)

def load_csv_to_df(file_name, **kwargs):
    df = pd.read_csv(f"{DATA}/{file_name}", **kwargs)
    return df

def log_error(person_id, error, logfile="error_log.csv"):
    """Append an error record to a CSV log."""
    timestamp = datetime.now().isoformat()
    record = pd.DataFrame([{
        "timestamp": timestamp,
        "person_id": person_id,
        "error": str(error)
    }])

    # Append mode, no header after first write
    record.to_csv(logfile, mode="a", header=not os.path.exists(logfile), index=False)

def merge_dedup_and_shard(
    csv_with_extra: str,
    csv_without_extra: str,
    out_dir: str,
    base_name: str = "merged",
    id_col: str = "id",
    chunksize: int = 200_000,
    target_rows_per_file: int = 2_000_000,  # tune to hit desired GB/file
    force_id_as_string: bool = True,
):
    """
    Merge two CSVs by unioning rows, deduplicating by `id_col`.
    Preference rule: if an id exists in both files, keep the row from `csv_with_extra`.
    Output is sharded into multiple CSVs with at most `target_rows_per_file` rows each.
    Column order rule: shared cols first, then any plain-only cols, then extra-only cols (extras last).
    """
    os.makedirs(out_dir, exist_ok=True)

    # Read headers only
    cols_extra = pd.read_csv(csv_with_extra, nrows=0).columns.tolist()
    cols_plain = pd.read_csv(csv_without_extra, nrows=0).columns.tolist()

    if id_col not in cols_extra or id_col not in cols_plain:
        raise ValueError(f"Both CSVs must contain '{id_col}' column.")

    # Column ordering: shared → plain_only → extra_only  (extras go last)
    extra_only = [c for c in cols_extra if c not in cols_plain]
    shared = [c for c in cols_extra if c in cols_plain]  # keep preferred file's order
    plain_only = [c for c in cols_plain if c not in cols_extra]
    all_cols = shared + plain_only + extra_only

    # Output shard state
    file_idx = 1
    rows_in_current = 0
    out_path = os.path.join(out_dir, f"{base_name}_{file_idx:03d}.csv")
    first_write_in_shard = True

    def rotate_file():
        nonlocal file_idx, rows_in_current, out_path, first_write_in_shard
        file_idx += 1
        rows_in_current = 0
        out_path = os.path.join(out_dir, f"{base_name}_{file_idx:03d}.csv")
        first_write_in_shard = True

    def ensure_cols_and_order(df: pd.DataFrame) -> pd.DataFrame:
        for c in all_cols:
            if c not in df.columns:
                df[c] = pd.NA
        return df[all_cols]

    def write_df_sharded(df: pd.DataFrame):
        nonlocal rows_in_current, first_write_in_shard
        if df.empty:
            return

        df = ensure_cols_and_order(df)

        start = 0
        n = len(df)
        while start < n:
            space = target_rows_per_file - rows_in_current
            if space <= 0:
                rotate_file()
                space = target_rows_per_file

            end = min(start + space, n)
            part = df.iloc[start:end]

            part.to_csv(
                out_path,
                mode="a",
                index=False,
                header=first_write_in_shard,
            )
            first_write_in_shard = False
            rows_in_current += len(part)
            start = end

    # Seen-id tracker (memory-based)
    seen_ids = set()

    def iter_csv(path: str):
        dtype = {id_col: "string"} if force_id_as_string else None
        return pd.read_csv(path, chunksize=chunksize, dtype=dtype)

    def normalize_id_series(s: pd.Series) -> pd.Series:
        # If dtype is string, still normalize missing values; keep NA as NA.
        # This avoids issues where some ids have leading/trailing whitespace.
        if pd.api.types.is_string_dtype(s.dtype):
            return s.str.strip()
        return s

    def process_file(path: str, prefer: bool):
        """
        prefer=True means we WANT these rows to win ties (so process them first).
        prefer flag isn't used directly because we enforce preference by order:
        - process preferred file first, marking ids as seen
        - then process the other file, skipping seen ids
        """
        for chunk in iter_csv(path):
            # Normalize ids
            chunk[id_col] = normalize_id_series(chunk[id_col])

            # Optionally drop rows missing an id (common sanity step)
            chunk = chunk[chunk[id_col].notna()]

            # Drop duplicates within the chunk
            chunk = chunk.drop_duplicates(subset=[id_col], keep="first")

            # Keep only ids not yet written
            is_new = ~chunk[id_col].isin(seen_ids)
            new_rows = chunk.loc[is_new].copy()

            if not new_rows.empty:
                # Update seen ids and write
                seen_ids.update(new_rows[id_col].tolist())
                write_df_sharded(new_rows)

    # 1) Preferred file first (wins duplicates)
    process_file(csv_with_extra, prefer=True)

    # 2) Non-preferred file second
    process_file(csv_without_extra, prefer=False)

    print(f"Done. Wrote {file_idx} shard file(s) to: {out_dir}")
    if extra_only:
        print(f"Extra-only column(s) placed last: {extra_only}")
    else:
        print("No extra-only columns detected.")

import json
from pathlib import Path


def _to_jsonable(x):
    """Convert common non-JSON types into JSON-serializable Python types."""
    # Missing-ish values
    if x is None:
        return None

    # Numpy scalars (if numpy is present in values)
    try:
        import numpy as np
        if isinstance(x, np.integer):
            return int(x)
        if isinstance(x, np.floating):
            return float(x)
        if isinstance(x, np.bool_):
            return bool(x)
    except Exception:
        pass

    # Pandas Timestamp / NaT (if pandas is present in values)
    try:
        import pandas as pd
        if isinstance(x, pd.Timestamp):
            return x.isoformat()
        # pd.isna covers NaN/NaT, but only call if pandas exists
        try:
            if pd.isna(x):
                return None
        except Exception:
            pass
    except Exception:
        pass

    # Datetime/date -> ISO
    try:
        from datetime import datetime, date
        if isinstance(x, (datetime, date)):
            return x.isoformat()
    except Exception:
        pass

    # Paths -> str
    if isinstance(x, Path):
        return str(x)

    # Recurse containers
    if isinstance(x, (list, tuple)):
        return [_to_jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _to_jsonable(v) for k, v in x.items()}

    return x


def write_opinions_to_json_files(
    opinions,
    base_env_var="DATA",
    subdir="opinions",
    id_key="id",
    person_id_key="person_id",
    overwrite=False,
):
    """
    Takes a list of dictionaries, where each dict is an Opinion object, and writes each to:

        $DATA/<subdir>/<person_id>/<id>.json

    Each file contains a single JSON object (the opinion dict).

    Returns:
        (written_paths, errors)
        - written_paths: list of pathlib.Path written
        - errors: list of (opinion_id_or_None, exception)
    """
    if base_env_var not in os.environ or not os.environ[base_env_var].strip():
        raise EnvironmentError(f"Environment variable '{base_env_var}' is not set or empty.")

    base_dir = Path(os.environ[base_env_var]).expanduser().resolve()
    root = base_dir / subdir
    root.mkdir(parents=True, exist_ok=True)

    written = []
    errors = []

    if opinions is None:
        raise ValueError("opinions is None; expected a list of dicts.")

    for i, opinion in enumerate(opinions):
        op_id = None
        try:
            if not isinstance(opinion, dict):
                raise TypeError(f"Item {i} is not a dict (got {type(opinion)}).")

            if id_key not in opinion:
                raise KeyError(f"Item {i} missing required key '{id_key}'.")
            if person_id_key not in opinion:
                raise KeyError(f"Item {i} missing required key '{person_id_key}'.")

            op_id = opinion.get(id_key)
            person_id = opinion.get(person_id_key)

            if op_id is None or str(op_id).strip() == "":
                raise ValueError(f"Item {i} has empty '{id_key}'.")
            if person_id is None or str(person_id).strip() == "":
                raise ValueError(f"Item {i} (id={op_id}) has empty '{person_id_key}'.")

            person_folder = root / str(person_id)
            person_folder.mkdir(parents=True, exist_ok=True)

            out_path = person_folder / f"{op_id}.json"
            if out_path.exists() and not overwrite:
                continue

            record = _to_jsonable(opinion)

            with out_path.open("w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            written.append(out_path)

        except Exception as e:
            errors.append((op_id, e))

    return written, errors


def stream_and_write_opinions(
    opinions_iterable,
    batch_size=500,
    base_env_var="DATA",
    subdir="opinions",
    id_key="id",
    person_id_key="person_id",
    overwrite=False,
):
    """
    Consume an iterable/generator of opinion dicts and write them in batches.

    This lets callers pair API generators with ``write_opinions_to_json_files``
    so opinions can be streamed to disk with bounded memory use.
    """
    if opinions_iterable is None:
        raise ValueError("opinions_iterable is None; expected an iterable of dicts.")
    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer.")

    total_written = []
    total_errors = []
    batch = []

    for opinion in opinions_iterable:
        batch.append(opinion)
        if len(batch) >= batch_size:
            written, errors = write_opinions_to_json_files(
                batch,
                base_env_var=base_env_var,
                subdir=subdir,
                id_key=id_key,
                person_id_key=person_id_key,
                overwrite=overwrite,
            )
            total_written.extend(written)
            total_errors.extend(errors)
            batch = []

    if batch:
        written, errors = write_opinions_to_json_files(
            batch,
            base_env_var=base_env_var,
            subdir=subdir,
            id_key=id_key,
            person_id_key=person_id_key,
            overwrite=overwrite,
        )
        total_written.extend(written)
        total_errors.extend(errors)

    return total_written, total_errors


def fetch_and_write_opinions(
    page="opinions",
    headers={},
    params=None,
    max_pages=None,
    sleep=0,
    batch_size=500,
    base_env_var="DATA",
    subdir="opinions",
    id_key="id",
    person_id_key="person_id",
    overwrite=False,
):
    """
    Fetch opinions via paginated API generator and stream-write them to JSON.
    """
    from .api import cl_paginate_list_generator

    opinions_gen = cl_paginate_list_generator(
        page=page,
        headers=headers,
        params=params,
        max_pages=max_pages,
        sleep=sleep,
    )

    return stream_and_write_opinions(
        opinions_iterable=opinions_gen,
        batch_size=batch_size,
        base_env_var=base_env_var,
        subdir=subdir,
        id_key=id_key,
        person_id_key=person_id_key,
        overwrite=overwrite,
    )



# Source - https://stackoverflow.com/a/19366686
# Posted by Claudiu, modified by community. See post 'Timeline' for change history
# Retrieved 2026-03-13, License - CC BY-SA 3.0
# Used to create natural sort key for use in iter_subdirs because filenames are strings
import re

_nsre = re.compile('([0-9]+)')
def natural_sort_key_from_posixpath(p):
    s = str(p)
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]   




def iter_subdirs(data_subdir: str, base_env_var="DATA"):
    base = os.environ.get(base_env_var)

    if not base or not base.strip():
        raise EnvironmentError(
            f"Environment variable '{base_env_var}' is not set or empty."
        )

    base_dir = Path(base).expanduser().resolve()
    root = base_dir / data_subdir

    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {root}")

    for item in sorted(root.iterdir(),key=natural_sort_key_from_posixpath,reverse=True):
        if item.is_dir():
            yield item


def iter_json_files(folder):
    for file in folder.glob("*.json"):
        yield file


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
    
def iter_json_data(data_subdir, base_env_var="DATA"):
    for subdir in iter_subdirs(data_subdir, base_env_var):
        for file in iter_json_files(subdir):
            try:
                data = load_json(file)
                yield subdir.name, file, data
            except json.JSONDecodeError as e:
                print(f"Bad JSON in subdir: {subdir.name} file: {file}")
                print(f"Error: {e}")
