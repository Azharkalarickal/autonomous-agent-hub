from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Message or test instruction for the autonomous agent")


class ChatResponse(BaseModel):
    response: str
    status: str = "success"
    task_log_id: str
    created_at: datetime


class TaskLogOut(BaseModel):
    id: str
    agent_id: str
    user_input: str
    agent_response: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
