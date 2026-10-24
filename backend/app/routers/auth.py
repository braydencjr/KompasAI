import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.services import accounts

router = APIRouter(prefix="/auth", tags=["auth"])

# a person typing a wrong password is fine; a script trying thousands is not: 10 tries per 5 minutes per address
_WINDOW, _LIMIT = 300, 10
_tries: dict[str, deque] = defaultdict(deque)


def _throttle(request: Request, kind: str) -> None:
    key = f"{kind}:{request.client.host if request.client else '?'}"
    now, q = time.monotonic(), _tries[key]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= _LIMIT:
        raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")
    q.append(now)


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=accounts.PASSWORD_MAX)


class SignUp(Credentials):
    name: str = Field("", max_length=40)


class Progress(BaseModel):
    data: dict


def _token(authorization: str | None = Header(None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token if scheme.lower() == "bearer" else ""


def current_user(token: str = Depends(_token)) -> dict:
    user = accounts.user_for(token)
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    return user


def _run(fn, *args):
    try:
        return fn(*args)
    except accounts.AccountError as e:
        raise HTTPException(e.status, str(e))


@router.post("/signup")
def sign_up(body: SignUp, request: Request) -> dict:
    _throttle(request, "signup")
    token, user = _run(accounts.sign_up, body.email, body.password, body.name)
    return {"token": token, "user": user}


@router.post("/login")
def log_in(body: Credentials, request: Request) -> dict:
    _throttle(request, "login")
    token, user = _run(accounts.sign_in, body.email, body.password)
    return {"token": token, "user": user}


@router.post("/logout", status_code=204)
def log_out(token: str = Depends(_token)) -> Response:
    accounts.sign_out(token)
    return Response(status_code=204)


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user}


@router.get("/progress")
def read_progress(user: dict = Depends(current_user)) -> dict:
    return accounts.get_progress(user["id"]) or {"data": None, "updated_at": None}


@router.put("/progress")
def save_progress(body: Progress, user: dict = Depends(current_user)) -> dict:
    return {"updated_at": _run(accounts.put_progress, user["id"], body.data)}
