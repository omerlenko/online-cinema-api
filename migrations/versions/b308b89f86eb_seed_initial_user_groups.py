"""seed_initial_user_groups

Revision ID: b308b89f86eb
Revises: d437129f7309
Create Date: 2026-09-18 19:59:29.213941

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b308b89f86eb"
down_revision: Union[str, Sequence[str], None] = "d437129f7309"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_GROUP_NAMES = ["ADMIN", "MODERATOR", "USER"]

user_group_enum = postgresql.ENUM(
    *USER_GROUP_NAMES, name="usergroupenum", create_type=False
)

user_groups_table = sa.table(
    "user_groups",
    sa.column("id", sa.Integer),
    sa.column("name", user_group_enum),
)


def upgrade() -> None:
    """Seed the user groups."""
    op.bulk_insert(user_groups_table, [{"name": name} for name in USER_GROUP_NAMES])


def downgrade() -> None:
    """Remove the seeded user groups."""
    op.execute(
        user_groups_table.delete().where(user_groups_table.c.name.in_(USER_GROUP_NAMES))
    )
