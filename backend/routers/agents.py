from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from storage.db import get_session
from storage.models import Agent

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    model: str = Field(min_length=1)


class AgentOut(BaseModel):
    id: int
    name: str
    system_prompt: str
    voice: str
    model: str

    model_config = {"from_attributes": True}


@router.post("", response_model=AgentOut, status_code=201)
def create_agent(payload: AgentCreate, session: Session = Depends(get_session)) -> Agent:
    agent = Agent(
        name=payload.name,
        system_prompt=payload.system_prompt,
        voice=payload.voice,
        model=payload.model,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, session: Session = Depends(get_session)) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent
