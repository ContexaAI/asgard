
import importlib
from starlette.applications import Starlette
import typer
import asyncio
import importlib.resources as pkg_resources
from pathlib import Path
from typing import List
import os
import shutil


app = typer.Typer(
    name="odinmcp",
    help="OdinMCP CLI",
    add_completion=False,
    no_args_is_help=True,  # Show help if no args provided
)


@app.command(name="web")
def web(app_path: str, params: List[str] = typer.Argument(None)):
    """
    Run a web app with uvicorn. 
    app_path should be in the format 'module:attr', e.g., 'test_app.main:web'
    Any additional CLI arguments will be passed as kwargs to uvicorn.Config, e.g.:
    odinmcp web test_app.main:web --host 0.0.0.0 --port 8080
    """
    print("running web")


@app.command(name="worker")
def worker(app_path: str, params: List[str] = typer.Argument(None)):
    print("running worker")



@app.command(name="sidecar")
def sidecar(app_path: str, params: List[str] = typer.Argument(None)):
    print("running sidecar")

