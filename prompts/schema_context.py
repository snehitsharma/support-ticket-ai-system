TABLE_NAME = "support_tickets"
 
COLUMN_DESCRIPTIONS = {
    "ticket_id": "Unique ticket identifier.",
    "created_at": "Timestamp the ticket was created. Used for age-based checks (e.g. 'older than 24 hours').",
    "category": "Issue category: Billing, Technical, or General.",
    "priority": "Ticket urgency: Low, Medium, High, or Critical.",
    "status": "Current ticket status: Open, Resolved, or Escalated.",
    "response_time_hrs": "Hours from creation to the FIRST AGENT RESPONSE (not resolution).",
    "resolution_time_hrs": "Hours from creation to full RESOLUTION. NULL if not yet resolved.",
    "agent_id": "Identifier of the support agent assigned to the ticket.",
    "customer_rating": "Post-resolution rating, 1-5. NULL if unresolved — exclude from averages, don't treat as 0.",
    "issue_summary": "Free-text description of the issue.",
}
 
 
def format_for_prompt() -> str:
    lines = [f"Table: {TABLE_NAME}", "", "Columns:"]
    lines += [f"- {col}: {desc}" for col, desc in COLUMN_DESCRIPTIONS.items()]
    return "\n".join(lines)