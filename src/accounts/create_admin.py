import argparse
import asyncio
import sys
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts.crud import get_user_by_email, get_user_group_by_name, create_user
from src.accounts.models import User, UserGroupEnum
from src.accounts.schemas import UserRegistrationRequestSchema
from src.database.session import TaskSession


async def create_admin(db: AsyncSession, data: UserRegistrationRequestSchema) -> User:
    existing_user = await get_user_by_email(db=db, email=data.email)
    if existing_user is not None:
        raise ValueError("A user with this email already exists.")
    user_group = await get_user_group_by_name(db=db, name=UserGroupEnum.ADMIN)
    if user_group is None:
        raise ValueError("Admin group not found. Have the migrations been applied?")

    admin_user = await create_user(db=db, data=data, user_group=user_group)
    admin_user.is_active = True
    await db.commit()

    return admin_user


async def _run(data: UserRegistrationRequestSchema) -> User:
    async with TaskSession() as session:
        return await create_admin(db=session, data=data)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create an active admin account.")
    parser.add_argument("email")
    args = parser.parse_args(argv)

    password = getpass("Password: ")
    password_confirmation = getpass("Password (again): ")

    if password != password_confirmation:
        sys.exit("Passwords do not match.")

    try:
        data = UserRegistrationRequestSchema(email=args.email, password=password)
    except ValidationError as exc:
        sys.exit(exc.errors()[0]["msg"])

    try:
        asyncio.run(_run(data))
    except ValueError as exc:
        sys.exit(str(exc))

    print(f"Created admin account {data.email}.")


if __name__ == "__main__":
    main()
