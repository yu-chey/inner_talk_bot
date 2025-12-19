from .menu_callbacks import router as menu_router
from .session_callbacks import router as session_router
from .test_callbacks import router as test_router
from .portrait_callbacks import router as portrait_router
from .admin_callbacks import router as admin_router
from .onboarding_callbacks import router as onboarding_router
from .profile_callbacks import router as profile_router

__all__ = [
    "menu_router",
    "session_router",
    "test_router",
    "portrait_router",
    "admin_router",
    "onboarding_router",
    "profile_router",
]

