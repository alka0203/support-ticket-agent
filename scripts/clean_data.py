"""Clean the raw ticket export into the shape defined by db/schema.sql.

Implements every decision recorded in data-notes.md:
  - snake_case columns matching the Postgres schema
  - categorical values remapped to the lowercase snake_case ENUM values in
    db/schema.sql (technical_issue, pending_customer_response, etc.) so the
    cleaned CSV loads straight into the typed columns with no further mapping
  - no imputation of the "closed-only" fields (resolution, time_to_resolution,
    customer_satisfaction_rating) or of first_response_time — their
    missingness is structural (tied to ticket_status) and is preserved as-is
  - no synthesized created_at / ticket-opened date — date_of_purchase keeps
    its real meaning, nothing stands in for a ticket-filed timestamp
  - retrieval_text built only from the fields data-notes.md identified as
    carrying real signal (ticket_type, ticket_subject, product_purchased,
    ticket_description) — resolution is deliberately excluded (100% filler)
"""
import sys
import pandas as pd

RAW_PATH = "data/raw/customer_support_tickets.csv"
OUT_PATH = "data/clean/tickets_clean.csv"

EXPECTED_ROWS = 8469

COLUMN_RENAME = {
    "Ticket ID": "ticket_id",
    "Customer Name": "customer_name",
    "Customer Email": "customer_email",
    "Customer Age": "customer_age",
    "Customer Gender": "customer_gender",
    "Product Purchased": "product_purchased",
    "Date of Purchase": "date_of_purchase",
    "Ticket Type": "ticket_type",
    "Ticket Subject": "ticket_subject",
    "Ticket Description": "ticket_description",
    "Ticket Status": "ticket_status",
    "Resolution": "resolution",
    "Ticket Priority": "ticket_priority",
    "Ticket Channel": "ticket_channel",
    "First Response Time": "first_response_time",
    "Time to Resolution": "time_to_resolution",
    "Customer Satisfaction Rating": "customer_satisfaction_rating",
}

# Source value -> ENUM value in db/schema.sql. Kept as explicit maps (not a
# blanket .str.lower().replace(' ', '_')) so a source value that doesn't
# match one of these fails loudly via the assertion below, instead of
# silently producing a snake_case string that isn't actually a valid ENUM
# member and would fail later at Postgres load time with a less clear error.
TICKET_TYPE_MAP = {
    "Technical issue": "technical_issue",
    "Billing inquiry": "billing_inquiry",
    "Cancellation request": "cancellation_request",
    "Refund request": "refund_request",
    "Product inquiry": "product_inquiry",
}
TICKET_STATUS_MAP = {
    "Open": "open",
    "Closed": "closed",
    "Pending Customer Response": "pending_customer_response",
}
TICKET_PRIORITY_MAP = {
    "Low": "low",
    "Medium": "medium",
    "High": "high",
    "Critical": "critical",
}
TICKET_CHANNEL_MAP = {
    "Email": "email",
    "Phone": "phone",
    "Chat": "chat",
    "Social media": "social_media",
}


def clean() -> pd.DataFrame:
    df = pd.read_csv(RAW_PATH)
    assert len(df) == EXPECTED_ROWS, (
        f"expected {EXPECTED_ROWS} rows (per data-notes.md), got {len(df)} — "
        "raw file changed, re-verify data-notes.md before trusting this output"
    )

    df = df.rename(columns=COLUMN_RENAME)

    df["ticket_type"] = df["ticket_type"].map(TICKET_TYPE_MAP)
    df["ticket_status"] = df["ticket_status"].map(TICKET_STATUS_MAP)
    df["ticket_priority"] = df["ticket_priority"].map(TICKET_PRIORITY_MAP)
    df["ticket_channel"] = df["ticket_channel"].map(TICKET_CHANNEL_MAP)
    df["customer_gender"] = df["customer_gender"].str.lower()

    for col in ["ticket_type", "ticket_status", "ticket_priority", "ticket_channel"]:
        unmapped = df[col].isna().sum()
        assert unmapped == 0, f"{unmapped} unmapped value(s) in {col} — source has a new category"

    # Replace the unresolved {product_purchased} placeholder in ticket_description
    # with the actual product name from the row. This is the only template
    # placeholder that has a corresponding data column — all other {…} patterns
    # in the text are Faker-generated code-snippet noise and cannot be resolved.
    df["ticket_description"] = df.apply(
        lambda r: r["ticket_description"].replace("{product_purchased}", r["product_purchased"])
        if isinstance(r["ticket_description"], str) else r["ticket_description"],
        axis=1,
    )

    df["date_of_purchase"] = pd.to_datetime(df["date_of_purchase"]).dt.date
    df["first_response_time"] = pd.to_datetime(df["first_response_time"], errors="coerce")
    df["time_to_resolution"] = pd.to_datetime(df["time_to_resolution"], errors="coerce")

    df["retrieval_text"] = (
        df["ticket_type"].str.replace("_", " ")
        + " | "
        + df["ticket_subject"]
        + " | "
        + df["product_purchased"]
        + " | "
        + df["ticket_description"]
    )

    return df


def verify(df: pd.DataFrame) -> None:
    """Cross-check the cleaned output against the exact numbers recorded in
    data-notes.md, so a silent regression in this script is caught here
    rather than surfacing later as a wrong SQL answer."""
    checks = []

    checks.append(("row count", len(df) == EXPECTED_ROWS))
    checks.append(("ticket_id unique", df["ticket_id"].is_unique))

    status_counts = df["ticket_status"].value_counts()
    checks.append(("pending_customer_response count", status_counts.get("pending_customer_response") == 2881))
    checks.append(("open count", status_counts.get("open") == 2819))
    checks.append(("closed count", status_counts.get("closed") == 2769))

    closed_mask = df["ticket_status"] == "closed"
    checks.append((
        "resolution non-null iff closed",
        (df["resolution"].notna() == closed_mask).all(),
    ))
    checks.append((
        "customer_satisfaction_rating non-null iff closed",
        (df["customer_satisfaction_rating"].notna() == closed_mask).all(),
    ))
    open_mask = df["ticket_status"] == "open"
    checks.append((
        "first_response_time null iff open",
        (df["first_response_time"].isna() == open_mask).all(),
    ))

    checks.append(("no customer_name/email dropped from base file", {"customer_name", "customer_email"} <= set(df.columns)))
    checks.append(("no created_at / ticket-opened column invented", "created_at" not in df.columns))
    checks.append(("resolution excluded from retrieval_text", not df["retrieval_text"].str.contains("Five tree those particular").any()))
    checks.append(("{product_purchased} placeholder resolved", not df["ticket_description"].str.contains(r"\{product_purchased\}", regex=True).any()))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed: {failed}")
        sys.exit(1)
    print(f"\nAll {len(checks)} checks passed.")


if __name__ == "__main__":
    df = clean()
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUT_PATH}\n")
    verify(df)
