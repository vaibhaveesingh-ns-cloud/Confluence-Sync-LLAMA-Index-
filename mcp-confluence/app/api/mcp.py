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
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

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
                        "description": "CRITICAL: Use this tool to search the internal Confluence knowledge base. Use this for ANY questions about DevOps, EKS, CI/CD, security, LlamaIndex, or any internal documentation. If a user provides a Confluence link, search for its title using this tool.",
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
                    },
                    {
                        "name": "get_page",
                        "description": "Get the full content of a specific Confluence page by its title or ID. Use this when you have a specific page in mind or when a user provides a link/title.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "The exact title of the page"
                                },
                                "page_id": {
                                    "type": "string",
                                    "description": "The unique ID of the page (if known)"
                                },
                                "space_key": {
                                    "type": "string",
                                    "description": "Optional: The space key to search within (e.g. 'AICore')"
                                }
                            }
                        }
                    },
                    {
                        "name": "list_spaces",
                        "description": "List all accessible Confluence spaces. Use this to understand the organization of the knowledge base.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
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
                logger.info(f"search_confluence: Searching for '{query}' with top_k={top_k}")
                results = query_index(CONFLUENCE_PIPELINE_ID, query, top_k)
                search_results = results.get("results", [])
                logger.info(f"search_confluence: Found {len(search_results)} results for query: '{query}'")
                
                formatted_results = []
                for i, result in enumerate(search_results, 1):
                    text = result.get("text", "")
                    metadata = result.get("metadata", {})
                    score = result.get("score", 0)
                    filename = metadata.get("filename", "Unknown")
                    
                    formatted_results.append(
                        f"## Result {i} (Score: {score:.2f})\n"
                        f"**Source:** {filename}\n\n"
                        f"{text}\n"
                    )
                
                content = "\n---\n".join(formatted_results) if formatted_results else "No results found in Confluence for this query."
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": content}]
                    }
                }
            except Exception as e:
                logger.error(f"search_confluence failed: {e}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "isError": True
                    }
                }
        
        elif tool_name == "get_page":
            title = arguments.get("title")
            page_id = arguments.get("page_id")
            space_key = arguments.get("space_key")
            
            try:
                if not title and not page_id:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"type": "text", "text": "Please provide either a 'title' or 'page_id'."}]}
                    }
                
                # Use LlamaCloud to search for the page
                search_query = title if title else page_id
                if space_key:
                    search_query = f"{space_key} {search_query}"
                
                logger.info(f"get_page: Searching LlamaCloud for '{search_query}'")
                results = query_index(CONFLUENCE_PIPELINE_ID, search_query, top_k=5)
                search_results = results.get("results", [])
                
                if not search_results:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"type": "text", "text": f"No page found matching '{search_query}'"}]}
                    }
                
                # Return the best match (highest score)
                best_match = search_results[0]
                text = best_match.get("text", "")
                metadata = best_match.get("metadata", {})
                score = best_match.get("score", 0)
                filename = metadata.get("filename", "Unknown")
                
                logger.info(f"get_page: Found best match '{filename}' with score {score:.2f}")
                
                content = f"# {filename}\n\n**Relevance Score:** {score:.2f}\n\n{text}"
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": content}]
                    }
                }
            except Exception as e:
                logger.error(f"get_page failed: {e}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}
                }

        elif tool_name == "list_spaces":
            try:
                logger.info("list_spaces: Extracting spaces from LlamaCloud index")
                
                # Query LlamaCloud to get a sample of documents
                results = query_index(CONFLUENCE_PIPELINE_ID, "*", top_k=100)
                search_results = results.get("results", [])
                
                # Extract unique space names from filenames
                # Assuming filename format: SpaceName_PageTitle_PageID.md
                spaces_set = set()
                for result in search_results:
                    metadata = result.get("metadata", {})
                    filename = metadata.get("filename", "")
                    
                    # Extract space name (part before first underscore)
                    if "_" in filename:
                        space_name = filename.split("_")[0]
                        spaces_set.add(space_name)
                
                if not spaces_set:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"type": "text", "text": "No spaces found in indexed documents."}]}
                    }
                
                formatted_spaces = [f"- {space}" for space in sorted(spaces_set)]
                content = f"Indexed Confluence Spaces ({len(spaces_set)} found):\n" + "\n".join(formatted_spaces)
                
                logger.info(f"list_spaces: Found {len(spaces_set)} unique spaces")
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": content}]}
                }
            except Exception as e:
                logger.error(f"list_spaces failed: {e}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}
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
        print(f"DEBUG: Starting SSE event generator for session {session_id}")
        try:
            # Correct MCP SSE initial event: MUST be an 'endpoint' event with the POST URL
            # LibreChat expects a plain string URL here
            endpoint_url = f"/mcp/sse?session_id={session_id}"
            print(f"DEBUG: Yielding endpoint: {endpoint_url}")
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            
            while not session.disconnected:
                if await request.is_disconnected():
                    print(f"DEBUG: Session {session_id} disconnected by client")
                    session.disconnected = True
                    break
                
                try:
                    # Wait for messages from the queue
                    message = await asyncio.wait_for(session.queue.get(), timeout=30)
                    print(f"DEBUG: [SSE -> {session_id}] Sending message: {message.get('method', 'response')}")
                    yield f"event: message\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Keep connection alive
                    yield ": keepalive\n\n"
                except Exception as e:
                    print(f"DEBUG: Error in SSE generator for {session_id}: {e}")
                    break
        finally:
            print(f"DEBUG: Cleaning up session {session_id}")
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
    method = body.get("method", "response/unknown")
    
    print(f"DEBUG: Received POST for session {session_id}, method: {method}")
    
    # 1. Check if this is a notification or response (no response needed via SSE)
    if "method" in body and body.get("id") is None:
        print(f"DEBUG: Handling notification: {method}")
        handle_mcp_message(body)
        return Response(status_code=202)
    
    if "result" in body or "error" in body:
        print(f"DEBUG: Handling client response")
        return Response(status_code=202)
    
    # 2. Identify the session to send the response to
    if not session_id or session_id not in sessions:
        print(f"DEBUG: No session ID {session_id} found in active sessions")
        # Fallback to direct JSON ONLY if no session
        response = handle_mcp_message(body)
        return JSONResponse(content=response)
    
    # 3. Standard Request: process and send to the session queue
    session = sessions[session_id]
    response = handle_mcp_message(body)
    
    if response:
        print(f"DEBUG: Queuing response for session {session_id}")
        await session.queue.put(response)
    else:
        print(f"DEBUG: No response generated for method {method}")
    
    return Response(status_code=202)


@router.post("/")
async def mcp_handler(request: Request, accept: Optional[str] = Header(None)):
    """
    Main MCP endpoint - handles both JSON and SSE responses.
    """
    return await mcp_sse_post(request, accept)
