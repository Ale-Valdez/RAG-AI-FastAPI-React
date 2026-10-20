"""Enforce tenant isolation with row-level security.

Revision ID: 0004_tenant_rls
Revises: 0003_conversations
Create Date: 2026-10-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_tenant_rls"
down_revision: Union[str, Sequence[str], None] = "0003_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_TABLES = ("users", "documents", "conversations", "messages")
_PREDICATE = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    role_exists = bind.execute(
        sa.text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_rls'")
    ).scalar()
    # CREATE ROLE and ALTER ROLE cannot run inside the migration transaction.
    with op.get_context().autocommit_block():
        if role_exists:
            op.execute("ALTER ROLE app_rls WITH NOLOGIN NOSUPERUSER NOBYPASSRLS")
        else:
            op.execute("CREATE ROLE app_rls WITH NOLOGIN NOSUPERUSER NOBYPASSRLS")

    op.execute("GRANT app_rls TO app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON users, documents, conversations, messages TO app_rls"
    )
    op.execute("GRANT SELECT, INSERT ON tenants TO app_rls")

    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_select_tenant ON {table} "
            f"FOR SELECT USING ({_PREDICATE})"
        )
        op.execute(
            f"CREATE POLICY {table}_insert_tenant ON {table} "
            f"FOR INSERT WITH CHECK ({_PREDICATE})"
        )
        op.execute(
            f"CREATE POLICY {table}_update_tenant ON {table} "
            f"FOR UPDATE USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(
            f"CREATE POLICY {table}_delete_tenant ON {table} "
            f"FOR DELETE USING ({_PREDICATE})"
        )

    op.execute(
        """
        CREATE FUNCTION app_user_by_email(email text)
        RETURNS TABLE (
            id varchar(36),
            tenant_id varchar(36),
            email varchar(320),
            password_hash varchar(255)
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT users.id, users.tenant_id, users.email, users.password_hash
            FROM public.users
            WHERE users.email = $1
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_users_any_exist()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (SELECT 1 FROM public.users)
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_user_by_email(text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_users_any_exist() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_by_email(text) TO app_rls")
    op.execute("GRANT EXECUTE ON FUNCTION app_users_any_exist() TO app_rls")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_tenant ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_insert_tenant ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_update_tenant ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_delete_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("REVOKE ALL ON FUNCTION app_user_by_email(text) FROM app_rls")
    op.execute("REVOKE ALL ON FUNCTION app_users_any_exist() FROM app_rls")
    op.execute("DROP FUNCTION IF EXISTS app_user_by_email(text)")
    op.execute("DROP FUNCTION IF EXISTS app_users_any_exist()")
    op.execute(
        "REVOKE ALL ON TABLE users, documents, conversations, messages, tenants FROM app_rls"
    )
    op.execute("REVOKE app_rls FROM app")
