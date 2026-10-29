"""Stand-in business tools. Replace them with real ones. They only run after ALLOW."""


def read_ticket(ticket_id: str) -> str:
    return f"Ticket {ticket_id}: customer asks for their invoice history."


def export_report(to: str, records: int) -> str:
    return f"Exported {records} records to {to}."


def delete_table(table: str) -> str:
    return f"Dropped table {table}."
