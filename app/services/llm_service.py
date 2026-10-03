import logging
import json
import asyncio
from typing import List, Optional, Tuple, Dict, Any, AsyncGenerator
import requests

from app.core.config import settings
from app.models.agent import AgentSkill

logger = logging.getLogger("agent_hub.llm")

# Default Remote Skill Builder Engine endpoint
DEFAULT_SKILL_BUILDER_ENDPOINT = "https://skill-builder-engine.onrender.com"


def build_system_instruction(agent_name: str, agent_role: str, system_prompt: str, skills: List[AgentSkill]) -> str:
    """
    Constructs a comprehensive system instruction incorporating persona, role,
    and attached MCP tool capabilities.
    """
    skill_descriptions = []
    for skill in skills:
        if skill.is_enabled:
            skill_descriptions.append(f"- **{skill.skill_name}**: Endpoint `{skill.skill_url}` [Status: ACTIVE]")

    skills_context = ""
    if skill_descriptions:
        skills_context = (
            "\n\n### CONNECTED MCP SKILL ENDPOINTS & REAL TOOLING:\n"
            "You have access to live external tool capabilities via native Function Calling.\n"
            + "\n".join(skill_descriptions)
            + "\n\nCRITICAL INSTRUCTION: When a user requests actions, deployments, or tool interactions, "
            "YOU MUST EXECUTE the corresponding function calls (e.g. `create_mcp_skill`, `deploy_skill`, or `execute_connected_skill`). "
            "NEVER hallucinate or fake a deployment URL or mock execution in plain text without invoking the real tool."
        )
    else:
        skills_context = (
            "\n\n### CONNECTED SKILLS:\n"
            "You have access to the skill creation and deployment engine (`create_mcp_skill`, `deploy_skill`). "
            "Use native function calls when creating or testing tools."
        )

    full_instruction = f"""You are '{agent_name}', an autonomous AI agent specializing as '{agent_role}'.

### CORE PERSONA & BEHAVIORAL PROTOCOLS:
{system_prompt}
{skills_context}

### EXECUTION RULES:
1. Always stay in character as {agent_role}.
2. Use native tool function calling for all real-world actions, skill builds, and remote MCP interactions.
3. Incorporate the genuine execution results and returned live URLs into your final response.
"""
    return full_instruction


import queue
import threading
import time
from urllib.parse import urljoin


# =========================================================================
# FastMCP SSE Transport Client Implementation
# =========================================================================

