"""Sync service for syncing Confluence pages to LlamaCloud indexes"""

from sqlalchemy.orm import Session
from typing import List, Dict
import os
import shutil
import re
from datetime import datetime
from markdownify import markdownify as md
from bs4 import BeautifulSoup

from app.models.index import Index
from app.models.sync_config import SyncConfig
from app.models.sync_history import SyncHistory
from app.models.synced_page import SyncedPage
from app.services.confluence_api import list_pages, get_page_content, get_page_attachments, download_attachment
from app.services.llama_cloud import upload_files_to_index
from app.config import config


def sync_index(db: Session, user_id: int, index_id: int) -> Dict:
    """
    Sync Confluence pages to a LlamaCloud index

    Args:
        db: Database session
        user_id: User ID
        index_id: Index ID to sync

    Returns:
        Sync result with statistics
    """
    # Get index and verify ownership
    index = db.query(Index).filter(
        Index.id == index_id,
        Index.user_id == user_id
    ).first()

    if not index:
        raise Exception("Index not found or access denied")

    if not index.llamacloud_index_id:
        raise Exception("Index not linked to LlamaCloud")

    # Get sync config
    sync_config = db.query(SyncConfig).filter(
        SyncConfig.index_id == index_id
    ).first()

    if not sync_config or not sync_config.enabled:
        raise Exception("Sync not configured or disabled")

    # Create sync history record
    sync_history = SyncHistory(
        index_id=index_id,
        started_at=datetime.utcnow(),
        status="running",
        logs="Sync started\n"
    )
    db.add(sync_history)
    db.commit()
    db.refresh(sync_history)

    downloaded_files = []
    temp_dir = None

    try:
        # Create temporary directory for this sync
        temp_dir = os.path.join(
            config.TEMP_FILES_DIR,
            f"sync_{index_id}_{sync_history.id}"
        )
        os.makedirs(temp_dir, exist_ok=True)

        # Get pages from Confluence
        sync_history.logs += "Fetching pages from Confluence...\n"
        db.commit()

        # List pages based on sync config
        spaces = sync_config.confluence_spaces or []

        sync_history.logs += f"Spaces to sync: {spaces}\n"
        db.commit()

        all_pages = []
        if spaces:
            for space_key in spaces:
                sync_history.logs += f"Listing pages from space {space_key}...\n"
                db.commit()

                pages = list_pages(db, user_id, space_key)
                sync_history.logs += f"  Got {len(pages)} pages from space\n"
                db.commit()
                all_pages.extend(pages)
        else:
            sync_history.logs += "No spaces configured, skipping...\n"
            db.commit()

        sync_history.logs += f"Found {len(all_pages)} total pages\n"
        sync_history.files_found = len(all_pages)
        db.commit()

        # Check which pages need syncing (incremental sync)
        sync_history.logs += "Checking for modified pages...\n"
        db.commit()

        pages_to_sync = []
        skipped_count = 0

        for page in all_pages:
            page_id = page.get('id')
            page_title = page.get('title', 'Untitled')
            page_version = page.get('version', {}).get('number', 0) if isinstance(page.get('version'), dict) else 0

            # Check if page was previously synced
            synced_page = db.query(SyncedPage).filter(
                SyncedPage.index_id == index_id,
                SyncedPage.confluence_page_id == page_id
            ).first()

            if synced_page and synced_page.confluence_version >= page_version:
                skipped_count += 1
                continue

            pages_to_sync.append({
                'id': page_id,
                'title': page_title,
                'version': page_version,
                'is_new': synced_page is None
            })

        sync_history.logs += f"Pages to sync: {len(pages_to_sync)}, Skipped (unchanged): {skipped_count}\n"
        db.commit()

        # Download and convert pages that need syncing
        if pages_to_sync:
            sync_history.logs += "Downloading and converting pages...\n"
            db.commit()

            for page_info in pages_to_sync:
                try:
                    page_id = page_info['id']
                    page_title = page_info['title']

                    # Get page content
                    content = get_page_content(db, user_id, page_id)
                    
                    # Extract HTML body
                    html_body = ""
                    if content.get('body'):
                        body_data = content['body']
                        if isinstance(body_data, dict):
                            storage = body_data.get('storage', {})
                            if isinstance(storage, dict):
                                html_body = storage.get('value', '')

                    # Convert HTML to Markdown
                    if html_body:
                        markdown_content = html_to_markdown(html_body)
                    else:
                        markdown_content = ""

                    # Create safe filename
                    safe_title = re.sub(r'[^\w\s-]', '', page_title).strip()
                    safe_title = re.sub(r'[-\s]+', '_', safe_title)[:100]
                    file_path = os.path.join(temp_dir, f"{safe_title}_{page_id}.md")

                    # Write content to file
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(f"# {page_title}\n\n")
                        f.write(f"Source: Confluence Page ID {page_id}\n\n")
                        f.write("---\n\n")
                        f.write(markdown_content)

                    downloaded_files.append(file_path)
                    sync_history.logs += f"Converted: {page_title}\n"

                    # Update synced page record
                    synced_page = db.query(SyncedPage).filter(
                        SyncedPage.index_id == index_id,
                        SyncedPage.confluence_page_id == page_id
                    ).first()

                    if synced_page:
                        synced_page.confluence_version = page_info['version']
                        synced_page.confluence_page_title = page_title
                        synced_page.last_synced_at = datetime.utcnow()
                    else:
                        synced_page = SyncedPage(
                            index_id=index_id,
                            confluence_page_id=page_id,
                            confluence_page_title=page_title,
                            confluence_version=page_info['version'],
                            last_synced_at=datetime.utcnow()
                        )
                        db.add(synced_page)

                    db.commit()

                except Exception as e:
                    sync_history.logs += f"Failed to process {page_info.get('title', 'unknown')}: {str(e)}\n"
                    db.commit()

        # Upload to LlamaCloud
        if downloaded_files:
            sync_history.logs += f"Uploading {len(downloaded_files)} files to LlamaCloud...\n"
            db.commit()

            upload_result = upload_files_to_index(
                index.llamacloud_index_id,
                downloaded_files
            )

            sync_history.files_synced = upload_result['uploaded']
            sync_history.logs += f"Uploaded: {upload_result['uploaded']}, Failed: {upload_result['failed']}\n"

            if upload_result['errors']:
                for error in upload_result['errors'][:10]:
                    sync_history.logs += f"Error: {error}\n"

        # Mark as completed
        sync_history.status = "completed"
        sync_history.completed_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "files_found": len(all_pages),
            "files_downloaded": len(downloaded_files),
            "files_uploaded": sync_history.files_synced,
            "sync_history_id": sync_history.id
        }

    except Exception as e:
        # Mark as failed
        sync_history.status = "failed"
        sync_history.error_message = str(e)
        sync_history.completed_at = datetime.utcnow()
        db.commit()

        raise

    finally:
        # Cleanup temporary files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass


def html_to_markdown(html_content: str) -> str:
    """
    Convert Confluence HTML to clean Markdown

    Args:
        html_content: HTML string from Confluence

    Returns:
        Clean markdown string
    """
    if not html_content:
        return ""

    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    # Convert to markdown using markdownify
    markdown = md(str(soup), heading_style="ATX", bullets="-")

    # Clean up extra whitespace
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    markdown = markdown.strip()

    return markdown


def get_sync_history(db: Session, user_id: int, index_id: int, limit: int = 10) -> List[SyncHistory]:
    """
    Get sync history for an index

    Args:
        db: Database session
        user_id: User ID
        index_id: Index ID
        limit: Maximum number of records to return

    Returns:
        List of sync history records
    """
    # Verify index ownership
    index = db.query(Index).filter(
        Index.id == index_id,
        Index.user_id == user_id
    ).first()

    if not index:
        raise Exception("Index not found or access denied")

    # Get sync history
    history = db.query(SyncHistory).filter(
        SyncHistory.index_id == index_id
    ).order_by(
        SyncHistory.started_at.desc()
    ).limit(limit).all()

    return history