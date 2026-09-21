from __future__ import annotations

import argparse
import sys

from app.application.auth.bootstrap_tenant import BootstrapConflictError, BootstrapTenant
from app.application.auth.models import BootstrapCommand
from app.bootstrap.persistence import LazySessionFactory
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.config.settings import load_settings
from app.infrastructure.persistence.session import session_scope
from app.infrastructure.persistence.tenant_repository import SqlAlchemyTenantRepository
from app.infrastructure.persistence.user_repository import SqlAlchemyUserRepository


def _require_bootstrap_settings() -> tuple[str, str, str]:
    settings = load_settings()
    tenant_name = settings.bootstrap_tenant_name.strip()
    admin_email = settings.bootstrap_admin_email.strip()
    admin_password = settings.bootstrap_admin_password.strip()
    if not tenant_name or not admin_email or not admin_password:
        print(
            "BOOTSTRAP_TENANT_NAME, BOOTSTRAP_ADMIN_EMAIL, and BOOTSTRAP_ADMIN_PASSWORD are required",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return tenant_name, admin_email, admin_password


def cmd_bootstrap() -> int:
    tenant_name, admin_email, admin_password = _require_bootstrap_settings()
    settings = load_settings()
    sessions = LazySessionFactory(settings.database_url)
    try:
        with session_scope(sessions) as session:
            use_case = BootstrapTenant(
                SqlAlchemyTenantRepository(session),
                SqlAlchemyUserRepository(session),
                Argon2PasswordHasher(),
            )
            result = use_case.execute(
                BootstrapCommand(
                    tenant_name=tenant_name,
                    admin_email=admin_email,
                    admin_password=admin_password,
                )
            )
    except BootstrapConflictError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if result.created:
        print(f"bootstrap created tenant={result.tenant_id} user={result.user_id}")
    else:
        print("bootstrap skipped: admin email already exists")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="Create the first tenant and admin user")
    args = parser.parse_args(argv)
    if args.command == "bootstrap":
        return cmd_bootstrap()
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
