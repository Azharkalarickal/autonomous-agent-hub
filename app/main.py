import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.models.agent import Agent, AgentSkill
from app.routers.agents import router as agents_router
from app.routers.web import router as web_router


def seed_default_agents_if_empty():
    """Seeds introductory autonomous agents and MCP tool endpoints if database is fresh."""
    db = SessionLocal()
    try:
        existing_count = db.query(Agent).count()
        if existing_count == 0:
            # 1. Procurement Lead
            agent1 = Agent(
                name="Arjun - Procurement Lead",
                role="Procurement Specialist",
                avatar_color="emerald",
                system_prompt=(
                    "You are Arjun, a Senior Procurement & Supply Chain Lead. "
                    "Your mission is to autonomously evaluate vendor quotations, ensure strict SLA compliance, "
                    "optimize BOM (Bill of Materials) costs, and draft purchase agreements with zero discrepancy."
                ),
                is_active=True
            )
            # 2. Civil CAD Engineer
            agent2 = Agent(
                name="Maya - Structural CAD AI",
                role="Civil CAD Engineer",
                avatar_color="cyan",
                system_prompt=(
                    "You are Maya, an autonomous Structural & Civil CAD Engineering agent. "
                    "You inspect engineering schematics, calculate load tolerances, review BIM parameters, "
                    "and interface directly with CAD computational engines to audit technical drawings."
                ),
                is_active=True
            )
            # 3. Security & Compliance Overseer
            agent3 = Agent(
                name="Vigil - SOC Security Lead",
                role="Cybersecurity Sentinel",
                avatar_color="amber",
                system_prompt=(
                    "You are Vigil, an autonomous cybersecurity and SOC analyst agent. "
                    "You monitor real-time threat telemetry, parse CVE databases, perform automated vulnerability "
                    "triaging, and orchestrate incident response playbooks."
                ),
                is_active=True
            )

            db.add_all([agent1, agent2, agent3])
            db.commit()
            db.refresh(agent1)
            db.refresh(agent2)
            db.refresh(agent3)

            # Add sample MCP skills
            skill1 = AgentSkill(
                agent_id=agent1.id,
                skill_name="WhatsApp Vendor MCP",
                skill_url="https://mcp-whatsapp-procure.onrender.com/sse",
                is_enabled=True
            )
            skill2 = AgentSkill(
                agent_id=agent1.id,
                skill_name="ERP Inventory Sync",
                skill_url="https://api.internal-erp.io/mcp/v1",
                is_enabled=True
            )
            skill3 = AgentSkill(
                agent_id=agent2.id,
                skill_name="AutoCAD Geometry Engine",
                skill_url="https://cad-worker-mesh.onrender.com/sse",
                is_enabled=True
            )
            skill4 = AgentSkill(
                agent_id=agent3.id,
                skill_name="SIEM Telemetry Pipeline",
                skill_url="https://siem-mcp.internal.net/events",
                is_enabled=True
            )

            db.add_all([skill1, skill2, skill3, skill4])
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Warning: Failed to seed default data: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables
    Base.metadata.create_all(bind=engine)
    # Seed initial agents for preview
    seed_default_agents_if_empty()
    yield


app = FastAPI(
    title="Autonomous Agent Hub",
    description="Production-ready hub for managing, configuring, and testing autonomous AI agents & MCP endpoints.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files setup
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount Routers
app.include_router(web_router)
app.include_router(agents_router)


@app.get("/api/health", tags=["Health"])
def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "system": "Autonomous Agent Hub",
        "version": "1.0.0",
        "gemini_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here")
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
