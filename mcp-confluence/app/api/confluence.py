from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.oauth_token import ConfluenceOAuthToken
from app.services.confluence_oauth import (
    get_authorization_url,
    exchange_code_for_tokens,
    save_oauth_token,
    get_accessible_resources, 
)
from app.services.confluence_api import list_spaces, list_pages
from app.database import get_db

router = APIRouter()

@router.get("/connect")
def connect(state: str, db: Session = Depends(get_db)):
    authorization_url = get_authorization_url(state)
    return {"authorization_url": authorization_url}

@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    token_data = exchange_code_for_tokens(code)
    user_id = int(state)  # Assuming state contains user_id
    
    # Fetch accessible resources to get cloud_id
    resources = get_accessible_resources(token_data["access_token"])
    if not resources:
        raise HTTPException(status_code=400, detail="No Confluence instances accessible")
    
    # Use first accessible Confluence instance
    cloud_id = resources[0]["id"]
    
    save_oauth_token(db, user_id, token_data, cloud_id)
    return {"message": "OAuth tokens saved successfully.", "cloud_id": cloud_id}

@router.get("/status")
def status(user_id: str, db: Session = Depends(get_db)):
    token = db.query(ConfluenceOAuthToken).filter_by(user_id=user_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="No active session found.")
    return {"status": "connected"}

@router.delete("/disconnect")
def disconnect(user_id: str, db: Session = Depends(get_db)):
    token = db.query(ConfluenceOAuthToken).filter_by(user_id=user_id).first()
    if token:
        db.delete(token)
        db.commit()
    return {"message": "Disconnected successfully."}


@router.get("/spaces")
def get_spaces(user_id: int, db: Session = Depends(get_db)):
    """List all accessible Confluence spaces"""
    try:
        spaces = list_spaces(db, user_id)
        return {"spaces": spaces}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spaces/{space_key}/pages")
def get_pages(space_key: str, user_id: int, db: Session = Depends(get_db)):
    """List pages in a specific space"""
    try:
        pages = list_pages(db, user_id, space_key)
        return {"pages": pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))