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
