import json
import os
import urllib.request
from fastapi import Header, HTTPException


def identity(authorization: str | None = Header(default=None)):
    if os.getenv("APP_MODE", "production") == "local":
        return {"uid": "local-developer", "role": "admin", "local": True}
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign-in required")
    try:
        # Supabase Auth validates the access token and rejects signed-out sessions.
        url = os.getenv("SUPABASE_URL") or os.environ["VITE_SUPABASE_URL"]
        key = os.getenv("SUPABASE_ANON_KEY") or os.environ["VITE_SUPABASE_ANON_KEY"]
        request = urllib.request.Request(
            url.rstrip("/") + "/auth/v1/user",
            headers={"Authorization": authorization, "apikey": key},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            user = json.load(response)
        return {"uid": user["id"], "email": user.get("email")}
    except Exception:
        raise HTTPException(401, "Invalid or expired token")


def authorize(user, store, roles=("viewer", "operator", "admin")):
    if user.get("local"):
        return user
    profile = store.get("users", user["uid"])
    if not profile or not profile.get("active") or profile.get("role") not in roles:
        raise HTTPException(403, "Insufficient permissions")
    return {**user, **profile}
