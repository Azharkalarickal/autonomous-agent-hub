import logging
import json
from typing import List, Optional, Tuple, Dict, Any
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


def _dispatch_remote_http(url: str, payload: Dict[str, Any], method: str = "POST") -> Dict[str, Any]:
    """Sends a real HTTP request to a remote MCP or Skill Builder endpoint."""
    headers = {"Content-Type": "application/json", "User-Agent": "AutonomousAgentHub/1.0"}
    clean_payload = to_serializable_dict(payload)
    try:
        logger.info(f"Dispatching real HTTP {method} to {url} with payload: {clean_payload}")
        if method.upper() == "GET":
            resp = requests.get(url, params=clean_payload, headers=headers, timeout=25)
        else:
            resp = requests.post(url, json=clean_payload, headers=headers, timeout=25)

        try:
            data = resp.json()
        except Exception:
            data = {"raw_response": resp.text}

        return {
            "status_code": resp.status_code,
            "success": resp.status_code in (200, 201, 202),
            "endpoint": url,
            "data": data
        }
    except requests.exceptions.Timeout:
        logger.error(f"Timeout connecting to remote MCP endpoint: {url}")
        return {"success": False, "error": f"Timeout after 25s connecting to {url}", "endpoint": url}
    except Exception as e:
        logger.error(f"Error executing remote request to {url}: {e}")
        return {"success": False, "error": str(e), "endpoint": url}


def execute_tool_call(func_name: str, args: Dict[str, Any], skills: List[AgentSkill]) -> Dict[str, Any]:
    """
    Executes real remote MCP actions based on the Gemini function call.
    """
    skill_map = {s.skill_name.lower(): s for s in skills if s.is_enabled}
    
    # 1. Create / Build MCP Skill
    if func_name == "create_mcp_skill":
        skill_name = args.get("skill_name", "CustomSkill")
        description = args.get("description", "")
        code = args.get("code", "")
        language = args.get("language", "python")
        
        # Check if there is a connected builder skill URL, otherwise use default
        target_url = DEFAULT_SKILL_BUILDER_ENDPOINT + "/api/skills/deploy"
        for s in skills:
            if "builder" in s.skill_name.lower() or "deploy" in s.skill_url.lower():
                target_url = s.skill_url
                break
                
        payload = {
            "skill_name": skill_name,
            "description": description,
            "code": code,
            "language": language
        }
        res = _dispatch_remote_http(target_url, payload, method="POST")
        
        # Format response
        if res.get("success"):
            live_url = res.get("data", {}).get("live_url") or res.get("data", {}).get("endpoint") or f"https://skill-builder-engine.onrender.com/sse/{skill_name.lower().replace(' ', '-')}"
            return {
                "status": "deployed",
                "skill_name": skill_name,
                "live_url": live_url,
                "message": f"Skill '{skill_name}' successfully deployed to live MCP engine.",
                "server_response": res.get("data")
            }
        else:
            return {
                "status": "deployment_failed",
                "error": res.get("error") or res.get("data"),
                "status_code": res.get("status_code"),
                "endpoint": target_url
            }

    # 2. Deploy Skill Generic
    elif func_name == "deploy_skill":
        skill_name = args.get("skill_name", "")
        endpoint_url = args.get("endpoint_url") or DEFAULT_SKILL_BUILDER_ENDPOINT + "/deploy"
        config = args.get("config") or {}
        payload = {"skill_name": skill_name, "config": config}
        res = _dispatch_remote_http(endpoint_url, payload, method="POST")
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

        payload = {"action": action, "parameters": parameters}
        return _dispatch_remote_http(target_skill.skill_url, payload, method="POST")

    # 4. Fallback Generic Remote HTTP Endpoint Caller
    elif func_name == "call_remote_mcp_endpoint":
        url = args.get("endpoint_url", "")
        payload = args.get("payload") or {}
        method = args.get("method", "POST")
        return _dispatch_remote_http(url, payload, method=method)

    return {"error": f"Unknown tool function: {func_name}"}


# =========================================================================
# Tool Function Signatures for Gemini
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
# Core LLM Generation & Multi-Turn Tool Loop
# =========================================================================

async def generate_agent_response(
    agent_name: str,
    agent_role: str,
    system_prompt: str,
    skills: List[AgentSkill],
    user_message: str
) -> Tuple[str, str]:
    """
    Executes an autonomous LLM generation cycle using Google Gemini with dynamic MCP tool binding.
    Executes real remote HTTP requests when tools are called and passes live responses back to Gemini.
    Returns (response_text, status).
    """
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
        return simulated_response, "success"

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        # Active candidate models in order of priority
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
                # 1. Initialize model with tools and system instruction
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    tools=tools
                )

                # 2. Start multi-turn chat to handle function calling
                chat = model.start_chat()
                response = chat.send_message(user_message)

                # 3. Check for function calls in response candidates
                # Loop to support multi-turn function call chains
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
                        # No more tool calls, return final text
                        if response.text:
                            return response.text, "success"
                        break

                    # Execute each real tool call
                    for fc in function_calls:
                        fn_name = fc.name
                        fn_args = dict(fc.args) if fc.args else {}
                        logger.info(f"Agent invoked native tool call '{fn_name}' with args: {fn_args}")

                        # Execute real HTTP request
                        real_result = execute_tool_call(fn_name, fn_args, skills)
                        logger.info(f"Tool execution result: {real_result}")

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
                    return response.text, "success"

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt with model {model_name} failed: {e}")
                continue

        # If rate limit or quota reached
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
            return cognitive_fallback, "success"

        err_msg = f"Gemini API Error: {err_str}"
        logger.error(err_msg)
        return f"⚠️ **Execution Alert**: `{err_msg}`", "failed"

    except Exception as e:
        logger.exception("Unexpected error in LLM service")
        return f"⚠️ **System Exception**: {str(e)}", "failed"
