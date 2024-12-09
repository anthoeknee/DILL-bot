"""Initial migration

Revision ID: 088dc53612e1
Revises:
Create Date: 2024-12-08 23:01:41.721200

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "088dc53612e1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ManagedServer table
    op.create_table(
        "managed_servers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.String(), nullable=False),
        sa.Column("forum_channel_id", sa.String(), nullable=False),
        sa.Column("spreadsheet_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id"),
    )

    # Create ValidTag table
    op.create_table(
        "valid_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("tag_type", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "name", name="unique_tag_per_server"),
    )

    # Create BotSetting table
    op.create_table(
        "bot_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("bot_settings")
    op.drop_table("valid_tags")
    op.drop_table("managed_servers")
