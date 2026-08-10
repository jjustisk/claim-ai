import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from sqlalchemy.engine.url import make_url
from app.config import settings

RELATIONS_SQL = """
SELECT
    n.nspname AS schema,
    c.relname AS name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'S' THEN 'sequence'
    END AS type,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'S')
ORDER BY c.relname
"""


def print_psql_relations(rows: list[tuple[str, str, str, str]]) -> None:
    headers = ("Schema", "Name", "Type", "Owner")
    data = [headers] + [tuple(row) for row in rows]

    widths = [max(len(str(row[i])) for row in data) for i in range(4)]

    def line(cells: tuple[str, ...], sep: str = "|") -> str:
        return f" {cells[0]:<{widths[0]}} {sep} {cells[1]:<{widths[1]}} {sep} {cells[2]:<{widths[2]}} {sep} {cells[3]:<{widths[3]}} "

    title = "List of relations"
    print(title.rjust((sum(widths) + 13) // 2 + len(title) // 2))
    print(line(headers))
    print("+-".join("-" * w for w in widths) + "+")
    for row in rows:
        print(line(tuple(row)))
    print(f"({len(rows)} rows)")


url = make_url(settings.database_url)
conn = psycopg.connect(
    host=url.host,
    port=url.port,
    dbname=url.database,
    user=url.username,
    password=url.password,
    sslmode=url.query.get("sslmode", "require"),
)
cur = conn.cursor()
cur.execute(RELATIONS_SQL)
rows = cur.fetchall()

if rows:
    print_psql_relations(rows)
else:
    print("No relations found in schema public.")
    print("Run: uvicorn app.main:app --reload  (creates tables on startup)")

conn.close()
