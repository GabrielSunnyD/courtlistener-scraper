from .api import cl_paginate, cl_get
from dotenv import load_dotenv
import os
import time
from datetime import datetime, date
import ast

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


def get_date_ranges_for_person(date_ranges_df,person_id):
    row = date_ranges_df.loc[date_ranges_df["person_id"] == person_id, "date_ranges"]
    if row.empty:
        return []  # or raise an error
    
    # row.iloc(0) gives the string version of the list
    range_str = row.iloc[0]
    
    # Safely parse the string into a Python list
    return ast.literal_eval(range_str)


def dockets_in_date_range(person_id, date_ranges,sleep=0):
    date_format = "%Y-%m-%d"

    params = {"assigned_to":f"{person_id}"}
    dockets_df = cl_paginate("dockets",params=params,sleep=sleep)

    date_ranges_mask = []
    for index, row in dockets_df.iterrows():
        if row["date_filed"]:
            date_filed = datetime.strptime(row["date_filed"], date_format)
        else:
            return "date_filed does not exist on one of this judges dockets"

        in_range = False
        for date_range in date_ranges:
            if date_range[0]:
                date_start = datetime.strptime(date_range[0], date_format)
            else:
                return "judge has a date range with no start date"
            if date_range[1]:
                date_end = datetime.strptime(date_range[1], date_format)
            else:
                date_end = None
            
            if date_end:
                if date_start <= date_filed <= date_end:
                    in_range = True
                    break
            else:
                if date_start <= date_filed:
                    in_range = True
                    break

        date_ranges_mask.append(in_range)


    return dockets_df[date_ranges_mask]



def opinion_ids_from_dockets(docket_list,sleep=0):

    opinions_list = []
    for docket_id in docket_list:

        docket_url = f"{BASE.strip('/')}/dockets/{docket_id}/"
        params = {"fields":"clusters"}
        
        time.sleep(sleep)
        docket_result = cl_get(docket_url,params=params)

        clusters = docket_result["clusters"]

        if len(clusters) == 0:
            continue

        if len(clusters) > 1:
            opinions_list.append("docket has multiple clusters")
            continue

        for cluster_url in clusters:
            
            params = {"fields":"sub_opinions"}

            time.sleep(sleep)
            cluster_result = cl_get(cluster_url,params=params)

            sub_opinions = cluster_result["sub_opinions"]

            if len(sub_opinions) > 1:
                pass


            
