from .api import cl_paginate, cl_get
from dotenv import load_dotenv
import os

load_dotenv()

BASE = os.getenv("BASE")

def federal_dist_jud_position_dates(person_id):

    url = f"{BASE.strip('/')}/people/{person_id}/"

    results = cl_get(url)

    # Calling a url for a specific person means we don't have a "results"
    # portion before we actually get the info we want
    positions = results["positions"]

    