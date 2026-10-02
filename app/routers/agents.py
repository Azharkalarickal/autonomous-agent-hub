from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.agent import Agent, AgentSkill
from app.models.task_log import TaskLog
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentOut,
    AgentSkillCreate,
    AgentSkillOut,
)
from app.schemas.chat import ChatRequest, ChatResponse, TaskLogOut
from app.services.llm_service import generate_agent_response

router = APIRouter(prefix="/api/agents", tags=["Agents"])


# ==========================================
# Agents CRUD
# ==========================================

@router.get("/", response_model=List[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    """
    List all autonomous agents with nested skills and task log counts.
    """
    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()
    
    # Calculate log count for each agent
    results = []
    for agent in agents:
        log_count = db.query(func.count(TaskLog.id)).filter(TaskLog.agent_id == agent.id).scalar() or 0
        agent_out = AgentOut.model_validate(agent)
        agent_out.log_count = log_count
        results.append(agent_out)
        
    return results


@router.post("/", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(agent_in: AgentCreate, db: Session = Depends(get_db)):
    """
    Register and deploy a new autonomous agent persona.
    """
    new_agent = Agent(
        name=agent_in.name.strip(),
        role=agent_in.role.strip(),
        avatar_color=agent_in.avatar_color.strip() or "emerald",
        system_prompt=agent_in.system_prompt.strip(),
        is_active=agent_in.is_active
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    
    agent_out = AgentOut.model_validate(new_agent)
    agent_out.log_count = 0
    return agent_out


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """
    Retrieve single agent details including skills and log metrics.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with ID '{agent_id}' not found"
        )
    log_count = db.query(func.count(TaskLog.id)).filter(TaskLog.agent_id == agent.id).scalar() or 0
    agent_out = AgentOut.model_validate(agent)
    agent_out.log_count = log_count
    return agent_out


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: str, agent_in: AgentUpdate, db: Session = Depends(get_db)):
    """
    Update an agent's configuration, persona, role, or active status.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with ID '{agent_id}' not found"
        )

    if agent_in.name is not None:
        agent.name = agent_in.name.strip()
    if agent_in.role is not None:
        agent.role = agent_in.role.strip()
    if agent_in.avatar_color is not None:
        agent.avatar_color = agent_in.avatar_color.strip()
    if agent_in.system_prompt is not None:
        agent.system_prompt = agent_in.system_prompt.strip()
    if agent_in.is_active is not None:
        agent.is_active = agent_in.is_active

    db.commit()
    db.refresh(agent)
    
    log_count = db.query(func.count(TaskLog.id)).filter(TaskLog.agent_id == agent.id).scalar() or 0
    agent_out = AgentOut.model_validate(agent)
    agent_out.log_count = log_count
    return agent_out


@router.delete("/{agent_id}", status_code=status.HTTP_200_OK)
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    """
    Delete an agent along with its connected skills and task logs.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with ID '{agent_id}' not found"
        )
    db.delete(agent)
    db.commit()
    return {"message": f"Agent '{agent.name}' ({agent_id}) successfully removed", "id": agent_id}


# ==========================================
# Skills Management (MCP Endpoints)
# ==========================================

@router.post("/{agent_id}/skills", response_model=AgentSkillOut, status_code=status.HTTP_201_CREATED)
def attach_skill(agent_id: str, skill_in: AgentSkillCreate, db: Session = Depends(get_db)):
    """
    Attach a new remote MCP tool/skill endpoint to the designated agent.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with ID '{agent_id}' not found"
        )

    new_skill = AgentSkill(
        agent_id=agent_id,
        skill_name=skill_in.skill_name.strip(),
        skill_url=skill_in.skill_url.strip(),
        is_enabled=skill_in.is_enabled
    )
    db.add(new_skill)
    db.commit()
    db.refresh(new_skill)
    return new_skill


@router.delete("/{agent_id}/skills/{skill_id}", status_code=status.HTTP_200_OK)
def detach_skill(agent_id: str, skill_id: str, db: Session = Depends(get_db)):
    """
    Detach an MCP skill from an agent.
    """
    skill = db.query(AgentSkill).filter(
        AgentSkill.id == skill_id,
        AgentSkill.agent_id == agent_id
    ).first()

    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill with ID '{skill_id}' for agent '{agent_id}' not found"
        )

    db.delete(skill)
    db.commit()
    return {"message": f"Skill '{skill.skill_name}' successfully detached", "id": skill_id}


@router.patch("/{agent_id}/skills/{skill_id}/toggle", response_model=AgentSkillOut)
def toggle_skill(agent_id: str, skill_id: str, db: Session = Depends(get_db)):
    """
    Toggle the active/disabled status of a specific skill.
    """
    skill = db.query(AgentSkill).filter(
        AgentSkill.id == skill_id,
        AgentSkill.agent_id == agent_id
    ).first()

    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill with ID '{skill_id}' for agent '{agent_id}' not found"
        )

    skill.is_enabled = not skill.is_enabled
    db.commit()
    db.refresh(skill)
    return skill


# ==========================================
# Chat & Task Logs
# ==========================================

@router.get("/{agent_id}/logs", response_model=List[TaskLogOut])
def get_agent_logs(agent_id: str, limit: int = 50, db: Session = Depends(get_db)):
    """
    Fetch execution task logs and chat history for the agent.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with ID '{agent_id}' not found"
        )
        
    logs = (
        db.query(TaskLog)
        .filter(TaskLog.agent_id == agent_id)
        .order_by(TaskLog.created_at.asc())
        .limit(limit)
        .all()
    )
    return logs


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat_with_agent(
    agent_id: str,
    chat_in: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Execute a test conversation/task with the autonomous agent.
    Injects system instructions and attached MCP capabilities into Gemini LLM.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with ID '{agent_id}' not found"
        )

    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{agent.name}' is currently inactive. Please toggle active status to test."
        )

    # Generate response via LLM service
    response_text, status_str = await generate_agent_response(
        agent_name=agent.name,
        agent_role=agent.role,
        system_prompt=agent.system_prompt,
        skills=agent.skills,
        user_message=chat_in.message
    )

    # Record interaction in TaskLog
    task_log = TaskLog(
        agent_id=agent_id,
        user_input=chat_in.message,
        agent_response=response_text,
        status=status_str
    )
    db.add(task_log)
    db.commit()
    db.refresh(task_log)

    return ChatResponse(
        response=task_log.agent_response,
        status=task_log.status,
        task_log_id=task_log.id,
        created_at=task_log.created_at
    )
