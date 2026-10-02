import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(150), nullable=False)
    role = Column(String(100), nullable=False)
    avatar_color = Column(String(50), default="emerald")
    system_prompt = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)

    # Relationships
    skills = relationship(
        "AgentSkill",
        back_populates="agent",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AgentSkill.added_at"
    )
    logs = relationship(
        "TaskLog",
        back_populates="agent",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="desc(TaskLog.created_at)"
    )


class AgentSkill(Base):
    __tablename__ = "agent_skills"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    agent_id = Column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_name = Column(String(100), nullable=False)
    skill_url = Column(String(500), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime, default=get_utc_now, nullable=False)

    # Relationship back to Agent
    agent = relationship("Agent", back_populates="skills")
