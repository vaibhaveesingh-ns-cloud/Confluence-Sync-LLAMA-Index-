from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import httpx
import base64
from app.models.oauth_token import ConfluenceOAuthToken
from app.config import config

# Confluence Cloud API base URL template
CONFLUENCE_API_BASE = "https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/api/v2"


def get_confluence_client(db: Session, user_id: int) -> Tuple[httpx.Client, str]:
    """
    Get an httpx client configured for Confluence API.
    Supports both OAuth and API token authentication.
    Returns (client, cloud_id) tuple.
    """
    # First, try API token auth from environment (simpler, no OAuth needed)
    if config.CONFLUENCE_API_TOKEN and config.CONFLUENCE_BASE_URL and config.CONFLUENCE_EMAIL:
        # Use basic auth with email:api_token
        credentials = f"{config.CONFLUENCE_EMAIL}:{config.CONFLUENCE_API_TOKEN}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        client = httpx.Client(
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
        return client, config.CONFLUENCE_BASE_URL
    
    # Fall back to OAuth token from database
    token = db.query(ConfluenceOAuthToken).filter(ConfluenceOAuthToken.user_id == user_id).first()
    if not token:
        raise Exception("No OAuth token found for user and no API token configured. Please connect Confluence first.")
    if not token.cloud_id:
        raise Exception("No Confluence Cloud ID found. Please reconnect Confluence first.")

    client = httpx.Client(
        headers={
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        timeout=30.0
    )

    return client, token.cloud_id
def _get_base_url(cloud_info: str) -> str:
    """
    Get the API base URL.
    If cloud_info is a URL (direct site access), return the wiki API path for that site.
    If cloud_info is a UUID (cloud_id), return the OAuth gateway URL.
    """
    if cloud_info.startswith("http"):
        # Direct site access via API token
        base = cloud_info.rstrip("/")
        if not base.endswith("/wiki"):
            base = f"{base}/wiki"
        return f"{base}/api/v2"
    
    # OAuth gateway access
    return CONFLUENCE_API_BASE.format(cloud_id=cloud_info)


def find_page_by_title(db: Session, user_id: int, title: str, space_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Find pages by title, optionally filtered by space_key"""
    client, cloud_id = get_confluence_client(db, user_id)
    base_url = _get_base_url(cloud_id)
    
    try:
        params = {"title": title}
        
        # If space_key is provided, we need to get space ID first (v2 API requirement)
        if space_key:
            space_response = client.get(f"{base_url}/spaces", params={"keys": space_key})
            space_response.raise_for_status()
            spaces = space_response.json().get("results", [])
            if spaces:
                params["space-id"] = spaces[0]["id"]
        
        response = client.get(f"{base_url}/pages", params=params)
        response.raise_for_status()
        return response.json().get("results", [])
    finally:
        client.close()
def list_spaces(db: Session, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    """List all accessible Confluence spaces"""
    client, cloud_id = get_confluence_client(db, user_id)
    base_url = _get_base_url(cloud_id)
    
    try:
        response = client.get(f"{base_url}/spaces", params={"limit": limit})
        response.raise_for_status()
        return response.json().get("results", [])
    finally:
        client.close()
def list_pages(db: Session, user_id: int, space_key: str, limit: int = 100) -> List[Dict[str, Any]]:
    """List pages in a specific space"""
    client, cloud_id = get_confluence_client(db, user_id)
    base_url = _get_base_url(cloud_id)
    
    try:
        # First get space ID from space key
        space_response = client.get(f"{base_url}/spaces", params={"keys": space_key})
        space_response.raise_for_status()
        spaces = space_response.json().get("results", [])
        
        if not spaces:
            return []
        
        space_id = spaces[0]["id"]
        
        # Get pages in the space
        response = client.get(
            f"{base_url}/spaces/{space_id}/pages",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json().get("results", [])
    finally:
        client.close()
def get_page_content(db: Session, user_id: int, page_id: str) -> Dict[str, Any]:
    """Get page content with body in storage format"""
    client, cloud_id = get_confluence_client(db, user_id)
    base_url = _get_base_url(cloud_id)
    
    try:
        response = client.get(
            f"{base_url}/pages/{page_id}",
            params={"body-format": "storage"}  # Get HTML storage format
        )
        response.raise_for_status()
        return response.json()
    finally:
        client.close()
def get_page_attachments(db: Session, user_id: int, page_id: str) -> List[Dict[str, Any]]:
    """Get attachments for a page"""
    client, cloud_id = get_confluence_client(db, user_id)
    base_url = _get_base_url(cloud_id)
    
    try:
        response = client.get(f"{base_url}/pages/{page_id}/attachments")
        response.raise_for_status()
        return response.json().get("results", [])
    finally:
        client.close()
def download_attachment(db: Session, user_id: int, attachment_id: str, dest_path: str) -> str:
    """Download an attachment to local file"""
    client, cloud_id = get_confluence_client(db, user_id)
    base_url = _get_base_url(cloud_id)
    
    try:
        # Get attachment metadata first
        meta_response = client.get(f"{base_url}/attachments/{attachment_id}")
        meta_response.raise_for_status()
        attachment = meta_response.json()
        
        # Download the file
        download_url = attachment.get("downloadLink")
        if not download_url:
            raise Exception("No download link found for attachment")
        
        # Download link might be relative, construct full URL
        if download_url.startswith("/"):
            download_url = f"https://api.atlassian.com{download_url}"
        
        file_response = client.get(download_url)
        file_response.raise_for_status()
        
        with open(dest_path, 'wb') as f:
            f.write(file_response.content)
        
        return dest_path
    finally:
        client.close()
def export_page_as_pdf(db: Session, user_id: int, page_id: str, dest_path: str) -> str:
    """
    Export page as PDF.
    Note: Confluence Cloud API v2 doesn't have direct PDF export.
    Use the legacy REST API endpoint instead.
    """
    client, cloud_id = get_confluence_client(db, user_id)
    
    try:
        # Use legacy API for PDF export
        legacy_url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/rest/api/content/{page_id}/export/pdf"
        
        response = client.get(legacy_url)
        response.raise_for_status()
        
        with open(dest_path, 'wb') as f:
            f.write(response.content)
        
        return dest_path
    finally:
        client.close()

