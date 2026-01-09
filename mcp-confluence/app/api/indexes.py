from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.models.index import Index
from app.models.sync_config import SyncConfig
from app.models.sync_history import SyncHistory
from app.database import get_db
from app.services.llama_cloud import create_index as create_llamacloud_index, delete_index as delete_llamacloud_index
from app.services.sync_service import sync_index, get_sync_history

router = APIRouter()


# Pydantic schemas for request/response
class IndexCreate(BaseModel):
    name: str
    confluence_spaces: List[str] = []
    confluence_labels: List[str] = []
    include_attachments: bool = True
    include_comments: bool = False
    interval_minutes: int = 60


class IndexUpdate(BaseModel):
    name: Optional[str] = None
    confluence_spaces: Optional[List[str]] = None
    confluence_labels: Optional[List[str]] = None
    include_attachments: Optional[bool] = None
    include_comments: Optional[bool] = None
    interval_minutes: Optional[int] = None
    enabled: Optional[bool] = None


class SyncConfigResponse(BaseModel):
    interval_minutes: int
    confluence_spaces: List[str]
    confluence_labels: List[str]
    include_attachments: bool
    include_comments: bool
    enabled: bool

    class Config:
        from_attributes = True


class IndexResponse(BaseModel):
    id: int
    name: str
    llamacloud_index_id: Optional[str]
    sync_config: Optional[SyncConfigResponse]

    class Config:
        from_attributes = True


