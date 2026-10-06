"""`/api/v1/auth` and `/api/v1/security` -- the login gate's two surfaces.

`/auth/*` is what a visitor uses: is the gate on, log in, log out. Those three
are the only API routes answerable without credentials (`proxy.api.gate`).
`/security` is what Settings -> Security uses to configure the gate, and sits
behind it like everything else.

Plain `def` handlers like the rest of `/api/v1`: a login runs scrypt, which
belongs in the threadpool.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from proxy.api import gate
from proxy.api.schemas import LoginIn, SecurityIn, SecurityOut, SessionOut
from proxy.state import security

router = APIRouter()


def _set_session(response: Response) -> None:
    response.set_cookie(
        gate.COOKIE,
        security.store().issue_session(),
        max_age=security.SESSION_SECONDS,
        httponly=True,
        # Lax keeps the cookie off cross-site fetches, which matters because the
        # server's CORS policy is wide open for the userscripts' sake. Not
        # `secure`: the archive is served over plain http on a LAN.
        samesite="lax",
        path="/",
    )


def _security_out() -> SecurityOut:
    config = security.store().config()
    return SecurityOut(
        enabled=config.enabled,
        username=config.username,
        has_password=bool(config.password_hash),
    )


@router.get("/auth/session", response_model=SessionOut, summary="Is login required, and is this client logged in")
def session(request: Request) -> SessionOut:
    return SessionOut(
        enabled=security.store().config().locked,
        authenticated=gate.is_authenticated(request),
    )


@router.post("/auth/login", response_model=SessionOut, summary="Log in")
def login(body: LoginIn, response: Response) -> SessionOut:
    if not security.store().check_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _set_session(response)
    return SessionOut(enabled=True, authenticated=True)


@router.post("/auth/logout", status_code=204, summary="Log out")
def logout(response: Response) -> None:
    response.delete_cookie(gate.COOKIE, path="/")


@router.get("/security", response_model=SecurityOut, summary="The login gate's settings")
def get_security() -> SecurityOut:
    return _security_out()


@router.put("/security", response_model=SecurityOut, summary="Change the login gate's settings")
def put_security(body: SecurityIn, response: Response) -> SecurityOut:
    """Store the gate's settings. Omit `password` (or send it empty) to keep the
    current one; the password itself is never stored or returned."""
    try:
        config = security.store().update(
            enabled=body.enabled, username=body.username, password=body.password or None
        )
    except security.SecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"could not save: {exc}") from exc
    # Saving replaces the session secret, which would log out the very browser
    # that just turned the gate on -- so it is handed a session under the new one.
    if config.enabled:
        _set_session(response)
    else:
        response.delete_cookie(gate.COOKIE, path="/")
    return _security_out()
