from authlib.integrations.starlette_client import OAuth

from app.config import get_settings

oauth = OAuth()


def get_oauth() -> OAuth:
    """Return configured OAuth registry with GitHub client.

    Uses client credentials from app Settings.
    """
    if "github" not in oauth._clients:
        settings = get_settings()
        oauth.register(
            name="github",
            client_id=settings.GITHUB_CLIENT_ID,
            client_secret=settings.GITHUB_CLIENT_SECRET,
            authorize_url="https://github.com/login/oauth/authorize",
            access_token_url="https://github.com/login/oauth/access_token",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )
    return oauth
