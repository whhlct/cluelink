"""Add puzzle generation and gameplay tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_gameplay"
down_revision = "0006_wikipedia_monthly_pageviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "puzzles",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("puzzle_type", sa.String(), nullable=False),
        sa.Column("difficulty", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("public_payload", postgresql.JSONB(), nullable=False),
        sa.Column("policy", postgresql.JSONB(), nullable=False),
        sa.Column("generation_version", sa.String(), nullable=False),
        sa.Column("prompt_fingerprint", sa.String(), nullable=False, unique=True),
        sa.Column("disabled_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_puzzles_available", "puzzles", ["status", "puzzle_type", "difficulty"])
    op.create_table(
        "puzzle_solutions",
        sa.Column("puzzle_id", sa.String(), sa.ForeignKey("puzzles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("solution_payload", postgresql.JSONB(), nullable=False),
        sa.Column("optimal_moves", sa.Integer()),
        sa.Column("quality", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("stats", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("puzzle_id", sa.String(), sa.ForeignKey("puzzles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("failure_reason", sa.String()),
        sa.Column("current_entity_id", sa.String()),
        sa.Column("move_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("guess_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wrong_guess_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("guessed_entity_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("stars", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_game_sessions_puzzle", "game_sessions", ["puzzle_id"])
    op.create_table(
        "game_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "sequence", name="uq_game_events_session_sequence"),
    )
    op.create_index("ix_game_events_session_sequence", "game_events", ["session_id", "sequence"])


def downgrade() -> None:
    op.drop_index("ix_game_events_session_sequence", table_name="game_events")
    op.drop_table("game_events")
    op.drop_index("ix_game_sessions_puzzle", table_name="game_sessions")
    op.drop_table("game_sessions")
    op.drop_table("generation_runs")
    op.drop_table("puzzle_solutions")
    op.drop_index("ix_puzzles_available", table_name="puzzles")
    op.drop_table("puzzles")
