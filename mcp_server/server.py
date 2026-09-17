from mcp.server.fastmcp import FastMCP

from db import get_db
from prompts.schema_context import format_for_prompt

mcp = FastMCP("support-tickets")


@mcp.tool()
def get_schema() -> str:
    return format_for_prompt()


@mcp.tool()
def query_tickets(sql: str) -> list[dict]:
    if not sql.strip().lower().startswith("select"):
        raise ValueError("Only SELECT statements are allowed.")

    conn = get_db()
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [dict(zip(columns, row)) for row in rows]


if __name__ == "__main__":
    mcp.run()
