import requests
import pandas as pd
from dotenv import load_dotenv
import os
import time
import random

load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE = os.getenv("BASE")


def cl_get(url, headers=None, params=None, timeout=30, retries=3, backoff=0.5):
    """
    Returns json response from get request. Includes API_KEY in header if available.

    Args:
        url (string): URL for get request.
        headers (dict): Headers to be included in the get request.
        params (dict): Parameters to be included in the get request.
    
    Returns:
        The json response from courtlistener.
    """
    
    if headers is None:
        headers = {}
    if API_KEY:
        headers = {**headers, "Authorization":f"Token {API_KEY}"}

    attempt = 0
    while True:
        try:
            r = requests.get(url,headers=headers,params=params,timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            attempt += 1
            if attempt > retries:
                raise
            sleep_s = backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
            time.sleep(sleep_s)
            continue


def cl_paginate(page,headers={},params=None,max_pages = None,sleep=0):
    url = f"{BASE.strip("/")}/{page.strip("/")}/"
    rows = []
    pages = 0

    while url:
        data = cl_get(url,headers=headers,params=params) 

        for obj in data.get("results",[]):
            rows.append(obj)
        
        url = data.get("next")
        params = None

        pages += 1

        if max_pages and pages >= max_pages:
            break

        if sleep > 0:
            time.sleep(sleep)
    
    return pd.DataFrame(rows)


def cl_paginate_list(page,headers={},params=None,max_pages = None,sleep=0):
    url = f"{BASE.strip("/")}/{page.strip("/")}/"
    rows = []
    pages = 0

    while url:
        data = cl_get(url,headers=headers,params=params) 

        for obj in data.get("results",[]):
            rows.append(obj)
        
        url = data.get("next")
        params = None

        pages += 1

        if max_pages and pages >= max_pages:
            break

        if sleep > 0:
            time.sleep(sleep)
    
    return rows


def cl_paginate_list_generator(page, headers={}, params=None, max_pages=None, sleep=0):
    """
    Yield result objects across paginated CourtListener responses one at a time.

    This is a streaming variant of ``cl_paginate_list`` that avoids building the
    full list in memory.
    """
    url = f"{BASE.strip('/')}/{page.strip('/')}/"
    pages = 0

    while url:
        data = cl_get(url, headers=headers, params=params)

        for obj in data.get("results", []):
            yield obj

        url = data.get("next")
        params = None
        pages += 1

        if max_pages and pages >= max_pages:
            break

        if sleep > 0:
            time.sleep(sleep)

        
