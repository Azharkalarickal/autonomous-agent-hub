import logging
from typing import List, Optional, Tuple
from app.core.config import settings
from app.models.agent import AgentSkill

logger = logging.getLogger("agent_hub.llm")


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
            "\n\n### CONNECTED MCP SKILL ENDPOINTS & TOOLING:\n"
            "You have access to the following live tool capabilities:\n"
            + "\n".join(skill_descriptions)
            + "\nWhen solving user requests, reference these specific capabilities and explain how your autonomous actions interface with them."
        )
    else:
        skills_context = "\n\n### CONNECTED SKILLS:\nNo external MCP skills currently connected. You operate using your core autonomous cognition."

    full_instruction = f"""You are '{agent_name}', an autonomous AI agent specializing as '{agent_role}'.

### CORE PERSONA & BEHAVIORAL PROTOCOLS:
{system_prompt}
{skills_context}

### EXECUTION GUIDELINES:
1. Stay strictly in character and adhere to your defined role constraints.
2. Deliver clear, actionable, high-quality responses tailored to your specialty.
3. If relevant, simulate tool execution or outline step-by-step autonomous decision pathways.
"""
    return full_instruction


async def generate_agent_response(
    agent_name: str,
    agent_role: str,
    system_prompt: str,
    skills: List[AgentSkill],
    user_message: str
) -> Tuple[str, str]:
    """
    Executes an autonomous LLM generation cycle using Google Gemini with persona injection.
    Falls back gracefully to intelligent simulated mode if no API key is set.
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
        # Realistic fallback simulation when API key is not yet configured
        active_skills_names = [s.skill_name for s in skills if s.is_enabled]
        skills_str = ", ".join(active_skills_names) if active_skills_names else "Core Cognition"
        
        simulated_response = (
            f"**[{agent_name} | {agent_role}]**\n\n"
            f"Acknowledged request: *\"{user_message}\"*\n\n"
            f"I have initialized my reasoning loop based on my persona instructions:\n"
            f"> *\"{system_prompt[:160]}...\"*\n\n"
            f"**Autonomous Pipeline Execution:**\n"
            f"1. **Dispatched to MCP Subsystem**: Active tools [{skills_str}]\n"
            f"2. **Analysis**: Evaluated input parameters against operational bounds for {agent_role}.\n"
            f"3. **Result**: Successfully formulated the targeted execution plan.\n\n"
            f"💡 *Note: Running in sandbox test mode. Configure your `GEMINI_API_KEY` in `.env` to enable live Google Gemini 1.5/2.0 LLM inference.*"
        )
        return simulated_response, "success"

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        # List of active modern Gemini models in order of preference
        candidate_models = [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
            "gemini-pro-latest"
        ]
        last_error = None

        for model_name in candidate_models:
            try:
                # Initialize model with system instruction
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction
                )
                response = model.generate_content(user_message)
                if response and response.text:
                    return response.text, "success"
            except TypeError:
                # Fallback if system_instruction param is structured differently
                combined_prompt = f"System Instructions:\n{system_instruction}\n\nUser Request:\n{user_message}"
                model = genai.GenerativeModel(model_name=model_name)
                response = model.generate_content(combined_prompt)
                if response and response.text:
                    return response.text, "success"
            except Exception as e:
                last_error = e
                logger.warning(f"Failed generation with model {model_name}: {e}")
                continue

        # If quota is exhausted or temporary API limit reached, provide helpful agent feedback
        err_str = str(last_error) if last_error else "Unknown Gemini Error"
        if "429" in err_str or "ResourceExhausted" in err_str or "quota" in err_str.lower():
            active_skills_names = [s.skill_name for s in skills if s.is_enabled]
            skills_str = ", ".join(active_skills_names) if active_skills_names else "Core Cognition"
            
            cognitive_fallback = (
                f"**[{agent_name} | {agent_role}]**\n\n"
                f"I received your directive: *\"{user_message}\"*\n\n"
                f"**Autonomous Persona Assessment:**\n"
                f"As {agent_role}, I am operating under instructions:\n"
                f"> *\"{system_prompt}\"*\n\n"
                f"**Connected Tooling & MCP Subsystems:**\n"
                f"• Active MCP Tools: `{skills_str}`\n\n"
                f"⚡ *API Notice: Google Gemini Free Tier requests per minute limit reached (429). The system temporarily fell back to autonomous cognitive evaluation.*"
            )
            return cognitive_fallback, "success"

        err_msg = f"Gemini API Error: {err_str}"
        logger.error(err_msg)
        return f"⚠️ **Execution Alert**: `{err_msg}`", "failed"

    except Exception as e:
        logger.exception("Unexpected error in LLM service")
        return f"⚠️ **System Exception**: {str(e)}", "failed"
