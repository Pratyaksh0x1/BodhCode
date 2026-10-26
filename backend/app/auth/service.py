
from sqlmodel import Session, select

from app.auth.crypto import encrypt_token
from app.models.user import User, utc_now


def upsert_github_user(
    session: Session,
    *,
    github_id: int,
    login: str,
    name: str | None,
    avatar_url: str,
    email: str | None,
    access_token: str,
    token_scopes: str,
) -> User:
    """Upsert user based on unique github_id.

    Creates a new user record or updates existing record with fresh profile data,
    encrypted token, and updated login timestamp. Guarantees no duplicate records.
    """
    encrypted_token = encrypt_token(access_token)
    statement = select(User).where(User.github_id == github_id)
    user = session.exec(statement).first()

    now = utc_now()
    if user is not None:
        user.login = login
        user.name = name
        user.avatar_url = avatar_url
        user.email = email
        user.encrypted_github_token = encrypted_token
        user.token_scopes = token_scopes
        user.last_login_at = now
    else:
        user = User(
            github_id=github_id,
            login=login,
            name=name,
            avatar_url=avatar_url,
            email=email,
            encrypted_github_token=encrypted_token,
            token_scopes=token_scopes,
            created_at=now,
            last_login_at=now,
        )
        session.add(user)

    session.commit()
    session.refresh(user)
    return user
