import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter(tags=["Web UI"])

templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
index_html_path = os.path.join(templates_dir, "index.html")


@router.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """
    Renders the Autonomous Agent Hub web dashboard.
    """
    if os.path.exists(index_html_path):
        return FileResponse(index_html_path, media_type="text/html")
    return HTMLResponse("<h1>Autonomous Agent Hub - index.html not found</h1>", status_code=404)
