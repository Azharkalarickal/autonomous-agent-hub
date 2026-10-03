#!/usr/bin/env python3
"""
Commander Orchestrator MCP Server
==================================
Autonomous Orchestration Engine exposing FastMCP tools over Server-Sent Events (SSE).

Exposed Tools:
1. create_agent(name, role, persona_instructions, avatar_color)
2. list_fleet_agents()
3. order_skill_from_builder(skill_name, specifications)
4. bind_skill_to_agent(agent_name, mcp_url)

Author: Senior Python Backend Architect
"""

import os
import sys
import json
import time
import socket
import ssl
import logging
import threading
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from fastmcp import FastMCP

# -----------------------------------------------------------------------------
# Configuration & Environment
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [CommanderMCP] %(message)s"
)
logger = logging.getLogger("commander_orchestrator")

AGENT_HUB_API_URL = os.environ.get("AGENT_HUB_API_URL", "https://autonomous-agent-hub.onrender.com").rstrip("/")
SKILL_BUILDER_BASE_URL = os.environ.get("SKILL_BUILDER_BASE_URL", "https://skill-builder-engine.onrender.com").rstrip("/")
PORT = int(os.environ.get("PORT", "8001"))
HOST = os.environ.get("HOST", "0.0.0.0")

# -----------------------------------------------------------------------------
# Initialize FastMCP Server
# -----------------------------------------------------------------------------
mcp = FastMCP(
    "Commander Orchestrator Engine",
    instructions="You are the Commander Orchestrator, managing autonomous agent lifecycles, discovering fleet personas, dispatching skill generation to the Skill Builder, and binding remote MCP endpoints to active agents."
)

