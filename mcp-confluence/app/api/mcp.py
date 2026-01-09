"""MCP (Model Context Protocol) Server endpoint for LibreChat integration

This implements the MCP SSE transport protocol for LibreChat.
See: https://modelcontextprotocol.io/docs/concepts/transports#server-sent-events-sse
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import json
import asyncio
import uuid

from app.services.llama_cloud import query_index

router = APIRouter()

# Store the pipeline ID (from your synced index)
CONFLUENCE_PIPELINE_ID = "c6517502-2dce-4b8a-b134-834b3aa4ad24"

# Store pending requests and their response queues
pending_requests = {}


def handle_mcp_message(body: dict) -> dict:
    """Process MCP JSON-RPC messages and return response"""
    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id")
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "confluence-knowledge-base",
                    "version": "1.0.0"
                }
            }
        }
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "search_confluence",
                        "description": "Search the Confluence knowledge base for relevant documentation about DevOps, EKS, CI/CD, security, and other technical topics.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to find relevant Confluence pages"
                                },
                                "top_k": {
                                    "type": "integer",
                                    "description": "Number of results to return (default: 5)",
                                    "default": 5
                                }
                            },
                            "required": ["query"]
                        }
                    }
                ]
            }
        }
    
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        if tool_name == "search_confluence":
            query = arguments.get("query", "")
            top_k = arguments.get("top_k", 5)
            
            try:
                results = query_index(CONFLUENCE_PIPELINE_ID, query, top_k)
                
                formatted_results = []
                for i, result in enumerate(results.get("results", []), 1):
                    text = result.get("text", "")
                    metadata = result.get("metadata", {})
                    score = result.get("score", 0)
                    filename = metadata.get("filename", "Unknown")
                    
                    formatted_results.append(
                        f"## Result {i} (Score: {score:.2f})\n"
                        f"**Source:** {filename}\n\n"
                        f"{text}\n"
                    )
                
                content = "\n---\n".join(formatted_results) if formatted_results else "No results found."
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": content}]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "isError": True
                    }
                }
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
        }
    
    elif method == "notifications/initialized":
        # Client notification, no response needed
        return None
    
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    }


@router.get("/sse")
async def mcp_sse_endpoint(request: Request):
    """
    SSE endpoint for MCP protocol.
    Client connects here to receive server messages.
    Returns the endpoint URL for posting messages.
    """
    session_id = str(uuid.uuid4())
    message_queue = asyncio.Queue()
    pending_requests[session_id] = message_queue
    
    async def event_generator():
        try:
            # Send endpoint event with the URL for posting messages
            endpoint_url = f"/mcp/messages?session_id={session_id}"
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            
            # Keep connection alive and send queued messages
            while True:
                if await request.is_disconnected():
                    break
                
                try:
                    # Check for messages with timeout
                    message = await asyncio.wait_for(message_queue.get(), timeout=30.0)
                    yield f"event: message\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            # Cleanup session
            pending_requests.pop(session_id, None)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/messages")
async def mcp_messages(request: Request, session_id: str):
    """
    Endpoint for receiving MCP messages from client.
    Processes the message and queues response for SSE stream.
    """
    if session_id not in pending_requests:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid or expired session"}
        )
    
    body = await request.json()
    response = handle_mcp_message(body)
    
    if response:
        # Queue response for SSE stream
        await pending_requests[session_id].put(response)
    
    return Response(status_code=202)


@router.post("/")
async def mcp_handler(request: Request):
    """
    Direct HTTP endpoint for MCP (non-SSE mode).
    Some clients may use direct HTTP instead of SSE.
    """
    body = await request.json()
    response = handle_mcp_message(body)
    
    if response is None:
        return Response(status_code=204)
    
    return JSONResponse(content=response)
