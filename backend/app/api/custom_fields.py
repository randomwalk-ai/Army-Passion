"""Extra fields the colonel has approved.

These feed the type-to-search box on the mapping screen: he sees our standard
fields, the extra fields already approved, and the option to add a new one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_session
from app.models import CustomField, slugify

router = APIRouter(prefix="/api/custom-fields", tags=["custom fields"])


class CustomFieldOut(BaseModel):
    key: str
    label: str
    description: str | None
    first_seen_as: str | None
    times_used: int


class CustomFieldIn(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    description: str | None = None
    # The sheet heading it came from, kept so its origin is traceable.
    first_seen_as: str | None = None
    import_id: int | None = None


def _out(field: CustomField) -> CustomFieldOut:
    return CustomFieldOut(
        key=field.key,
        label=field.label,
        description=field.description,
        first_seen_as=field.first_seen_as,
        times_used=field.times_used,
    )


@router.get("", response_model=list[CustomFieldOut])
def list_custom_fields(session: Session = Depends(get_session)) -> list[CustomFieldOut]:
    fields = session.scalars(
        select(CustomField)
        .where(CustomField.is_active.is_(True))
        .order_by(CustomField.times_used.desc(), CustomField.label)
    ).all()
    return [_out(f) for f in fields]


@router.post("", response_model=CustomFieldOut, status_code=201)
def create_custom_field(
    body: CustomFieldIn, session: Session = Depends(get_session)
) -> CustomFieldOut:
    """Approve a new extra field.

    If one with the same name already exists it is returned rather than
    duplicated — that is the whole point of keeping this list.
    """
    label = body.label.strip()
    key = slugify(label)
    if not key:
        raise HTTPException(
            status_code=400, detail="That name has no letters or numbers in it."
        )

    existing = session.scalar(select(CustomField).where(CustomField.key == key))
    if existing:
        if not existing.is_active:
            existing.is_active = True
            session.commit()
        return _out(existing)

    user = current_user(session)
    field = CustomField(
        key=key,
        label=label,
        description=body.description,
        first_seen_as=body.first_seen_as,
        created_from_import_id=body.import_id,
        created_by_user_id=user.id if user else None,
    )
    session.add(field)
    session.commit()
    return _out(field)


@router.delete("/{key}")
def retire_custom_field(key: str, session: Session = Depends(get_session)) -> dict:
    """Stop offering a field. Values already stored are left alone."""
    field = session.scalar(select(CustomField).where(CustomField.key == key))
    if field is None:
        raise HTTPException(status_code=404, detail="No such extra field.")
    field.is_active = False
    session.commit()
    return {"retired": key}