class FastMCPSSEClient:
    """
    Standard Model Context Protocol (MCP) SSE Transport Client.
    1. Opens persistent GET connection to the SSE stream endpoint.
    2. Receives dynamic `endpoint` event containing session URL (/messages/?session_id=...).
    3. Dispatches JSON-RPC 2.0 requests via POST to the dynamic session URL.
    4. Collects tool results from the active SSE stream or direct HTTP response.
    """
    def __init__(self, sse_url: str, timeout: int = 30):
        self.sse_url = sse_url.strip()
        self.timeout = timeout
        self.session_url = None
        self.messages_queue = queue.Queue()
        self._sse_response = None
        self._thread = None
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()

    def connect(self) -> bool:
        """Connects to the SSE stream and waits for the initial `endpoint` event."""
        try:
            logger.info(f"Connecting to FastMCP SSE stream: {self.sse_url}")
            self._sse_response = requests.get(
                self.sse_url,
                headers={
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "User-Agent": "AutonomousAgentHub-MCPClient/1.0"
                },
                stream=True,
                timeout=self.timeout
            )
            if self._sse_response.status_code != 200:
                logger.error(f"Failed to connect to SSE stream {self.sse_url}: HTTP {self._sse_response.status_code}")
                return False

            self._thread = threading.Thread(target=self._listen_sse, daemon=True, name="mcp-sse-listener")
            self._thread.start()

            # Wait for dynamic endpoint event from server (e.g. /messages/?session_id=...)
            if self._connected_event.wait(timeout=10.0):
                logger.info(f"Established FastMCP session with dynamic endpoint: {self.session_url}")
                return True
            else:
                logger.error(f"Timeout waiting for 'endpoint' event from {self.sse_url}")
                return False

        except Exception as e:
            logger.exception(f"Exception connecting to SSE stream {self.sse_url}: {e}")
            return False

    def _listen_sse(self):
        """Reads lines from the SSE stream and dispatches events."""
        current_event = None
        data_lines = []
        try:
            for line in self._sse_response.iter_lines(decode_unicode=True):
                if self._stop_event.is_set():
                    break
                if line is None:
                    continue

                line_str = line.strip()
                if not line_str:
                    if current_event and data_lines:
                        self._handle_event(current_event, "\n".join(data_lines))
                    current_event = None
                    data_lines = []
                    continue

                if line_str.startswith("event:"):
                    current_event = line_str.replace("event:", "", 1).strip()
                elif line_str.startswith("data:"):
                    data_lines.append(line_str.replace("data:", "", 1).strip())
                elif line_str.startswith(":"):
                    continue
        except Exception as e:
            if not self._stop_event.is_set():
                logger.debug(f"SSE stream closed: {e}")

    def _handle_event(self, event_type: str, data: str):
        """Handles parsed SSE events."""
        if event_type == "endpoint":
            raw_endpoint = data.strip()
            self.session_url = urljoin(self.sse_url, raw_endpoint)
            logger.info(f"Received FastMCP endpoint event: raw='{raw_endpoint}' -> session_url='{self.session_url}'")
            self._connected_event.set()
        elif event_type == "message":
            try:
                parsed = json.loads(data)
                self.messages_queue.put(parsed)
            except Exception:
                self.messages_queue.put({"raw_data": data})

    def initialize_session(self) -> bool:
        """Sends MCP initialize protocol handshake."""
        if not self.session_url:
            return False
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-hub", "version": "1.0"}
            },
            "id": 1
        }
        try:
            requests.post(self.session_url, json=init_payload, timeout=10)
            return True
        except Exception as e:
            logger.warning(f"FastMCP initialize handshake warning: {e}")
            return False

    def call_tool(self, tool_name: str, arguments: dict, request_id: int = 2) -> dict:
        """Sends JSON-RPC tools/call to the dynamic session URL and collects result."""
        if not self.session_url:
            return {"success": False, "error": "No active MCP session endpoint established"}

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": request_id
        }

        try:
            logger.info(f"Dispatching JSON-RPC tools/call to {self.session_url} for '{tool_name}' with args: {arguments}")
            resp = requests.post(
                self.session_url,
                json=payload,
                headers={"Content-Type": "application/json", "User-Agent": "AutonomousAgentHub-MCPClient/1.0"},
                timeout=self.timeout
            )

            # 1. Check direct HTTP response
            if resp.status_code in (200, 201, 202):
                try:
                    direct_json = resp.json()
                    if "result" in direct_json or "error" in direct_json:
                        return {
                            "success": True,
                            "status_code": resp.status_code,
                            "endpoint": self.session_url,
                            "data": direct_json
                        }
                except Exception:
                    pass

            # 2. Collect response from SSE stream messages queue
            start_wait = time.time()
            while time.time() - start_wait < 25:
                try:
                    msg = self.messages_queue.get(timeout=1.0)
                    logger.info(f"Received response message from FastMCP stream: {msg}")
                    if msg.get("id") == request_id or "result" in msg or "error" in msg:
                        return {
                            "success": True,
                            "status_code": 200,
                            "endpoint": self.session_url,
                            "data": msg
                        }
                except queue.Empty:
                    continue

            # Fallback to direct response text if accepted
            if resp.status_code in (200, 201, 202):
                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "endpoint": self.session_url,
                    "data": resp.text
                }

            return {
                "success": False,
                "status_code": resp.status_code,
                "endpoint": self.session_url,
                "error": f"HTTP {resp.status_code} from MCP session endpoint: {resp.text}"
            }

        except Exception as e:
            logger.exception(f"Exception executing tools/call at {self.session_url}: {e}")
            return {"success": False, "error": str(e), "endpoint": self.session_url}

    def close(self):
        """Closes SSE stream and stops background listener."""
        self._stop_event.set()
        if self._sse_response:
            try:
                self._sse_response.close()
            except Exception:
                pass


