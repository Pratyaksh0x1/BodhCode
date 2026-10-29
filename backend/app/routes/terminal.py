"""Integrated terminal execution routes for BodhCode Studio."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth.deps import get_current_user, require_csrf_header
from app.config import get_settings
from app.db import get_session
from app.models.repo import Repo
from app.models.user import User

router = APIRouter(
    prefix="/repos",
    tags=["Terminal"],
    dependencies=[Depends(require_csrf_header)],
)


class TerminalExecRequest(BaseModel):
    """Terminal execution payload."""

    command: str = Field(
        min_length=1, max_length=2000, description="Shell command line to execute."
    )


class TerminalExecResponse(BaseModel):
    """Terminal command execution result."""

    stdout: str
    stderr: str
    exit_code: int
    cwd: str
    duration_ms: float


@router.post("/{repo_id}/terminal/exec", response_model=TerminalExecResponse)
async def exec_terminal_command(
    repo_id: int,
    payload: TerminalExecRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> TerminalExecResponse:
    """Execute a CLI command inside the repository workspace environment."""
    repo = session.exec(
        select(Repo).where(Repo.id == repo_id, Repo.user_id == current_user.id)
    ).first()

    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    settings = get_settings()
    repo_src = (
        Path(settings.DATA_DIR)
        / "repos"
        / repo.owner
        / repo.name
        / (repo.commit_sha or "HEAD")
        / "src"
    )

    working_dir = repo_src if repo_src.exists() else Path(settings.DATA_DIR)
    working_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    try:
        proc = await asyncio.create_subprocess_shell(
            payload.command,
            cwd=str(working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CI": "true", "TERM": "xterm-256color"},
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        duration_ms = (time.time() - start_time) * 1000

        return TerminalExecResponse(
            stdout=stdout_bytes.decode(errors="replace")[:65536],
            stderr=stderr_bytes.decode(errors="replace")[:65536],
            exit_code=proc.returncode if proc.returncode is not None else -1,
            cwd=str(working_dir),
            duration_ms=round(duration_ms, 2),
        )
    except TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return TerminalExecResponse(
            stdout="",
            stderr="Error: Command timed out after 30 seconds.",
            exit_code=124,
            cwd=str(working_dir),
            duration_ms=30000.0,
        )
    except Exception as exc:
        return TerminalExecResponse(
            stdout="",
            stderr=f"Execution error: {exc}",
            exit_code=1,
            cwd=str(working_dir),
            duration_ms=(time.time() - start_time) * 1000,
        )
