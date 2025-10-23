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


def cl_paginate(page,headers={},params=None,max_pages = None):
    url = f"{BASE.strip("/")}/{page.strip("/")}/"
    rows = []
    pages = 0

    while url:
        r = cl_get(url,headers=headers,params=params)

        data = r.json()

        for obj in data.get("results",[]):
            rows.append(obj)
        
        url = data.get("next")
        params = None

        if max_pages and pages >= max_pages:
            break
    
    return pd.DataFrame(rows)

        