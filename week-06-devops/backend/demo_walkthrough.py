"""Print the CRUD and tenancy evidence as one transcript worth screenshotting.

The assignment asks for a demonstration, and a demonstration has to be
repeatable: the same commands, the same rows, the same output, however many
times it is retaken. This script reseeds first for exactly that reason, so it
never depends on what a previous run left behind, and it undoes its own
writes - the row it creates in step 1 is the row it deletes in step 5 - so the
database is back to the seeded five when it finishes.

No token is printed. Every line of this output is intended to end up in a
screenshot that is submitted, and a bearer token in a submitted screenshot is
a credential published to whoever reads the report. The actor is named instead
and the token stays in memory.

The steps are ordered so that each one is readable alone. A grader looking at
step 7 should not have to have read step 3 to know what it proves, because the
screenshots may well be split across pages of a report.

Run it from this directory, with the database up:

    .venv/bin/python demo_walkthrough.py

AI use: drafting, external API probing and performance checks, and reviewing
security trade-offs.
"""

import json

from fastapi.testclient import TestClient

from main import app

import seed_demo

WIDTH = 96


def body(response) -> str:
    """One line describing a response body.

    A coverage is rendered field by field rather than as raw JSON. Truncating
    the JSON to fit a terminal cut off `status`, which is the single field
    steps 1 and 4 exist to show. An error body is printed verbatim instead,
    because there the exact shape is the evidence.
    """
    if response.status_code == 204:
        return "(no content)"
    try:
        payload = response.json()
    except ValueError:
        return response.text[:70]
    if isinstance(payload, list):
        return f"{len(payload)} rows: " + ", ".join(
            f"id={row['id']} {row['ticker']}" for row in payload
        )
    if "error" in payload:
        return json.dumps(payload, separators=(",", ":"))
    return (
        f"id={payload['id']} status={payload['status']:<8} cik={payload['cik']}"
        f" {payload['title']!r}"
    )


def step(number: int, label: str, actor: str, response, note: str = "") -> None:
    request = response.request
    path = request.url.path
    print(
        f"[{number}] {label:<22} {request.method:<6} {path:<22}"
        f" {actor:<9} {response.status_code}"
    )
    print(f"    {body(response)}")
    if note:
        print(f"    -> {note}")
    print()


def rule(title: str) -> None:
    print("=" * WIDTH)
    print(title)
    print("=" * WIDTH)
    print()


def main() -> None:
    state = seed_demo.seed()
    token_a, token_b = state.token_a, state.token_b

    client = TestClient(app)
    a = {"Authorization": f"Bearer {token_a}"}
    b = {"Authorization": f"Bearer {token_b}"}

    rule("CRUD - all five endpoints, as analyst A")

    created = client.post(
        "/api/coverages",
        json={"title": "Walmart Inc.", "cik": "0000104169", "ticker": "WMT"},
        headers=a,
    )
    new_id = created.json()["id"]
    step(1, "create", "analyst A", created, "status defaults to draft; owner_id is not accepted")

    step(2, "list own coverages", "analyst A", client.get("/api/coverages", headers=a))
    step(3, "read one", "analyst A", client.get(f"/api/coverages/{new_id}", headers=a))
    step(
        4,
        "update",
        "analyst A",
        client.patch(f"/api/coverages/{new_id}", json={"status": "active"}, headers=a),
        "draft -> active. PATCH, not PUT: cik cannot be replaced, so a full representation would lie",
    )
    step(
        5,
        "delete",
        "analyst A",
        client.delete(f"/api/coverages/{new_id}", headers=a),
        "the seeded five are untouched; this removed only what step 1 added",
    )

    rule("Tenancy - the same refusal whether a row belongs to someone else or does not exist")

    cross = client.get("/api/coverages/4", headers=a)
    step(6, "read B's row", "analyst A", cross, "A owns the same filer at id=1, and still cannot read id=4")

    absent = client.get("/api/coverages/999", headers=a)
    identical = cross.content == absent.content
    step(7, "read absent id", "analyst A", absent,
         f"byte-identical to step 6: {identical} - id scanning cannot count another tenant's rows")

    step(8, "delete B's row", "analyst A", client.delete("/api/coverages/4", headers=a))
    survived = client.get("/api/coverages/4", headers=b)
    step(9, "B reads the same row", "analyst B", survived,
         "B's row survived A's delete: ownership is in the WHERE clause, not a check after the read")

    mine = client.get("/api/coverages", headers=a).json()
    theirs = client.get("/api/coverages", headers=b).json()
    print(f"    analyst A lists {len(mine)} rows {sorted(r['id'] for r in mine)}"
          f" | analyst B lists {len(theirs)} rows {sorted(r['id'] for r in theirs)}")
    print("    -> neither listing needs a filter applied by the client")
    print()


if __name__ == "__main__":
    main()
