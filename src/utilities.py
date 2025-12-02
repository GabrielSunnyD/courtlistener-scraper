import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
DATA = os.getenv("DATA")

def save_df_to_csv(df, file_name, index = False, **kwargs):
    df.to_csv(f"{DATA.strip('/')}/{file_name}", index=index, **kwargs)

def load_csv_to_df(file_name, **kwargs):
    df = pd.read_csv(f"{DATA.strip('/')}/{file_name}", **kwargs)
    return df
