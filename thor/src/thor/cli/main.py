import importlib
from starlette.applications import Starlette
import typer
import asyncio
import importlib.resources as pkg_resources
from pathlib import Path
from typing import List, Optional
import os
import shutil


app = typer.Typer(
    name="odinmcp",
    help="OdinMCP CLI",
    add_completion=False,
    no_args_is_help=True,  # Show help if no args provided
)   


@app.command(name="web")
def web(params: List[str] = typer.Argument(None)):
    """
    Run a web app with uvicorn. 
    Any additional CLI arguments will be passed as kwargs to uvicorn.Config, e.g.:
    odinmcp web --host 0.0.0.0 --port 8080
    """
    import uvicorn
    from thor.web import app    
    
    extra_kwargs = {}
    if params:
        if len(params) % 2 != 0:
            raise typer.BadParameter("Additional arguments must be key value pairs, e.g., --host 0.0.0.0 --port 8080")
        for i in range(0, len(params), 2):
            key = params[i].lstrip('-')
            value = params[i + 1]
            # Try to convert value to int or float if possible
            if value.isdigit():
                value = int(value)
                # Convert numeric strings 1/0 to boolean for flags like "reload"
                if key == "reload":
                    value = bool(value)
            else:
                try:
                    value = float(value)
                except ValueError:
                    pass
            extra_kwargs[key] = value

    # Default port to 80 if not provided
    if "port" not in extra_kwargs:
        extra_kwargs["port"] = 80
    # Default host to 0.0.0.0 if not provided
    if "host" not in extra_kwargs:
        extra_kwargs["host"] = "0.0.0.0"

    # If reload_dir is provided as a single string, convert it to a list as expected by uvicorn.Config
    if isinstance(extra_kwargs.get("reload_dirs"), str):
        extra_kwargs["reload_dirs"] = [extra_kwargs["reload_dirs"]]

    # If reload is requested, uvicorn requires the app to be provided as an import string
    target_app = "thor.web:app" if extra_kwargs.get("reload") else app

    config = uvicorn.Config(
        target_app,
        **extra_kwargs
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())



@app.command(name="worker")
def worker(
    mcp_id: Optional[str] = typer.Argument("mcp", help="The MCP ID for this worker instance. Defaults to 'mcp'."), 
    organization_id: Optional[str] = typer.Argument(None, help="The organization ID for this worker instance. Defaults to None."),
    params: List[str] = typer.Argument(None)
):
    from thor.worker import WorkerManager

    worker_manager = WorkerManager(
        mcp_id=mcp_id,
        organization_id=organization_id,
    )
    celery_app = worker_manager.get_worker()

    # Start the Celery worker, directing it to consume from the queue named after mcp_id.
    # The -Q option specifies the queue.
    base_argv = ["worker", "-Q", worker_manager.get_queue_name()]
    argv = base_argv + (params or [])
    celery_app.worker_main(argv=argv)



@app.command(name="sidecar")
def sidecar(params: List[str] = typer.Argument(None)):
    print("running sidecar")
