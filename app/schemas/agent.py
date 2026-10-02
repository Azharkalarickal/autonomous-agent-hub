from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==========================================
# Agent Skill Schemas
# ==========================================

class AgentSkillBase(BaseModel):
    skill_name: str = Field(..., min_length=1, max_length=100, description="Name of the MCP skill or tool")
    skill_url: str = Field(..., min_length=1, max_length=500, description="Remote SSE or HTTP URL of the MCP endpoint")
    is_enabled: bool = Field(default=True, description="Whether this skill is active")


class AgentSkillCreate(AgentSkillBase):
    pass


class AgentSkillUpdate(BaseModel):
    skill_name: Optional[str] = Field(None, min_length=1, max_length=100)
    skill_url: Optional[str] = Field(None, min_length=1, max_length=500)
    is_enabled: Optional[bool] = None


class AgentSkillOut(AgentSkillBase):
    id: str
    agent_id: str
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Agent Schemas
# ==========================================

class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150, description="Agent Display Name")
    role: str = Field(..., min_length=1, max_length=100, description="Agent Specialization / Role Title")
    avatar_color: str = Field(default="emerald", description="Tailwind color badge token (e.g., emerald, cyan, violet, amber)")
    system_prompt: str = Field(..., min_length=1, description="System persona and behavioral instructions")
    is_active: bool = Field(default=True, description="Fleet active status")


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    role: Optional[str] = Field(None, min_length=1, max_length=100)
    avatar_color: Optional[str] = None
    system_prompt: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


class AgentOut(AgentBase):
    id: str
    created_at: datetime
    skills: List[AgentSkillOut] = []
    log_count: int = 0

    model_config = ConfigDict(from_attributes=True)
