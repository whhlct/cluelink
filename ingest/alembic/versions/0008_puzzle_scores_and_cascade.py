"""Store puzzle scores explicitly and cascade puzzle deletion to sessions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_puzzle_scores_and_cascade"
down_revision = "0007_gameplay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("puzzle_solutions", sa.Column("final_score", sa.Float()))
    op.add_column(
        "puzzle_solutions",
        sa.Column("score_factors", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute("""
        UPDATE puzzle_solutions
        SET final_score = (quality -> 'score' ->> 'total')::double precision,
            score_factors = COALESCE(quality -> 'score' -> 'factors', '{}'::jsonb)
        WHERE quality ? 'score'
    """)
    op.alter_column("puzzle_solutions", "score_factors", server_default=None)
    op.drop_constraint("game_sessions_puzzle_id_fkey", "game_sessions", type_="foreignkey")
    op.create_foreign_key(
        "game_sessions_puzzle_id_fkey",
        "game_sessions",
        "puzzles",
        ["puzzle_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("game_sessions_puzzle_id_fkey", "game_sessions", type_="foreignkey")
    op.create_foreign_key(
        "game_sessions_puzzle_id_fkey",
        "game_sessions",
        "puzzles",
        ["puzzle_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_column("puzzle_solutions", "score_factors")
    op.drop_column("puzzle_solutions", "final_score")
