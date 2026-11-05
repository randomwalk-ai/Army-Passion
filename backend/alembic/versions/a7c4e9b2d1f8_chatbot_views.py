"""chatbot views, derived child facts, answer feedback

Revision ID: a7c4e9b2d1f8
Revises: f3a9c7d1e2b4
Create Date: 2026-11-05

The chatbot's searches run against simple views in their own schema, "ask",
instead of the raw tables: plain column names, readable values (no codes like
"verified_signed"), the class as a number, CEA results ready to filter on.
The search runs with search_path = ask, so it cannot see the raw tables.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c4e9b2d1f8"
down_revision: str | None = "f3a9c7d1e2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


VIEWS = {
    "families": """
        SELECT f.family_code,
               f.primary_contact_name AS widow_name,
               lower(f.nok_relationship) AS relationship,
               f.primary_phone AS phone,
               f.alternate_phone AS other_phone,
               f.email,
               f.preferred_language::text AS language,
               f.whatsapp_opted_in,
               f.village_or_town AS village, f.town, f.tehsil, f.post_office,
               f.district, f.state, f.pincode,
               f.bank_name, f.bank_branch, f.bank_account_number, f.bank_ifsc,
               (f.bank_account_number IS NOT NULL AND f.bank_account_number <> '') AS has_bank_account,
               f.ppo_number,
               f.monthly_pension_amount AS monthly_pension,
               f.annual_income,
               (SELECT count(*) FROM public.family_members m
                 WHERE m.family_id = f.id
                   AND m.relation::text IN ('son', 'daughter', 'other_dependent')) AS children_count,
               f.last_contacted_on,
               (current_date - f.last_contacted_on) AS days_since_contact,
               f.last_verified_on,
               s.full_name AS soldier_name, s.rank AS soldier_rank,
               s.service_number, s.regiment, s.unit,
               s.date_of_death,
               replace(s.cause_category::text, '_', ' ') AS cause,
               s.cause_sub_category AS cause_detail,
               f.co_unit_name, f.co_unit_phone,
               f.notes
          FROM public.families f
          JOIN public.soldiers s ON s.id = f.soldier_id
         WHERE NOT f.is_draft
    """,
    "members": """
        SELECT m.full_name AS name,
               replace(m.relation::text, '_', ' ') AS relation,
               m.gender, m.date_of_birth,
               date_part('year', age(current_date, m.date_of_birth))::int AS age,
               m.marital_status, m.is_married, m.is_employed, m.has_disability,
               f.family_code, f.primary_contact_name AS widow_name,
               f.primary_phone AS phone, f.district, f.state
          FROM public.family_members m
          JOIN public.families f ON f.id = m.family_id
         WHERE NOT f.is_draft
    """,
    "children": """
        SELECT m.full_name AS child_name,
               replace(m.relation::text, '_', ' ') AS relation,
               m.gender, m.date_of_birth,
               date_part('year', age(current_date, m.date_of_birth))::int AS age,
               (m.date_of_birth + interval '18 years')::date AS turns_18_on,
               m.is_studying,
               m.education_level AS education,
               cf.class_number,
               m.school_name, m.is_hostel, m.has_disability,
               m.marital_status, m.is_married, m.is_employed,
               f.family_code, f.primary_contact_name AS widow_name,
               f.primary_phone AS phone, f.district, f.state,
               cf.cea_year, cf.cea_status, cf.cea_reason, cf.cea_amount
          FROM public.family_members m
          JOIN public.families f ON f.id = m.family_id
          LEFT JOIN public.child_facts cf ON cf.member_id = m.id
         WHERE NOT f.is_draft
           AND m.relation::text IN ('son', 'daughter', 'other_dependent')
    """,
    "cea": """
        SELECT f.family_code, f.primary_contact_name AS widow_name,
               f.district, f.state,
               m.full_name AS child_name,
               c.academic_year, c.status, c.reason, c.amount,
               c.age_at_start, c.class_number
          FROM public.cea_by_year c
          JOIN public.family_members m ON m.id = c.member_id
          JOIN public.families f ON f.id = m.family_id
         WHERE NOT f.is_draft
    """,
    "applications": """
        SELECT a.reference_code AS reference,
               f.family_code, f.primary_contact_name AS widow_name,
               f.district, f.state,
               sc.name AS scheme, sc.category AS scheme_category,
               replace(a.stage::text, '_', ' ') AS stage,
               a.stage_changed_on AS stage_since,
               (current_date - a.stage_changed_on) AS days_in_stage,
               (a.stage::text NOT IN ('money_credited', 'rejected')
                AND (current_date - a.stage_changed_on) > a.stuck_after_days) AS is_stuck,
               a.amount_claimed, a.amount_credited, a.credited_on,
               a.ksb_dak_id, a.rejection_reason
          FROM public.applications a
          JOIN public.families f ON f.id = a.family_id
          JOIN public.schemes sc ON sc.id = a.scheme_id
         WHERE NOT f.is_draft
    """,
    "deaths": """
        SELECT f.family_code,
               s.full_name AS soldier_name, s.rank, s.regiment, s.unit, s.service_number,
               s.date_of_death,
               extract(year FROM s.date_of_death)::int AS year,
               extract(month FROM s.date_of_death)::int AS month,
               trim(to_char(s.date_of_death, 'Month')) AS month_name,
               CASE
                 WHEN extract(month FROM s.date_of_death) IN (12, 1, 2) THEN 'winter'
                 WHEN extract(month FROM s.date_of_death) IN (3, 4, 5) THEN 'summer'
                 WHEN extract(month FROM s.date_of_death) IN (6, 7, 8, 9) THEN 'monsoon'
                 WHEN extract(month FROM s.date_of_death) IN (10, 11) THEN 'post-monsoon'
               END AS season,
               replace(s.cause_category::text, '_', ' ') AS cause,
               s.cause_sub_category AS cause_detail,
               s.place_of_death, s.district_of_death, s.state_of_death,
               s.weather_at_death AS weather,
               replace(s.duty_status::text, '_', ' ') AS duty_status,
               f.district AS family_district, f.state AS family_state
          FROM public.soldiers s
          JOIN public.families f ON f.soldier_id = s.id
         WHERE NOT f.is_draft
    """,
    "calls": """
        SELECT f.family_code, f.primary_contact_name AS widow_name, f.district,
               replace(i.interaction_type::text, '_', ' ') AS type,
               i.occurred_at::date AS date,
               i.language::text AS language,
               i.summary_english AS summary,
               i.follow_up_needed, i.follow_up_note
          FROM public.interactions i
          JOIN public.families f ON f.id = i.family_id
         WHERE NOT f.is_draft
    """,
    "postings": """
        SELECT CASE WHEN p.user_id IS NOT NULL THEN 'officer' ELSE 'soldier' END AS person_type,
               coalesce(u.full_name, s.full_name) AS person_name,
               coalesce(u.rank, s.rank) AS rank,
               p.unit, p.formation, p.place, p.state, p.from_year, p.to_year,
               f.family_code
          FROM public.postings p
          LEFT JOIN public.users u ON u.id = p.user_id
          LEFT JOIN public.soldiers s ON s.id = p.soldier_id
          LEFT JOIN public.families f ON f.soldier_id = s.id
    """,
    "schemes": """
        SELECT name, code, category, authority, benefit_amount, is_recurring, is_active
          FROM public.schemes
    """,
    "eligibility": """
        SELECT f.family_code, f.primary_contact_name AS widow_name, f.district,
               sc.name AS scheme,
               replace(e.status::text, '_', ' ') AS status,
               e.becomes_eligible_on
          FROM public.family_scheme_eligibility e
          JOIN public.families f ON f.id = e.family_id
          JOIN public.schemes sc ON sc.id = e.scheme_id
         WHERE NOT f.is_draft
    """,
    "problems": """
        SELECT f.family_code, f.primary_contact_name AS widow_name, f.district,
               replace(i.issue_code::text, '_', ' ') AS problem,
               i.severity::text AS severity,
               i.status::text AS status,
               i.description
          FROM public.data_quality_issues i
          JOIN public.families f ON f.id = i.family_id
         WHERE NOT f.is_draft
    """,
    "documents": """
        SELECT f.family_code, f.primary_contact_name AS widow_name, f.district,
               m.full_name AS person,
               replace(d.doc_type::text, '_', ' ') AS document_type,
               replace(d.status::text, '_', ' ') AS status,
               d.is_supporting,
               d.created_at::date AS added_on
          FROM public.documents d
          JOIN public.families f ON f.id = d.family_id
          LEFT JOIN public.family_members m ON m.id = d.family_member_id
         WHERE NOT f.is_draft
    """,
}


def upgrade() -> None:
    op.create_table(
        "child_facts",
        sa.Column("member_id", sa.Integer(),
                  sa.ForeignKey("family_members.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("class_number", sa.Integer()),
        sa.Column("cea_year", sa.String(20)),
        sa.Column("cea_status", sa.String(30)),
        sa.Column("cea_reason", sa.Text()),
        sa.Column("cea_amount", sa.Integer()),
    )
    op.create_table(
        "cea_by_year",
        sa.Column("member_id", sa.Integer(),
                  sa.ForeignKey("family_members.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("academic_year", sa.String(20), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("amount", sa.Integer()),
        sa.Column("age_at_start", sa.Integer()),
        sa.Column("class_number", sa.Integer()),
    )
    op.create_table(
        "derived_state",
        sa.Column("name", sa.String(60), primary_key=True),
        sa.Column("fingerprint", sa.String(200), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "answer_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("answer", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_answer_feedback_rating", "answer_feedback", ["rating"])

    op.execute("CREATE SCHEMA IF NOT EXISTS ask")
    for name, body in VIEWS.items():
        op.execute(f"CREATE OR REPLACE VIEW ask.{name} AS {body}")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS ask CASCADE")
    op.drop_index("ix_answer_feedback_rating", table_name="answer_feedback")
    op.drop_table("answer_feedback")
    op.drop_table("derived_state")
    op.drop_table("cea_by_year")
    op.drop_table("child_facts")