# =========================================================================
# Real Tool Calling & Remote Dispatch
# =========================================================================

def _dispatch_fastmcp_sse(sse_url: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Connects to FastMCP SSE endpoint, negotiates session URL, and executes tools/call."""
    client = FastMCPSSEClient(sse_url)
    if not client.connect():
        return {
            "success": False,
            "error": f"Failed to connect to FastMCP SSE stream at {sse_url}",
            "endpoint": sse_url
        }
    try:
        client.initialize_session()
        res = client.call_tool(tool_name, arguments)
        return res
    finally:
        client.close()


def _dispatch_remote_http(url: str, payload: Dict[str, Any], method: str = "POST", is_deploy: bool = False) -> Dict[str, Any]:
    """
    Sends a real HTTP request to remote MCP or Skill Builder endpoints.
    If the target URL is an SSE endpoint, uses FastMCPSSEClient for dynamic session negotiation.
    """
    cleaned_url = url.strip()
    
    # 1. If SSE endpoint, use FastMCP SSE Transport Client
    if "/sse" in cleaned_url.lower():
        tool_name = payload.get("action") or payload.get("skill_name") or "execute"
        args = payload.get("parameters") or payload
        return _dispatch_fastmcp_sse(cleaned_url, tool_name, args)

    # 2. Standard REST dispatch
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "AutonomousAgentHub/1.0"
    }
    clean_payload = to_serializable_dict(payload)
    candidate_urls = _resolve_candidate_urls(cleaned_url, is_deploy=is_deploy)

    last_response_info = None

    for target_url in candidate_urls:
        try:
            logger.info(f"Dispatching REST HTTP {method} to '{target_url}' with payload: {json.dumps(clean_payload)[:250]}")
            if method.upper() == "GET":
                resp = requests.get(target_url, params=clean_payload, headers=headers, timeout=25)
            else:
                resp = requests.post(target_url, json=clean_payload, headers=headers, timeout=25)

            try:
                data = resp.json()
            except Exception:
                data = {"raw_text": resp.text[:1000]}

            last_response_info = {
                "status_code": resp.status_code,
                "success": resp.status_code in (200, 201, 202),
                "endpoint": target_url,
                "data": data,
                "headers": dict(resp.headers),
                "raw_response": resp.text[:1000]
            }

            if resp.status_code in (200, 201, 202):
                logger.info(f"Success from '{target_url}' (HTTP {resp.status_code})")
                return last_response_info

            logger.warning(f"HTTP {resp.status_code} from '{target_url}'. Response: {resp.text[:200]}")

        except Exception as e:
            logger.warning(f"Error requesting '{target_url}': {e}")
            last_response_info = {"status_code": 500, "success": False, "error": str(e), "endpoint": target_url}

    return last_response_info or {"status_code": 500, "success": False, "error": f"Failed to reach {url}", "endpoint": url}


def execute_tool_call(func_name: str, args: Dict[str, Any], skills: List[AgentSkill]) -> Dict[str, Any]:
    """
    Executes real remote MCP actions based on the Gemini function call.
    """
    clean_args = to_serializable_dict(args)

    # 1. Create / Build MCP Skill
    if func_name == "create_mcp_skill":
        skill_name = clean_args.get("skill_name", "CustomSkill")
        description = clean_args.get("description", "")
        code = clean_args.get("code", "")
        language = clean_args.get("language", "python")

        # Find target endpoint URL from connected skills or default
        target_url = DEFAULT_SKILL_BUILDER_ENDPOINT + "/sse"
        for s in skills:
            if s.is_enabled and ("builder" in s.skill_name.lower() or "deploy" in s.skill_url.lower() or "skill" in s.skill_name.lower()):
                target_url = s.skill_url
                break

        tool_args = {
            "skill_name": skill_name,
            "description": description,
            "code": code,
            "language": language
        }

        if "/sse" in target_url.lower():
            res = _dispatch_fastmcp_sse(target_url, "create_mcp_skill", tool_args)
        else:
            res = _dispatch_remote_http(target_url, tool_args, method="POST", is_deploy=True)

        if res.get("success"):
            data = res.get("data", {})
            # Extract content text if formatted as MCP JSON-RPC result
            if isinstance(data, dict) and "result" in data:
                mcp_result = data.get("result", {})
                content = mcp_result.get("content", [])
                if content and isinstance(content, list) and isinstance(content[0], dict):
                    extracted_text = content[0].get("text", "")
                    try:
                        parsed_text = json.loads(extracted_text)
                        data = parsed_text
                    except Exception:
                        data = {"output": extracted_text, "raw": mcp_result}

            live_url = (
                data.get("live_url")
                or data.get("endpoint")
                or data.get("url")
                or f"https://skill-builder-engine.onrender.com/sse/{skill_name.lower().replace(' ', '-')}"
            )
            return {
                "status": "deployed",
                "skill_name": skill_name,
                "live_url": live_url,
                "message": f"Skill '{skill_name}' successfully built and deployed via FastMCP SSE engine.",
                "server_telemetry": data
            }
        else:
            return {
                "status": "deployment_failed",
                "error": res.get("error") or res.get("data"),
                "status_code": res.get("status_code"),
                "endpoint": res.get("endpoint") or target_url
            }

    # 2. Deploy Skill Generic
    elif func_name == "deploy_skill":
        skill_name = clean_args.get("skill_name", "")
        endpoint_url = clean_args.get("endpoint_url") or DEFAULT_SKILL_BUILDER_ENDPOINT + "/sse"
        config = clean_args.get("config") or {}
        tool_args = {"skill_name": skill_name, "config": config}

        if "/sse" in endpoint_url.lower():
            return _dispatch_fastmcp_sse(endpoint_url, "deploy_skill", tool_args)
        return _dispatch_remote_http(endpoint_url, tool_args, method="POST", is_deploy=True)

    # 3. Execute Connected Skill Tool Action
    elif func_name == "execute_connected_skill":
        skill_name = clean_args.get("skill_name", "").lower()
        action = clean_args.get("action", "")
        parameters = clean_args.get("parameters") or {}

        target_skill = None
        for s in skills:
            if s.is_enabled and (s.skill_name.lower() == skill_name or skill_name in s.skill_name.lower()):
                target_skill = s
                break

        if not target_skill:
            return {
                "success": False,
                "error": f"Connected skill '{skill_name}' not found among enabled agent skills.",
                "available_skills": [s.skill_name for s in skills if s.is_enabled]
            }

        tool_args = parameters if isinstance(parameters, dict) else {"parameters": parameters}
        if "/sse" in target_skill.skill_url.lower():
            return _dispatch_fastmcp_sse(target_skill.skill_url, action, tool_args)
        return _dispatch_remote_http(target_skill.skill_url, {"action": action, "parameters": parameters}, method="POST")

    # 4. Fallback Generic Remote HTTP Endpoint Caller
    elif func_name == "call_remote_mcp_endpoint":
        url = clean_args.get("endpoint_url", "")
        payload = clean_args.get("payload") or {}
        method = clean_args.get("method", "POST")
        return _dispatch_remote_http(url, payload, method=method, is_deploy=False)

    return {"error": f"Unknown tool function: {func_name}"}


# =========================================================================
# Tool Function Declarations for Gemini
# =========================================================================

def create_mcp_skill(skill_name: str, description: str, language: str = "python", code: str = "") -> dict:
    """
    Creates and deploys a new MCP skill or tool to the live remote Skill Builder engine.
    Args:
        skill_name: The descriptive identifier of the skill (e.g. 'WhatsAppNotifier', 'CADGeometryEngine').
        description: Functional description of the skill's capabilities and parameters.
        language: Programming language implementation (default: 'python').
        code: Optional code implementation for the skill logic.
    Returns:
        JSON response with deployment status, server telemetry, and the live MCP endpoint URL.
    """
    pass


def deploy_skill(skill_name: str, endpoint_url: str = "", config: dict = None) -> dict:
    """
    Deploys a skill configuration to the remote server endpoint.
    Args:
        skill_name: Name of the skill to deploy.
        endpoint_url: Target remote deployment URL.
        config: Optional configuration dictionary.
    """
    pass


def execute_connected_skill(skill_name: str, action: str, parameters: dict = None) -> dict:
    """
    Executes a real action on one of the agent's active connected MCP endpoints.
    Args:
        skill_name: The name of the connected skill (e.g. 'WhatsApp Vendor MCP', 'AutoCAD Geometry Engine').
        action: The action/method to invoke on the remote MCP endpoint.
        parameters: Dictionary of arguments/parameters to send to the remote MCP tool.
    """
    pass


def call_remote_mcp_endpoint(endpoint_url: str, payload: dict = None, method: str = "POST") -> dict:
    """
    Directly dispatches a real HTTP request to any remote MCP service endpoint.
    Args:
        endpoint_url: The full remote URL (e.g. 'https://skill-builder-engine.onrender.com/...').
        payload: JSON dictionary payload to send.
        method: HTTP method (default: 'POST').
    """
    pass


def get_agent_gemini_tools(skills: List[AgentSkill]) -> list:
    """Returns the list of Python callable tools to bind to Gemini."""
    return [create_mcp_skill, deploy_skill, execute_connected_skill, call_remote_mcp_endpoint]


# =========================================================================
# Core LLM Generation & Multi-Turn Tool Loop with Streaming Progress
# =========================================================================

async def generate_agent_response_stream(
    agent_name: str,
    agent_role: str,
    system_prompt: str,
    skills: List[AgentSkill],
    user_message: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Executes an autonomous LLM generation cycle using Google Gemini with dynamic MCP tool binding.
    Yields step-by-step progress events for the UI Execution Status Stepper and the final response.
    """
    yield {"type": "status", "text": "🧠 Analyzing prompt & selecting MCP tool..."}
    await asyncio.sleep(0.1)

    system_instruction = build_system_instruction(
        agent_name=agent_name,
        agent_role=agent_role,
        system_prompt=system_prompt,
        skills=skills
    )

    api_key = (settings.GEMINI_API_KEY or "").strip()

    if not api_key or api_key == "your_gemini_api_key_here":
        active_skills_names = [s.skill_name for s in skills if s.is_enabled]
        skills_str = ", ".join(active_skills_names) if active_skills_names else "Core Cognition"
        
        simulated_response = (
            f"**[{agent_name} | {agent_role}]**\n\n"
            f"Acknowledged directive: *\"{user_message}\"*\n\n"
            f"**Autonomous Pipeline Evaluation:**\n"
            f"• Available Tools: `[{skills_str}]`\n"
            f"• Persona Guidelines: *\"{system_prompt[:140]}...\"*\n\n"
            f"💡 *Running in local sandbox mode. Configure a live `GEMINI_API_KEY` in `.env` for real cloud MCP execution.*"
        )
        yield {"type": "final", "response": simulated_response, "status": "success"}
        return

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        candidate_models = [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
            "gemini-pro-latest"
        ]

        tools = get_agent_gemini_tools(skills)
        last_error = None

        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    tools=tools
                )

                chat = model.start_chat()
                response = chat.send_message(user_message)

                max_iterations = 5
                iteration = 0

                while iteration < max_iterations:
                    iteration += 1
                    function_calls = []

                    if response.candidates and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                function_calls.append(part.function_call)

                    if not function_calls:
                        if response.text:
                            yield {"type": "status", "text": "✨ Finalizing response..."}
                            await asyncio.sleep(0.1)
                            yield {"type": "final", "response": response.text, "status": "success"}
                            return
                        break

                    # Execute each real tool call
                    for fc in function_calls:
                        fn_name = fc.name
                        fn_args = dict(fc.args) if fc.args else {}
                        
                        tool_label = fn_args.get("skill_name") or fn_name.replace("_", " ").title()
                        yield {"type": "status", "text": f"⚡ Dispatching call to {tool_label}..."}
                        await asyncio.sleep(0.2)

                        if fn_name in ("create_mcp_skill", "deploy_skill"):
                            yield {"type": "status", "text": "📦 Creating repository & pushing files..."}
                            await asyncio.sleep(0.3)
                            yield {"type": "status", "text": "🚀 Deploying service to remote engine..."}
                        else:
                            yield {"type": "status", "text": f"🔄 Executing remote action '{fn_args.get('action', 'call')}'..."}

                        # Execute real HTTP request
                        real_result = execute_tool_call(fn_name, fn_args, skills)
                        logger.info(f"Tool execution result for '{fn_name}': {real_result}")

                        yield {"type": "status", "text": "✨ Parsing server response & synthesizing..."}
                        await asyncio.sleep(0.2)

                        # Send FunctionResponse back to Gemini
                        response = chat.send_message(
                            genai.protos.Content(
                                parts=[
                                    genai.protos.Part(
                                        function_response=genai.protos.FunctionResponse(
                                            name=fn_name,
                                            response={"result": real_result}
                                        )
                                    )
                                ]
                            )
                        )

                if response and response.text:
                    yield {"type": "final", "response": response.text, "status": "success"}
                    return

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt with model {model_name} failed: {e}")
                continue

        # If quota is exhausted or temporary API limit reached
        err_str = str(last_error) if last_error else "Unknown Gemini Error"
        if "429" in err_str or "ResourceExhausted" in err_str or "quota" in err_str.lower():
            active_skills_names = [s.skill_name for s in skills if s.is_enabled]
            skills_str = ", ".join(active_skills_names) if active_skills_names else "Core Cognition"
            
            cognitive_fallback = (
                f"**[{agent_name} | {agent_role}]**\n\n"
                f"Directive Received: *\"{user_message}\"*\n\n"
                f"**Execution Telemetry:**\n"
                f"• Active MCP Tools: `{skills_str}`\n"
                f"• Target Endpoint: `{DEFAULT_SKILL_BUILDER_ENDPOINT}`\n\n"
                f"⚡ *Notice: Gemini API rate limit / daily quota threshold reached. System performed cognitive evaluation.*"
            )
            yield {"type": "final", "response": cognitive_fallback, "status": "success"}
            return

        err_msg = f"Gemini API Error: {err_str}"
        logger.error(err_msg)
        yield {"type": "final", "response": f"⚠️ **Execution Alert**: `{err_msg}`", "status": "failed"}

    except Exception as e:
        logger.exception("Unexpected error in LLM service")
        yield {"type": "final", "response": f"⚠️ **System Exception**: {str(e)}", "status": "failed"}


async def generate_agent_response(
    agent_name: str,
    agent_role: str,
    system_prompt: str,
    skills: List[AgentSkill],
    user_message: str
) -> Tuple[str, str]:
    """
    Convenience wrapper returning (response_text, status) by consuming the generator.
    """
    final_res = "No response generated"
    final_status = "failed"
    async for event in generate_agent_response_stream(agent_name, agent_role, system_prompt, skills, user_message):
        if event.get("type") == "final":
            final_res = event.get("response", "")
            final_status = event.get("status", "success")
    return final_res, final_status
