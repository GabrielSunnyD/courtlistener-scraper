import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
DATA = os.getenv("DATA")

def save_df_to_csv(df, file_name, index = False, **kwargs):
    df.to_csv(f"{DATA}/{file_name}", index=index, **kwargs)
