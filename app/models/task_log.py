import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    agent_id = Column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_input = Column(Text, nullable=False)
    agent_response = Column(Text, nullable=False)
    status = Column(String(20), default="success", nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)

    # Relationship back to Agent
    agent = relationship("Agent", back_populates="logs")
