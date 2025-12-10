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