class SyncHistoryResponse(BaseModel):
    id: int
    started_at: str
    completed_at: Optional[str]
    status: str
    files_found: int
    files_synced: int
    error_message: Optional[str]

    class Config:
        from_attributes = True


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_index_endpoint(
    index_data: IndexCreate,
    user_id: int,  # TODO: Get from JWT auth
    db: Session = Depends(get_db)
):
    """Create a new index with LlamaCloud pipeline"""
    try:
        # Create LlamaCloud pipeline
        llamacloud_id = create_llamacloud_index(index_data.name)

        # Create index in database
        db_index = Index(
            user_id=user_id,
            name=index_data.name,
            llamacloud_index_id=llamacloud_id
        )
        db.add(db_index)
        db.commit()
        db.refresh(db_index)

        # Create sync config
        sync_config = SyncConfig(
            index_id=db_index.id,
            confluence_spaces=index_data.confluence_spaces,
            confluence_labels=index_data.confluence_labels,
            include_attachments=index_data.include_attachments,
            include_comments=index_data.include_comments,
            interval_minutes=index_data.interval_minutes,
            enabled=True
        )
        db.add(sync_config)
        db.commit()

        return {
            "id": db_index.id,
            "name": db_index.name,
            "llamacloud_index_id": db_index.llamacloud_index_id,
            "sync_config": {
                "interval_minutes": sync_config.interval_minutes,
                "confluence_spaces": sync_config.confluence_spaces or [],
                "confluence_labels": sync_config.confluence_labels or [],
                "include_attachments": sync_config.include_attachments,
                "include_comments": sync_config.include_comments,
                "enabled": sync_config.enabled
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create index: {str(e)}"
        )


@router.get("/")
def list_indexes(
    user_id: int,  # TODO: Get from JWT auth
    db: Session = Depends(get_db)
):
    """List all indexes for a user"""
    indexes = db.query(Index).filter(Index.user_id == user_id).all()

    result = []
    for idx in indexes:
        sync_config = db.query(SyncConfig).filter(SyncConfig.index_id == idx.id).first()
        result.append({
            "id": idx.id,
            "name": idx.name,
            "llamacloud_index_id": idx.llamacloud_index_id,
            "created_at": idx.created_at.isoformat() if idx.created_at else None,
            "sync_config": {
                "interval_minutes": sync_config.interval_minutes if sync_config else 60,
                "confluence_spaces": sync_config.confluence_spaces or [] if sync_config else [],
                "confluence_labels": sync_config.confluence_labels or [] if sync_config else [],
                "include_attachments": sync_config.include_attachments if sync_config else True,
                "include_comments": sync_config.include_comments if sync_config else False,
                "enabled": sync_config.enabled if sync_config else False
            } if sync_config else None
        })

    return {"indexes": result, "total": len(result)}


@router.get("/{index_id}")
def get_index(
    index_id: int,
    user_id: int,  # TODO: Get from JWT auth
    db: Session = Depends(get_db)
):
    """Get a specific index"""
    db_index = db.query(Index).filter(
        Index.id == index_id,
        Index.user_id == user_id
    ).first()

    if not db_index:
        raise HTTPException(status_code=404, detail="Index not found")

    sync_config = db.query(SyncConfig).filter(SyncConfig.index_id == index_id).first()

    return {
        "id": db_index.id,
        "name": db_index.name,
        "llamacloud_index_id": db_index.llamacloud_index_id,
        "created_at": db_index.created_at.isoformat() if db_index.created_at else None,
        "sync_config": {
            "interval_minutes": sync_config.interval_minutes if sync_config else 60,
            "confluence_spaces": sync_config.confluence_spaces or [] if sync_config else [],
            "confluence_labels": sync_config.confluence_labels or [] if sync_config else [],
            "include_attachments": sync_config.include_attachments if sync_config else True,
            "include_comments": sync_config.include_comments if sync_config else False,
            "enabled": sync_config.enabled if sync_config else False
        } if sync_config else None
    }


@router.patch("/{index_id}")
def update_index_endpoint(
    index_id: int,
    index_data: IndexUpdate,
    user_id: int,  # TODO: Get from JWT auth
    db: Session = Depends(get_db)
):
    """Update an index"""
    db_index = db.query(Index).filter(
        Index.id == index_id,
        Index.user_id == user_id
    ).first()

    if not db_index:
        raise HTTPException(status_code=404, detail="Index not found")

    # Update index name if provided
    if index_data.name is not None:
        db_index.name = index_data.name

    # Update sync config
    sync_config = db.query(SyncConfig).filter(SyncConfig.index_id == index_id).first()
    if sync_config:
        if index_data.confluence_spaces is not None:
            sync_config.confluence_spaces = index_data.confluence_spaces
        if index_data.confluence_labels is not None:
            sync_config.confluence_labels = index_data.confluence_labels
        if index_data.include_attachments is not None:
            sync_config.include_attachments = index_data.include_attachments
        if index_data.include_comments is not None:
            sync_config.include_comments = index_data.include_comments
        if index_data.interval_minutes is not None:
            sync_config.interval_minutes = index_data.interval_minutes
        if index_data.enabled is not None:
            sync_config.enabled = index_data.enabled

    db.commit()
    db.refresh(db_index)

    return {
        "id": db_index.id,
        "name": db_index.name,
        "llamacloud_index_id": db_index.llamacloud_index_id,
        "sync_config": {
            "interval_minutes": sync_config.interval_minutes if sync_config else 60,
            "confluence_spaces": sync_config.confluence_spaces or [] if sync_config else [],
            "confluence_labels": sync_config.confluence_labels or [] if sync_config else [],
            "include_attachments": sync_config.include_attachments if sync_config else True,
            "include_comments": sync_config.include_comments if sync_config else False,
            "enabled": sync_config.enabled if sync_config else False
        } if sync_config else None
    }


@router.delete("/{index_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_index_endpoint(
    index_id: int,
    user_id: int,  # TODO: Get from JWT auth
    db: Session = Depends(get_db)
):
    """Delete an index"""
    db_index = db.query(Index).filter(
        Index.id == index_id,
        Index.user_id == user_id
    ).first()

    if not db_index:
        raise HTTPException(status_code=404, detail="Index not found")

    # Delete from LlamaCloud
    if db_index.llamacloud_index_id:
        delete_llamacloud_index(db_index.llamacloud_index_id)

    # Delete from database (cascades to sync_config, sync_history, synced_pages)
    db.delete(db_index)
    db.commit()

    return None


@router.post("/{index_id}/sync")
def trigger_sync_endpoint(
    index_id: int,
    user_id: int,  # TODO: Get from JWT auth
    db: Session = Depends(get_db)
):
    """Trigger a manual sync for an index"""
    try:
        result = sync_index(db, user_id, index_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{index_id}/sync-history")
def get_sync_history_endpoint(
    index_id: int,
    user_id: int,  # TODO: Get from JWT auth
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get sync history for an index"""
    try:
        history = get_sync_history(db, user_id, index_id, limit)

        return {
            "history": [
                {
                    "id": h.id,
                    "started_at": h.started_at.isoformat() if h.started_at else None,
                    "completed_at": h.completed_at.isoformat() if h.completed_at else None,
                    "status": h.status,
                    "files_found": h.files_found or 0,
                    "files_synced": h.files_synced or 0,
                    "error_message": h.error_message,
                    "logs": h.logs
                }
                for h in history
            ],
            "total": len(history)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/{index_id}/query")
def query_index_endpoint(
    index_id: int,
    request: QueryRequest,
    user_id: int,
    db: Session = Depends(get_db)
):
    """Query the index for relevant documents"""
    from app.services.llama_cloud import query_index
    
    # Get index
    index = db.query(Index).filter(
        Index.id == index_id,
        Index.user_id == user_id
    ).first()
    
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")
    
    if not index.llamacloud_index_id:
        raise HTTPException(status_code=400, detail="Index not synced to LlamaCloud yet")
    
    try:
        results = query_index(index.llamacloud_index_id, request.query, request.top_k)
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )