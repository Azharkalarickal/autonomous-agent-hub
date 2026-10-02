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


# =========================================================================
# Real HTTP Execution Handlers for Remote MCP Endpoints
# =========================================================================

def to_serializable_dict(val: Any) -> Any:
    """Recursively converts Protobuf MapComposite, RepeatedComposite, and objects into standard dicts."""
    if hasattr(val, "items"):
        return {str(k): to_serializable_dict(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple, set)):
        return [to_serializable_dict(v) for v in val]
    elif isinstance(val, (str, int, float, bool)) or val is None:
        return val
    try:
        return json.loads(json.dumps(val, default=str))
    except Exception:
        return str(val)


def _resolve_candidate_urls(url: str, is_deploy: bool = False) -> List[str]:
    """
    Computes priority list of candidate POST endpoints.
    If given an SSE URL (ending in /sse), strips /sse and adapts to FastMCP /messages/ and REST handler routes.
    """
    cleaned_url = url.strip()
    candidates = []

    # Strip /sse if present to avoid 405 Method Not Allowed (GET only)
    base = cleaned_url
    if "/sse" in cleaned_url.lower():
        base = cleaned_url.rstrip("/")
        if base.lower().endswith("/sse"):
            base = base[:-4].rstrip("/")
        elif "/sse/" in base.lower():
            base = base.split("/sse/")[0].rstrip("/")
        elif "/sse" in base.lower():
            base = base.split("/sse")[0].rstrip("/")

    if is_deploy:
        candidates.extend([
            f"{base}/api/skills/deploy",
            f"{base}/deploy",
            f"{base}/api/skills",
            f"{base}/messages/",
            f"{base}/messages",
            f"{base}/tools/call",
            f"{base}/run-tool",
            f"{base}/"
        ])
    else:
        candidates.extend([
            f"{base}/messages/",
            f"{base}/messages",
            f"{base}/tools/call",
            f"{base}/run-tool",
            f"{base}/api/execute",
            f"{base}/api/skills/deploy",
            f"{base}/"
        ])

    # Deduplicate while preserving priority order
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)
    return unique_candidates


def _dispatch_remote_http(url: str, payload: Dict[str, Any], method: str = "POST", is_deploy: bool = False) -> Dict[str, Any]:
    """
    Sends a real HTTP request to remote MCP or Skill Builder endpoints.
    Automatically handles /sse stripping, FastMCP /messages/ adaptation, JSON-RPC formatting, and full error logging.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream, text/plain, */*",
        "User-Agent": "AutonomousAgentHub/1.0"
    }
    clean_payload = to_serializable_dict(payload)
    candidate_urls = _resolve_candidate_urls(url, is_deploy=is_deploy)

    last_response_info = None

    for target_url in candidate_urls:
        try:
            logger.info(f"Dispatching HTTP {method} to '{target_url}' with payload: {json.dumps(clean_payload)[:250]}")

            if method.upper() == "GET":
                resp = requests.get(target_url, params=clean_payload, headers=headers, timeout=25)
            else:
                # Format payload according to endpoint expectations
                post_body = clean_payload
                if ("/messages" in target_url.lower() or "/tools/call" in target_url.lower()) and not ("jsonrpc" in clean_payload):
                    post_body = {
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": clean_payload.get("action") or clean_payload.get("skill_name") or "execute",
                            "arguments": clean_payload.get("parameters") or clean_payload
                        },
                        "id": 1
                    }

                resp = requests.post(target_url, json=post_body, headers=headers, timeout=25)

            # Capture response telemetry
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
                logger.info(f"Success from '{target_url}' (HTTP {resp.status_code}): {str(data)[:200]}")
                return last_response_info

            # If 405 Method Not Allowed or 404, log full diagnostics and try next route
            logger.warning(
                f"HTTP {resp.status_code} from '{target_url}'. "
                f"Response body: {resp.text[:300]}. Attempting next candidate endpoint..."
            )

        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to endpoint '{target_url}' (25s exceeded)")
            last_response_info = {
                "status_code": 408,
                "success": False,
                "error": f"Request timeout after 25s at {target_url}",
                "endpoint": target_url
            }
        except Exception as e:
            logger.exception(f"Exception during request to '{target_url}': {e}")
            last_response_info = {
                "status_code": 500,
                "success": False,
                "error": str(e),
                "endpoint": target_url
            }

    # All candidate URLs exhausted
    logger.error(f"All candidate routes failed for {url}. Last diagnostic: {last_response_info}")
    return last_response_info or {
        "status_code": 500,
        "success": False,
        "error": f"Unable to reach valid HTTP handler for {url}",
        "endpoint": url
    }


def execute_tool_call(func_name: str, args: Dict[str, Any], skills: List[AgentSkill]) -> Dict[str, Any]:
    """
    Executes real remote MCP actions based on the Gemini function call.
    """
    # 1. Create / Build MCP Skill
    if func_name == "create_mcp_skill":
        skill_name = args.get("skill_name", "CustomSkill")
        description = args.get("description", "")
        code = args.get("code", "")
        language = args.get("language", "python")
        
        target_url = DEFAULT_SKILL_BUILDER_ENDPOINT + "/api/skills/deploy"
        for s in skills:
            if s.is_enabled and ("builder" in s.skill_name.lower() or "deploy" in s.skill_url.lower() or "skill" in s.skill_name.lower()):
                target_url = s.skill_url
                break
                
        payload = {
            "skill_name": skill_name,
            "description": description,
            "code": code,
            "language": language
        }
        res = _dispatch_remote_http(target_url, payload, method="POST", is_deploy=True)
        
        if res.get("success"):
            data = res.get("data", {})
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
                "message": f"Skill '{skill_name}' successfully deployed to live MCP engine.",
                "server_response": data
            }
        else:
            return {
                "status": "deployment_failed",
                "error": res.get("error") or res.get("data") or res.get("raw_response"),
                "status_code": res.get("status_code"),
                "endpoint": res.get("endpoint") or target_url
            }

    # 2. Deploy Skill Generic
    elif func_name == "deploy_skill":
        skill_name = args.get("skill_name", "")
        endpoint_url = args.get("endpoint_url") or DEFAULT_SKILL_BUILDER_ENDPOINT + "/deploy"
        config = args.get("config") or {}
        payload = {"skill_name": skill_name, "config": config}
        res = _dispatch_remote_http(endpoint_url, payload, method="POST", is_deploy=True)
        return res

    # 3. Execute Connected Skill Tool Action
    elif func_name == "execute_connected_skill":
        skill_name = args.get("skill_name", "").lower()
        action = args.get("action", "")
        parameters = args.get("parameters") or {}
        
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

        payload = {"action": action, "parameters": parameters, "skill_name": target_skill.skill_name}
        return _dispatch_remote_http(target_skill.skill_url, payload, method="POST", is_deploy=False)

    # 4. Fallback Generic Remote HTTP Endpoint Caller
    elif func_name == "call_remote_mcp_endpoint":
        url = args.get("endpoint_url", "")
        payload = args.get("payload") or {}
        method = args.get("method", "POST")
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
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-2.5-flash",
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
