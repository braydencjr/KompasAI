"""Checks a "Sign in with Google" token (the signed ID token Google's button hands the browser).

Google signs the token; google-auth verifies the signature against Google's public keys, the expiry, and that the token
was issued for THIS app (GOOGLE_CLIENT_ID), so a token meant for another site is refused. No Google secret is kept
here: the client ID is public. Without GOOGLE_CLIENT_ID, Google sign-in is off.
"""

import os

import requests
from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleAuthError(Exception):
    """The token isn't usable (the message is safe to show)."""


def client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


def enabled() -> bool:
    return bool(client_id())


def verify(credential: str) -> dict:
    """{"sub", "email", "name"} of a verified Google account. Raises GoogleAuthError."""
    if not enabled():
        raise GoogleAuthError("Google sign-in isn't set up on this server.")
    try:
        claims = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id())
    except ValueError as e:      # bad signature, wrong audience, expired, malformed
        raise GoogleAuthError("Google couldn't confirm this sign-in. Try again.") from e
    except TransportError as e:  # Google's keys couldn't be fetched
        raise GoogleAuthError("Couldn't reach Google to check this sign-in. Try again.") from e
    if claims.get("iss") not in ISSUERS or not claims.get("sub"):
        raise GoogleAuthError("Google couldn't confirm this sign-in. Try again.")
    if not claims.get("email") or not claims.get("email_verified"):
        raise GoogleAuthError("This Google account's email isn't verified.")
    return {"sub": claims["sub"], "email": claims["email"], "name": claims.get("name") or ""}


TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"
_BAD = "Google couldn't confirm this sign-in. Try again."


def verify_access_token(access_token: str) -> dict:
    """The same answer as verify(), for the popup sign-in (which hands the browser an access token, not an ID token).

    Two checks with Google: the token was issued to THIS app (a token another site got for the same person is refused),
    then the profile it unlocks. {"sub", "email", "name"}; raises GoogleAuthError."""
    if not enabled():
        raise GoogleAuthError("Google sign-in isn't set up on this server.")
    try:
        meta = requests.get(TOKENINFO, params={"access_token": access_token}, timeout=8)
        if meta.status_code != 200 or meta.json().get("aud") != client_id():
            raise GoogleAuthError(_BAD)
        profile = requests.get(USERINFO, headers={"Authorization": f"Bearer {access_token}"}, timeout=8)
        if profile.status_code != 200:
            raise GoogleAuthError(_BAD)
        claims = profile.json()
    except requests.RequestException as e:
        raise GoogleAuthError("Couldn't reach Google to check this sign-in. Try again.") from e
    except ValueError as e:      # an answer that isn't JSON
        raise GoogleAuthError(_BAD) from e
    if not claims.get("sub") or not claims.get("email"):
        raise GoogleAuthError(_BAD)
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleAuthError("This Google account's email isn't verified.")
    return {"sub": claims["sub"], "email": claims["email"], "name": claims.get("name") or ""}
