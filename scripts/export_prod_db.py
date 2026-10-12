import psycopg2
import sqlite3
import pandas as pd
from sqlalchemy import create_engine

print("Connecting to PostgreSQL...")
pg_engine = create_engine('postgresql://anomaly_agent:2k%2FH3a2I4kR0luzxraefLfWca8bk4iSGK%2BS2Q5TuXXI%3D@localhost:5433/homelab_anomaly')

print("Fetching data from PostgreSQL...")
df = pd.read_sql("SELECT * FROM node_metrics", pg_engine)

print(f"Loaded {len(df)} rows. Saving to sqlite...")
sqlite_engine = create_engine('sqlite:///prod_telemetry.db')
df.to_sql('node_metrics', sqlite_engine, if_exists='replace', index=False)

print("Export complete: prod_telemetry.db")
