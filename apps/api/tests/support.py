from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


def create_org_user(
    client: TestClient,
    *,
    organization: str = "Test office",
    email: str = "staff@example.com",
    password: str = PASSWORD,
    display_name: str = "Staff",
) -> None:
    async def create() -> None:
        from sqlalchemy import select

        from app.db.session import session_scope
        from app.models.organization import Organization
        from app.models.user import User
        from app.services.auth_service import hash_password

        async with session_scope() as session:
            org = await session.scalar(select(Organization).where(Organization.name == organization))
            if org is None:
                org = Organization(name=organization)
                session.add(org)
                await session.flush()
            normalized = email.strip().lower()
            existing = await session.scalar(select(User).where(User.email == normalized))
            if existing is None:
                session.add(
                    User(
                        organization_id=org.id,
                        email=normalized,
                        password_hash=hash_password(password),
                        display_name=display_name,
                    )
                )
            await session.commit()

    client.portal.call(create)


def authenticate(
    client: TestClient,
    *,
    organization: str = "Test office",
    email: str = "staff@example.com",
    password: str = PASSWORD,
    display_name: str = "Staff",
    set_header: bool = True,
) -> dict:
    create_org_user(
        client,
        organization=organization,
        email=email,
        password=password,
        display_name=display_name,
    )
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    if set_header:
        client.headers["Authorization"] = f"Bearer {body['token']}"
    return body
