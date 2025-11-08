from .api import cl_paginate, cl_get
from dotenv import load_dotenv
import os
import time

load_dotenv()

BASE = os.getenv("BASE")

def federal_dist_jud_position_dates(person_id,sleep=.75):

    person_url = f"{BASE.strip('/')}/people/{person_id}/"

    time.sleep(sleep)
    person_results = cl_get(person_url)

    # Calling a url for a specific person means we don't have a "results"
    # portion before we actually get the info we want
    positions = person_results["positions"]

    date_ranges = []
    for position_url in positions:
        position_headers = {"fields": "date_start,date_termination,court,position_type"}

        time.sleep(sleep)
        
        position_results = cl_get(position_url, position_headers)
        date_start = position_results["date_start"]
        date_termination = position_results["date_termination"]

        if position_results["court"] and position_results["court"]["jurisdiction"] == "FD" and position_results["position_type"] == "jud":
            date_ranges.append((date_start,date_termination))

    return date_ranges


    