# -----------------------------------------------------------------------------
# Networking & HTTP Helpers
# -----------------------------------------------------------------------------
def _http_request(url: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    """Executes resilient HTTP JSON requests with structured error reporting."""
    ctx = ssl.create_default_context()
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {
        "User-Agent": "CommanderOrchestratorMCP/1.0",
        "Accept": "application/json, text/plain, */*"
    }
    if encoded_data is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed_json = json.loads(raw_body)
                return {"status": resp.status, "data": parsed_json, "raw": raw_body, "success": True}
            except json.JSONDecodeError:
                return {"status": resp.status, "data": raw_body, "raw": raw_body, "success": True}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        logger.error(f"HTTPError {e.code} on {method} {url}: {err_body}")
        return {"status": e.code, "error": err_body, "success": False}
    except Exception as e:
        logger.error(f"Network error on {method} {url}: {e}")
        return {"status": 0, "error": str(e), "success": False}


# -----------------------------------------------------------------------------
# MCP SSE Client Helper (for Abu's Skill Builder Engine)
# -----------------------------------------------------------------------------
def _invoke_remote_mcp_tool(base_url: str, tool_name: str, arguments: Dict[str, Any], timeout: int = 90) -> Dict[str, Any]:
    """
    Connects to a remote MCP server via SSE transport, performs initialize handshake,
    dispatches tools/call, and returns the response payload.
    """
    sse_url = f"{base_url}/sse"
    session_endpoint_url = None
    endpoint_event = threading.Event()
    stop_event = threading.Event()
    received_messages: List[Dict[str, Any]] = []

    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        sse_url,
        headers={"Accept": "text/event-stream", "Cache-Control": "no-cache", "User-Agent": "CommanderMCPClient/1.0"}
    )

    def sse_listener():
        nonlocal session_endpoint_url
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                event_type = "message"
                data_lines = []
                for raw_line in resp:
                    if stop_event.is_set():
                        break
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        if data_lines or event_type != "message":
                            combined = "\n".join(data_lines)
                            if event_type == "endpoint":
                                session_endpoint_url = urllib.parse.urljoin(base_url + "/", combined.strip())
                                endpoint_event.set()
                            elif event_type == "message":
                                try:
                                    received_messages.append(json.loads(combined))
                                except Exception:
                                    pass
                            event_type = "message"
                            data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    if ":" in line:
                        k, _, v = line.partition(":")
                        k = k.strip()
                        v = v.lstrip(" ")
                        if k == "event":
                            event_type = v
                        elif k == "data":
                            data_lines.append(v)
        except Exception as ex:
            logger.warning(f"SSE listener stream closed: {ex}")
            endpoint_event.set()

    thread = threading.Thread(target=sse_listener, daemon=True)
    thread.start()

    if not endpoint_event.wait(timeout=30) or not session_endpoint_url:
        stop_event.set()
        return {"success": False, "error": f"Failed to acquire session endpoint from {sse_url}"}

    # 1. Initialize Handshake
    init_payload = {
        "jsonrpc": "2.0",
        "id": "commander-init-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "commander-orchestrator", "version": "1.0.0"}
        }
    }
    _http_request(session_endpoint_url, method="POST", data=init_payload, timeout=20)
    _http_request(session_endpoint_url, method="POST", data={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=10)

    # 2. Dispatch Tool Call
    call_id = f"call-{int(time.time())}"
    tool_payload = {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    _http_request(session_endpoint_url, method="POST", data=tool_payload, timeout=30)

    # 3. Await Response on SSE stream
    start_time = time.time()
    while time.time() - start_time < timeout:
        for msg in list(received_messages):
            if msg.get("id") == call_id:
                stop_event.set()
                return {"success": True, "result": msg.get("result", {}), "raw": msg}
        time.sleep(1)

    stop_event.set()
    return {"success": False, "error": f"Timed out waiting for tool response from {tool_name}", "messages": received_messages}


# -----------------------------------------------------------------------------
# Tool 1: create_agent
# -----------------------------------------------------------------------------
@mcp.tool()
def create_agent(
    name: str,
    role: str,
    persona_instructions: str,
    avatar_color: str = "emerald"
) -> str:
    """
    Programmatically registers and deploys a new autonomous agent persona in the Autonomous Agent Hub.

    Args:
        name: Full agent name (e.g. 'Dexter - Lead Data Engineer')
        role: Primary operational role or specialty (e.g. 'Data Pipeline Specialist')
        persona_instructions: Detailed system prompt and behavioral directives for the agent
        avatar_color: UI badge color (emerald, cyan, amber, violet, rose, indigo, blue, fuchsia)

    Returns:
        JSON string containing the created agent's unique ID, registration status, and metadata.
    """
    logger.info(f"Invoked create_agent for '{name}' ({role})")
    url = f"{AGENT_HUB_API_URL}/api/agents/"
    payload = {
        "name": name.strip(),
        "role": role.strip(),
        "system_prompt": persona_instructions.strip(),
        "avatar_color": avatar_color.strip() or "emerald",
        "is_active": True
    }

    res = _http_request(url, method="POST", data=payload)
    if not res.get("success"):
        return json.dumps({
            "status": "error",
            "message": f"Failed to register agent in Hub API: {res.get('error')}",
            "http_status": res.get("status")
        }, indent=2)

    agent_data = res.get("data", {})
    return json.dumps({
        "status": "success",
        "message": f"Autonomous Agent '{name}' registered and deployed successfully.",
        "agent": agent_data
    }, indent=2)


# -----------------------------------------------------------------------------
# Tool 2: list_fleet_agents
# -----------------------------------------------------------------------------
@mcp.tool()
def list_fleet_agents() -> str:
    """
    Queries the Autonomous Agent Hub to retrieve all deployed agents, operational roles,
    active fleet statuses, and connected MCP tool endpoints.

    Returns:
        JSON string containing a formatted summary of all agents in the fleet.
    """
    logger.info("Invoked list_fleet_agents")
    url = f"{AGENT_HUB_API_URL}/api/agents/"
    res = _http_request(url, method="GET")

    if not res.get("success"):
        return json.dumps({
            "status": "error",
            "message": f"Failed to retrieve agents from Hub: {res.get('error')}",
            "http_status": res.get("status")
        }, indent=2)

    agents = res.get("data", [])
    fleet_summary = []

    for ag in agents:
        skills = [
            {
                "skill_name": s.get("skill_name"),
                "skill_url": s.get("skill_url"),
                "is_enabled": s.get("is_enabled")
            }
            for s in ag.get("skills", [])
        ]
        fleet_summary.append({
            "id": ag.get("id"),
            "name": ag.get("name"),
            "role": ag.get("role"),
            "is_active": ag.get("is_active"),
            "connected_mcps_count": len(skills),
            "connected_mcps": skills,
            "system_prompt_preview": (ag.get("system_prompt") or "")[:120] + "..."
        })

    return json.dumps({
        "status": "success",
        "total_agents": len(fleet_summary),
        "active_fleet_count": sum(1 for a in fleet_summary if a["is_active"]),
        "fleet": fleet_summary
    }, indent=2)


# -----------------------------------------------------------------------------
# Tool 3: order_skill_from_builder
# -----------------------------------------------------------------------------
@mcp.tool()
def order_skill_from_builder(
    skill_name: str,
    specifications: str,
    python_code: Optional[str] = None,
    requirements_txt: Optional[str] = None
) -> str:
    """
    Dispatches a generative skill build and cloud deployment request to Abu's Skill Builder Engine.

    Args:
        skill_name: Name of the microservice skill (e.g. 'whatsapp-vendor-notifier')
        specifications: Functional capabilities and purpose of the requested tool
        python_code: Optional FastMCP Python source code (if omitted, a standard template is synthesized)
        requirements_txt: Optional pip dependencies list (defaults to 'fastmcp>=0.1.0\nrequests')

    Returns:
        JSON string containing the build status, repository details, and live Render SSE endpoint URL.
    """
    logger.info(f"Ordering skill '{skill_name}' from Skill Builder Engine...")

    # Synthesize standard FastMCP template if code is not explicitly supplied
    if not python_code:
        sanitized_identifier = skill_name.replace("-", "_").replace(" ", "_").lower()
        python_code = f'''from fastmcp import FastMCP
import requests
import os

mcp = FastMCP("{skill_name}")

@mcp.tool()
def execute_{sanitized_identifier}_action(query: str) -> str:
    """{specifications}"""
    # Autonomous Tool Implementation for {skill_name}
    return f"Executed action for {skill_name} with query: {{query}}"

if __name__ == "__main__":
    mcp.run(transport="sse")
'''

    if not requirements_txt:
        requirements_txt = "fastmcp>=0.1.0\nrequests>=2.31.0"

    # Attempt generate_and_deploy_skill on the engine
    arguments = {
        "skill_name": skill_name.strip(),
        "description": specifications.strip(),
        "python_code": python_code.strip(),
        "requirements_txt": requirements_txt.strip(),
        "is_private_repo": False
    }

    resp = _invoke_remote_mcp_tool(
        base_url=SKILL_BUILDER_BASE_URL,
        tool_name="generate_and_deploy_skill",
        arguments=arguments,
        timeout=120
    )

    if not resp.get("success"):
        # Fallback to create_mcp_skill signature if schema variation exists
        fallback_args = {
            "skill_name": skill_name.strip(),
            "language": "python",
            "tools": [{"name": f"run_{skill_name.lower().replace('-', '_')}", "description": specifications}]
        }
        fallback_resp = _invoke_remote_mcp_tool(
            base_url=SKILL_BUILDER_BASE_URL,
            tool_name="create_mcp_skill",
            arguments=fallback_args,
            timeout=60
        )
        if fallback_resp.get("success"):
            return json.dumps({
                "status": "success",
                "message": f"Skill '{skill_name}' processed by Skill Builder (fallback interface).",
                "result": fallback_resp.get("result")
            }, indent=2)

        return json.dumps({
            "status": "error",
            "message": f"Skill Builder Engine invocation failed: {resp.get('error')}",
            "details": resp
        }, indent=2)

    return json.dumps({
        "status": "success",
        "message": f"Skill '{skill_name}' generated and deployed successfully.",
        "deployment_result": resp.get("result")
    }, indent=2)


# -----------------------------------------------------------------------------
# Tool 4: bind_skill_to_agent
# -----------------------------------------------------------------------------
@mcp.tool()
def bind_skill_to_agent(
    agent_name: str,
    mcp_url: str,
    skill_title: Optional[str] = None
) -> str:
    """
    Attaches a remote MCP endpoint URL to an autonomous agent persona in the database.

    Args:
        agent_name: Exact or partial name of the target agent (e.g. 'Arjun' or 'Maya - Structural CAD AI')
        mcp_url: The live SSE or HTTP MCP endpoint URL (e.g. 'https://cad-worker.onrender.com/sse')
        skill_title: Optional custom display label for the MCP tool

    Returns:
        JSON string containing the binding confirmation and updated agent MCP registry.
    """
    logger.info(f"Binding MCP '{mcp_url}' to agent '{agent_name}'")

    # 1. Locate Agent by Name
    list_url = f"{AGENT_HUB_API_URL}/api/agents/"
    res = _http_request(list_url, method="GET")

    if not res.get("success"):
        return json.dumps({
            "status": "error",
            "message": f"Could not query agents from Hub: {res.get('error')}"
        }, indent=2)

    agents = res.get("data", [])
    target_agent = None
    agent_name_lower = agent_name.lower().strip()

    for ag in agents:
        if agent_name_lower == ag.get("name", "").lower():
            target_agent = ag
            break
        elif agent_name_lower in ag.get("name", "").lower():
            target_agent = ag

    if not target_agent:
        return json.dumps({
            "status": "error",
            "message": f"No agent found matching name '{agent_name}'. Available agents: {[a.get('name') for a in agents]}"
        }, indent=2)

    agent_id = target_agent["id"]
    inferred_title = skill_title or mcp_url.split("//")[-1].split(".")[0].replace("-", " ").title() + " MCP"

    # 2. POST to Agent Skills endpoint
    attach_url = f"{AGENT_HUB_API_URL}/api/agents/{agent_id}/skills"
    skill_payload = {
        "skill_name": inferred_title.strip(),
        "skill_url": mcp_url.strip(),
        "is_enabled": True
    }

    attach_res = _http_request(attach_url, method="POST", data=skill_payload)
    if not attach_res.get("success"):
        return json.dumps({
            "status": "error",
            "message": f"Failed to attach skill to agent '{target_agent['name']}': {attach_res.get('error')}",
            "http_status": attach_res.get("status")
        }, indent=2)

    return json.dumps({
        "status": "success",
        "message": f"Successfully bound MCP tool '{inferred_title}' ({mcp_url}) to Agent '{target_agent['name']}'.",
        "agent_id": agent_id,
        "skill": attach_res.get("data")
    }, indent=2)


# -----------------------------------------------------------------------------
# Application Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("  Starting Commander Orchestrator FastMCP Engine")
    logger.info(f"  Transport: SSE (Server-Sent Events) | Host: {HOST} | Port: {PORT}")
    logger.info(f"  Hub API Target: {AGENT_HUB_API_URL}")
    logger.info(f"  Skill Builder Target: {SKILL_BUILDER_BASE_URL}")
    logger.info("=" * 80)

    # Launch FastMCP with native SSE transport on /sse endpoint
    mcp.run(transport="sse", host=HOST, port=PORT)
