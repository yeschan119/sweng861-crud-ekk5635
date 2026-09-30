"""Health probes: /health and /health/ready check the database, /health/live does not.

Unauthenticated on purpose: a load balancer or a container runtime has no login.
"""

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from db import get_probe_engine

logger = logging.getLogger("sweng861.health")

router = APIRouter(prefix="/health", tags=["health"])

UP = "UP"
DOWN = "DOWN"


def is_database_reachable(engine: Engine) -> bool:
    """True when a fresh connection answers a trivial query within the connect timeout."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # The exception type names the failure without echoing a connection string.
        logger.warning("database health check failed: %s", type(exc).__name__)
        return False
    return True


@router.get("")
@router.get("/ready")
def readiness(engine: Engine = Depends(get_probe_engine)) -> JSONResponse:
    """Ready to serve traffic: 200 when the database is reachable, 503 when not."""
    if is_database_reachable(engine):
        return JSONResponse({"status": UP, "db": UP}, status_code=status.HTTP_200_OK)
    return JSONResponse(
        {"status": DOWN, "db": DOWN}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )


@router.get("/live")
def liveness() -> dict[str, str]:
    """The process is running and can answer HTTP. Touches nothing else."""
    return {"status": UP}
