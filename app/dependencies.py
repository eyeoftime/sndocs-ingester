from fastapi import Cookie, Header, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

SESSION_COOKIE = "sndocs_session"
_serializer = URLSafeTimedSerializer(settings.secret_key)


def create_session() -> str:
    return _serializer.dumps({"auth": True})


def require_auth(
    sndocs_session: str = Cookie(default=None),
    authorization: str = Header(default=None),
):
    # Allow internal API key auth via Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        if token == settings.secret_key:
            return
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not sndocs_session:
        raise _redirect()
    try:
        _serializer.loads(sndocs_session, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        raise _redirect()


def _redirect():
    return HTTPException(status_code=302, headers={"Location": "/login"})
