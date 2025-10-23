import requests
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE = os.getenv("BASE")


def cl_get(url,headers={},params=None):
    """
    Returns json response from get request. Includes API_KEY in header if available.

    Args:
        url (string): URL for get request.
        headers (dict): Headers to be included in the get request.
        params (dict): Parameters to be included in the get request.
    
    Returns:
        The json response from courtlistener.
    """
    
    if API_KEY:
        headers["Authorization"] = f"Token {API_KEY}"

    r = requests.get(url,headers=headers,params=params)
    r.raise_for_status()
    return r.json()

