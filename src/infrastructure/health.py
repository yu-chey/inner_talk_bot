import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class HealthChecker:
    
    def __init__(self, database=None, gemini_circuit=None, openai_circuit=None):
        self.database = database
        self.gemini_circuit = gemini_circuit
        self.openai_circuit = openai_circuit
    
    async def check_database(self) -> Dict[str, Any]:
        if not self.database:
            return {"status": "unknown", "error": "Database not initialized"}
        
        if not self.database.db:
            return {"status": "unknown", "error": "Database not connected"}
        
        try:
            await self.database.db.command("ping")
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def check_circuit_breaker(self, circuit, name: str) -> Dict[str, Any]:
        if not circuit:
            return {"status": "unknown", "error": f"{name} circuit breaker not initialized"}
        
        try:
            from src.infrastructure.circuit_breaker import CircuitState
            state = circuit.get_state()
            
            return {
                "status": "healthy" if state == CircuitState.CLOSED else "degraded",
                "state": state.value,
                "failure_count": circuit.failure_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Circuit breaker health check failed for {name}: {e}")
            return {
                "status": "unknown",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        db_status = await self.check_database()
        gemini_status = self.check_circuit_breaker(self.gemini_circuit, "Gemini")
        openai_status = self.check_circuit_breaker(self.openai_circuit, "OpenAI")
        
        all_healthy = (
            db_status.get("status") == "healthy" and
            gemini_status.get("status") in ("healthy", "degraded") and
            openai_status.get("status") in ("healthy", "degraded", "unknown")
        )
        
        return {
            "overall": "healthy" if all_healthy else "degraded",
            "services": {
                "database": db_status,
                "gemini_api": gemini_status,
                "openai_api": openai_status
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def is_healthy(self) -> bool:
        status = await self.get_health_status()
        return status["overall"] == "healthy"

