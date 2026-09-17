from dotenv import load_dotenv
from langchain_community.agent_toolkits import SQLDatabaseToolkit, create_sql_agent
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine

from db import get_db
from llm.models import get_llm
from prompts.schema_context import format_for_prompt

BLOCKED_KEYWORDS = ("insert", "update", "delete", "drop", "alter", "truncate", "create", "replace")

TABLE_KEYWORDS = (
    "ticket", "tickets", "support", "priority", "status", "category", "agent",
    "rating", "resolution", "response", "customer", "created", "issue",
)


def check_guardrail(question: str) -> None:
    lowered = question.lower()
    if any(word in lowered for word in BLOCKED_KEYWORDS):
        raise ValueError("Only read-only questions are allowed.")
    if not any(word in lowered for word in TABLE_KEYWORDS):
        raise ValueError("It looks like you strayed too far, Question must be about the support ticket data." \
        "I'd be happy to help about anything related to support tickets, such as ticket counts, average resolution times, agent performance, and customer ratings.")


AGENT_BEHAVIOR_PROMPT = """You are a support-ticket data analyst. You answer
natural-language questions by generating and running SQL against a single
read-only SQLite table.

IMPORTANT — scope: You must ONLY answer the part(s) of the question about
this table. If a question bundles in ANYTHING unrelated (general knowledge,
trivia, writing code/algorithms, other topics), do NOT answer that part
under any circumstances.. Reply to the
unrelated part with exactly: "I can only help with support ticket
data (tickets, priority, status, category, agent performance, response/
resolution times, customer ratings)."


Rules:
- When a question implies a time window (e.g. "this week", "this month",
  "not resolved within 12 hours"), compute it relative to the current
  timestamp using SQLite datetime functions against created_at.
- Give a direct, concise natural-language answer citing the actual number(s)
  found
"""


def _build_system_prompt() -> str:
    return f"{AGENT_BEHAVIOR_PROMPT}\n\n{format_for_prompt()}"


SYSTEM_PROMPT = _build_system_prompt()


def answer_query(question: str) -> dict:
    check_guardrail(question)

    engine = create_engine("sqlite://", creator=get_db)
    db = SQLDatabase(engine)
    llm = get_llm()

    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    agent = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        prefix=SYSTEM_PROMPT,
        agent_type="tool-calling",
        verbose=False,
    )
    result = agent.invoke({"input": question})
    return {"question": question, "answer": result.get("output", "")}


if __name__ == "__main__":
    load_dotenv()
    sample_questions = [
        "How many tickets are currently open?",
        "Which agent has the lowest average customer rating?",
        "What is the average customer rating for Technical category tickets?",
    ]
    for q in sample_questions:
        print(answer_query(q))
