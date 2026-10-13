"""Initial schema: business tables and ingestion audit tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Business tables ---
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("department", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("job", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_table(
        "hired_employees",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_hired_employees_department_id_departments",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_hired_employees_job_id_jobs"),
        sa.PrimaryKeyConstraint("id", name="pk_hired_employees"),
    )
    op.create_index("ix_hired_employees_datetime", "hired_employees", ["datetime"])
    op.create_index("ix_hired_employees_department_id", "hired_employees", ["department_id"])
    op.create_index("ix_hired_employees_job_id", "hired_employees", ["job_id"])

    # --- Ingestion audit tables ---
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("rows_read", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_loaded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_rejected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_ingestion_jobs_status_valid",
        ),
        sa.CheckConstraint(
            "table_name IN ('departments', 'jobs', 'hired_employees')",
            name="ck_ingestion_jobs_table_name_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
    )
    op.create_table(
        "load_rejections",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("raw_record", postgresql.JSONB(), nullable=False),
        sa.Column("errors", postgresql.JSONB(), nullable=False),
        sa.Column(
            "rejected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            name="fk_load_rejections_job_id_ingestion_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_load_rejections"),
    )
    op.create_index("ix_load_rejections_job_id", "load_rejections", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_load_rejections_job_id", table_name="load_rejections")
    op.drop_table("load_rejections")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_hired_employees_job_id", table_name="hired_employees")
    op.drop_index("ix_hired_employees_department_id", table_name="hired_employees")
    op.drop_index("ix_hired_employees_datetime", table_name="hired_employees")
    op.drop_table("hired_employees")
    op.drop_table("jobs")
    op.drop_table("departments")
