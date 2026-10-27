"""Enable RLS on application tables without client policies.

Revision ID: 0ca4f924ef31
Revises: 7112857481bf
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0ca4f924ef31"
down_revision: Union[str, None] = "7112857481bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPLICATION_TABLES = (
    "user_profiles",
    "conversations",
    "daily_plans",
    "scan_sessions",
    "shopping_searches",
    "user_style_preferences",
    "voice_command_receipts",
    "conversation_messages",
    "daily_plan_events",
    "garment_detections",
    "outfit_recommendations",
    "preparation_tasks",
    "wardrobe_items",
    "app_notifications",
    "outfit_history",
    "outfit_recommendation_items",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in APPLICATION_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in APPLICATION_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY'))
