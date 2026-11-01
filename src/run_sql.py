"""
Loads data/*.csv into an in-memory DuckDB database using sql/schema.sql,
then runs every query in sql/metrics.sql and prints the results.

Run:  python src/run_sql.py
"""
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
TABLES = ["facilities", "provider_directory", "discharge_plans",
          "outbound_referrals", "referral_events", "discharge_date_changes"]

con = duckdb.connect()
con.execute((ROOT / "sql" / "schema.sql").read_text())
for t in TABLES:
    path = (ROOT / "data" / f"{t}.csv").as_posix()
    con.execute(f"INSERT INTO {t} SELECT * FROM read_csv('{path}', header=true, all_varchar=true)")

sql = (ROOT / "sql" / "metrics.sql").read_text()
titles = re.findall(r"^-- (M\d+\..*)$", sql, flags=re.M)
statements = [s.strip() for s in re.sub(r"--.*", "", sql).split(";") if s.strip()]
for title, stmt in zip(titles, statements):
    print(f"\n{title}")
    print(con.execute(stmt).fetchdf().to_string(index=False))
