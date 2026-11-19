"""Initial schema — campaigns table.

Revision ID: 001
Revises:
Create Date: 2026-03-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column("duration_seconds", sa.String(32), nullable=True),
        sa.Column("sample_rate", sa.String(16), nullable=True),
        sa.Column("audio_analysis", sa.JSON(), nullable=True),
        sa.Column("music_brief", sa.Text(), nullable=True),
        sa.Column("lore", sa.Text(), nullable=True),
        sa.Column("rag_context", sa.JSON(), nullable=True),
        sa.Column("social_media_proposals", sa.JSON(), nullable=True),
        sa.Column("selected_proposal_index", sa.String(8), nullable=True),
        sa.Column("thread_id", sa.String(255), nullable=True, unique=True),
        sa.Column(
            "workflow_status",
            sa.String(64),
            nullable=False,
            server_default="created",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_campaigns_thread_id", "campaigns", ["thread_id"])
    op.create_index("ix_campaigns_workflow_status", "campaigns", ["workflow_status"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_workflow_status", table_name="campaigns")
    op.drop_index("ix_campaigns_thread_id", table_name="campaigns")
    op.drop_table("campaigns")
