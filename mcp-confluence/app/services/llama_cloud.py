"""LlamaCloud integration service for managing indexes and uploading files"""

from llama_cloud.client import LlamaCloud as LlamaCloudClient
from llama_cloud.types import CloudDocumentCreate
from typing import List, Optional
import os
from app.config import config


def get_llama_client():
    """Get LlamaCloud client instance"""
    if not config.LLAMA_CLOUD_API_KEY:
        raise Exception("LLAMA_CLOUD_API_KEY not configured")

    return LlamaCloudClient(
        token=config.LLAMA_CLOUD_API_KEY
    )


def create_index(index_name: str) -> str:
    """
    Create a new index (pipeline) in LlamaCloud

    Args:
        index_name: Name for the index

    Returns:
        Pipeline ID from LlamaCloud
    """
    client = get_llama_client()

    pipeline = client.pipelines.create_pipeline(
        request={
            "name": index_name,
            "pipeline_type": "MANAGED",
            "embedding_config": {
                "type": "OPENAI_EMBEDDING",
                "component": {
                    "model_name": "text-embedding-3-small"
                }
            },
            "transform_config": {
                "mode": "auto"
            }
        }
    )

    return pipeline.id


def upload_files_to_index(pipeline_id: str, file_paths: List[str]) -> dict:
    """
    Upload files to an existing index using CloudDocumentCreate

    Args:
        pipeline_id: LlamaCloud pipeline ID
        file_paths: List of local file paths to upload

    Returns:
        Upload result with status and counts
    """
    client = get_llama_client()

    uploaded = 0
    failed = 0
    errors = []

    # Batch documents for upload
    documents = []
    
    for file_path in file_paths:
        try:
            if not os.path.exists(file_path):
                failed += 1
                errors.append(f"File not found: {file_path}")
                continue

            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract filename for metadata
            filename = os.path.basename(file_path)
            doc_id = os.path.splitext(filename)[0]
            
            documents.append(CloudDocumentCreate(
                text=content,
                metadata={
                    "filename": filename,
                    "source": "confluence",
                    "file_path": file_path
                },
                id=doc_id
            ))

        except Exception as e:
            failed += 1
            errors.append(f"{file_path}: {str(e)}")

    # Upload documents in batches
    if documents:
        try:
            batch_size = 50
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                client.pipelines.upsert_batch_pipeline_documents(
                    pipeline_id=pipeline_id,
                    request=batch
                )
                uploaded += len(batch)
        except Exception as e:
            failed += len(documents)
            errors.append(f"Batch upload failed: {str(e)}")

    return {
        "uploaded": uploaded,
        "failed": failed,
        "errors": errors,
        "total": len(file_paths)
    }


def delete_index(pipeline_id: str) -> bool:
    """
    Delete an index from LlamaCloud

    Args:
        pipeline_id: LlamaCloud pipeline ID

    Returns:
        True if successful
    """
    client = get_llama_client()

    try:
        client.pipelines.delete_pipeline(
            project_id=config.LLAMA_CLOUD_PROJECT_ID,
            pipeline_id=pipeline_id
        )
        return True
    except Exception:
        return False


def get_index_status(pipeline_id: str) -> dict:
    """
    Get status information for an index

    Args:
        pipeline_id: LlamaCloud pipeline ID

    Returns:
        Status information dictionary
    """
    client = get_llama_client()

    try:
        pipeline = client.pipelines.get_pipeline(
            project_id=config.LLAMA_CLOUD_PROJECT_ID,
            pipeline_id=pipeline_id
        )

        return {
            "id": pipeline.id,
            "name": pipeline.name,
            "status": "active",
            "document_count": getattr(pipeline, 'document_count', 0)
        }
    except Exception as e:
        return {
            "id": pipeline_id,
            "status": "error",
            "error": str(e)
        }


def query_index(pipeline_id: str, query: str, top_k: int = 3) -> dict:
    """
    Query an index with a search query

    Args:
        pipeline_id: LlamaCloud pipeline ID
        query: Search query string
        top_k: Number of top results to return

    Returns:
        Query results with context and sources
    """
    client = get_llama_client()

    try:
        response = client.pipelines.run_search(
            project_id=config.LLAMA_CLOUD_PROJECT_ID,
            pipeline_id=pipeline_id,
            query=query,
            dense_similarity_top_k=top_k
        )

        results = []
        for node_with_score in response.retrieval_nodes:
            node = node_with_score.node
            results.append({
                "text": node.text if node.text else "",
                "score": node_with_score.score if node_with_score.score else 0.0,
                "metadata": node.extra_info if hasattr(node, 'extra_info') and node.extra_info else {}
            })

        return {
            "query": query,
            "results": results,
            "total_results": len(results)
        }

    except Exception as e:
        raise Exception(f"Failed to query index: {str(e)}")