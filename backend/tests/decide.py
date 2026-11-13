"""Make the choices the colonel makes on the preview, for tests about what
happens after them.

Every value that would change on a family we already have needs his choice
before Import is allowed. Tests about saving (history, children, extras) are
not about that choice, so they take the sheet's value for everything, as he
would by pressing "Take Excel".
"""

from app.services.import_preview import build_preview


def take_the_sheet(session, batch, sheet, match: str = "new") -> None:
    """Choose "Take Excel" for every change, and `match` for every possible duplicate."""
    overrides = dict(batch.row_overrides or {})
    # Twice: a possible duplicate marked "same" only shows its changes afterwards.
    for _ in range(2):
        preview = build_preview(
            session, sheet, batch.confirmed_mapping, overrides, batch.added_fields or {}
        )
        for row in preview.rows:
            entry = dict(overrides.get(str(row.row_number)) or {"skip": False, "values": {}})
            if row.action.value == "needs_decision" and row.match_choice is None:
                entry["match"] = match
            entry["decisions"] = {
                **(entry.get("decisions") or {}),
                **{c.field_name: "excel" for c in row.changes if c.decision is None},
            }
            overrides[str(row.row_number)] = entry
    batch.row_overrides = overrides
    session.flush()


def take_the_sheet_via_api(client, import_id: int, match: str = "new") -> dict:
    """The same through the API, as the screen does it. Returns the last preview."""
    preview = client.post(f"/api/imports/{import_id}/preview").json()
    for _ in range(2):
        for row in preview["rows"]:
            body: dict = {}
            if row["action"] == "needs_decision" and row["match_choice"] is None:
                body["match"] = match
            waiting = {c["field_name"]: "excel" for c in row["changes"] if c["decision"] is None}
            if waiting:
                body["decisions"] = waiting
            if body:
                preview = client.put(
                    f"/api/imports/{import_id}/rows/{row['row_number']}/decision", json=body
                ).json()
    return preview
