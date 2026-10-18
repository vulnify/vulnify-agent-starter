"""Fake business tools. Replace them with your real ones."""


def read_ticket(ticket_id: str) -> str:
    return f"Ticket {ticket_id}: customer asks for their invoice history."


def export_customers(to: str, records: int) -> str:
    return f"Exported {records} customer records to {to}."


def delete_table(table: str) -> str:
    return f"Dropped table {table}."
