from sqlalchemy.orm import Session
from fastapi import HTTPException
import httpx
import os
import json
from app.models.oauth_token import ConfluenceOAuthToken

CONFLUENCE_AUTH_URL = "https://auth.atlassian.com/authorize"
CONFLUENCE_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
CONFLUENCE_REDIRECT_URI = os.getenv("CONFLUENCE_REDIRECT_URI")
CONFLUENCE_CLIENT_ID = os.getenv("CONFLUENCE_CLIENT_ID")
CONFLUENCE_CLIENT_SECRET = os.getenv("CONFLUENCE_CLIENT_SECRET")

def get_authorization_url(state: str) -> str:
    return f"{CONFLUENCE_AUTH_URL}?client_id={CONFLUENCE_CLIENT_ID}&redirect_uri={CONFLUENCE_REDIRECT_URI}&response_type=code&state={state}&scope=read:confluence-content.all read:confluence-space.summary offline_access"

def exchange_code_for_tokens(code: str) -> dict:
    response = httpx.post(CONFLUENCE_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": CONFLUENCE_CLIENT_ID,
        "client_secret": CONFLUENCE_CLIENT_SECRET,
        "redirect_uri": CONFLUENCE_REDIRECT_URI,
        "code": code
    })
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to exchange code for tokens")
    return response.json()

def refresh_access_token(refresh_token: str) -> dict:
    response = httpx.post(CONFLUENCE_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": CONFLUENCE_CLIENT_ID,
        "client_secret": CONFLUENCE_CLIENT_SECRET,
        "refresh_token": refresh_token
    })
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to refresh access token")
    return response.json()

def get_accessible_resources(access_token: str) -> list:
    """
    Get list of Confluence Cloud instances the user has access to.
    Returns list of {id, url, name} for each accessible resource.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    response = httpx.get(
        "https://api.atlassian.com/oauth/token/accessible-resources",
        headers=headers
    )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch accessible resources")
    return response.json()
def save_oauth_token(db: Session, user_id: int, token_data: dict, cloud_id: str):
    """Save OAuth token with cloud_id"""
    # Check if token already exists
    existing = db.query(ConfluenceOAuthToken).filter(
        ConfluenceOAuthToken.user_id == user_id
    ).first()
    
    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data.get("refresh_token", existing.refresh_token)
        existing.cloud_id = cloud_id
        existing.expires_at = token_data.get("expires_at")
        existing.scopes = token_data.get("scope", "")
    else:
        token = ConfluenceOAuthToken(
            user_id=user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", ""),
            cloud_id=cloud_id,
            expires_at=token_data.get("expires_at"),
            scopes=token_data.get("scope", "")
        )
        db.add(token)
    
    db.commit()

def get_credentials(db: Session, user_id: int) -> dict:
    token = db.query(ConfluenceOAuthToken).filter(ConfluenceOAuthToken.user_id == user_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="OAuth token not found")
    return {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "expires_at": token.expires_at
    }