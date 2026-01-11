"""MCP (Model Context Protocol) Server endpoint for LibreChat integration

This implements the MCP Streamable HTTP transport protocol.
See: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
"""

from fastapi import APIRouter, Request, Response, Header
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional
import json
import uuid

from app.services.llama_cloud import query_index
import asyncio
from typing import Dict, Any

router = APIRouter()

# Global session management for SSE
class SSESession:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.disconnected = False

sessions: Dict[str, SSESession] = {}

# Store the pipeline ID (from your synced index)
CONFLUENCE_PIPELINE_ID = "c6517502-2dce-4b8a-b134-834b3aa4ad24"


def handle_mcp_message(body: dict) -> dict:
    """Process MCP JSON-RPC messages and return response"""
    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id")
    
    print(f"DEBUG: MCP Method: {method}")
    if method == "tools/call":
        print(f"DEBUG: Tool Call: {params.get('name')} with {params.get('arguments')}")
    
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
        return None
    
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    }


@router.get("/sse")
async def mcp_sse_get(request: Request, accept: Optional[str] = Header(None)):
    """
    GET endpoint for SSE stream - allows server to send messages to client.
    Per MCP Streamable HTTP spec, this opens an SSE stream for server->client messages.
    """
    # Relaxed Accept check
    if accept and "text/event-stream" not in accept and "*/*" not in accept:
        return Response(status_code=405, content="Method Not Allowed")
    
    session_id = str(uuid.uuid4())
    session = SSESession()
    sessions[session_id] = session
    
    async def event_generator():
        try:
            # Correct MCP SSE initial event: MUST be an 'endpoint' event with the POST URL
            # We include session_id to route POST messages back to this SSE stream
            yield f"event: endpoint\ndata: /mcp/sse?session_id={session_id}\n\n"
            
            while not session.disconnected:
                if await request.is_disconnected():
                    session.disconnected = True
                    break
                
                try:
                    # Wait for messages from the queue
                    message = await asyncio.wait_for(session.queue.get(), timeout=30)
                    yield f"event: message\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Keep connection alive
                    yield ": keepalive\n\n"
                except Exception as e:
                    print(f"Error in SSE generator: {e}")
                    break
        finally:
            if session_id in sessions:
                del sessions[session_id]
            session.disconnected = True
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/sse")
async def mcp_sse_post(request: Request, session_id: Optional[str] = None):
    """
    POST endpoint for MCP Streamable HTTP transport.
    Client sends JSON-RPC messages here.
    """
    body = await request.json()
    
    # Check if this is a notification or response (no response needed)
    if "method" in body and body.get("id") is None:
        # This is a notification
        handle_mcp_message(body)
        return Response(status_code=202)
    
    if "result" in body or "error" in body:
        # This is a response from client
        return Response(status_code=202)
    
    # Identify the session to send the response to
    if not session_id or session_id not in sessions:
        # If no session, fallback to processing normally but we might lose responsiveness
        response = handle_mcp_message(body)
        return JSONResponse(content=response)
    
    # This is a request - process and send to the session queue
    session = sessions[session_id]
    response = handle_mcp_message(body)
    
    if response:
        await session.queue.put(response)
    
    # Per MCP spec, return 202 Accepted for SSE transport
    return Response(status_code=202)


@router.post("/")
async def mcp_handler(request: Request, accept: Optional[str] = Header(None)):
    """
    Main MCP endpoint - handles both JSON and SSE responses.
    """
    return await mcp_sse_post(request, accept)
