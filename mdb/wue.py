#!/usr/bin/python3
'''Results of Feedback control: reads temperature and pump
activations, grouped by day from elastic search, and does a scatter
plot.
'''

import requests
import json
import pandas as pd
# Disable GUI backend for web server compatibility
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys
import io

HEADERS = {"Content-Type": "application/json"}

# DSL Query: groups by day
query = {
    "size": 0,
    "query": {
        "bool": {
            "filter": [
                { "term": { "logger_name": "rpi.feedback_control" } },
                { "range": { "@timestamp": { "gte": "now-90d/d" } } }
            ]
        }
    },
    "aggregations": {
        "daily_buckets": {
            "date_histogram": {
                "field": "@timestamp",
                "calendar_interval": "1d"
            },
            "aggs": {
                "activations": {
                    "filter": { "term": { "message.keyword": "Activate" } },
                    "aggs": {
                        "total_duration_sec": {
                            "sum": {
                                "field": "duration",
                                "missing": 60  # Default to 1 minute if field is missing
                            }
                        }
                    }
                },
                "high_temp": {
                    "percentiles": { "field": "Temperature" , "percents": [90]}
                }
            }
        }
    }
}


def get_data(es_url):
    # Fetch Data via HTTP POST
    response = requests.post(es_url, headers=HEADERS, data=json.dumps(query))
    response.raise_for_status()
    raw_data = response.json()

    # Parse JSON into pandas data frame
    buckets = raw_data['aggregations']['daily_buckets']['buckets']
    parsed_data = []

    for b in buckets:
        # Extract total seconds and convert to minutes
        total_sec = b['activations']['total_duration_sec']['value']
        duration_mins = total_sec / 60.0

        parsed_data.append({
            "timestamp": b['key_as_string'],
            "activation_mins": duration_mins,
            "high_temp": b['high_temp']['values']['90.0']
        })

    df = pd.DataFrame(parsed_data)
    # Drop days where no temperature was recorded to avoid plotting nulls
    df = df.dropna(subset=['high_temp'])
    # Format the timestamp into a shorter, readable date string (YYYY-MM-DD)
    df['short_date'] = pd.to_datetime(df['timestamp']).dt.strftime('%m-%d')

    return df


def plot(df):
    plt.figure(figsize=(10, 6))
    plt.scatter(df['activation_mins'], df['high_temp'], s=64, c=df.index, cmap='viridis')

    # color legend (time in days)
    cb = plt.colorbar(label="Days ago")
    cticks = cb.get_ticks()
    cb.set_ticklabels(map(lambda x: int(cticks[-1]-x),cticks))

    # labels data points by date
    for index, row in df.iterrows():
        plt.annotate(
            row['short_date'],
            (row['activation_mins'], row['high_temp']),
            textcoords="offset points",
            xytext=(5, 5),
            ha='left',
            fontsize=6
        )

    plt.xlabel('Activation duration (min/day)')
    plt.ylabel('High (90th-p) Temperature (°C)')
    plt.grid(True, alpha=0.3)

    buf = io.BytesIO()
    # Save the plot into the buffer as a PNG
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close() # Close figure to free up memory
    buf.seek(0) # Rewind the buffer's file pointer to the beginning
    return buf.getvalue() # Return the raw bytes
