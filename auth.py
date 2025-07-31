import time
import os
import logging
from typing import Tuple
from telegram import Update

from state_manager import StateManager

logger = logging.getLogger(__name__)

def get_verification_ttl() -> int:
    """Get verification TTL based on environment"""
    is_dev = not os.getenv("PORT")  # No PORT means local development
    if is_dev:
        return 600  # 10 minutes for dev/testing
    else:
        return 86400  # 24 hours for production

def is_verification_expired(verified_at: int) -> bool:
    """Check if admin verification has expired"""
    if verified_at == 0:
        return False
    current_time = int(time.time())
    ttl = get_verification_ttl()
    return (current_time - verified_at) >= ttl

async def verify_admin_access(content_manager, user_id: int, username: str = "") -> int:
    """
    Checks admin status and returns verified_at timestamp if successful, else 0.
    Call this on /start or /sign_in, and again only if verification expires.
    """
    if await check_admin_access(content_manager, user_id, username):
        return int(time.time())
    return 0

def get_user_info(update: Update) -> Tuple[int, str, str]:
    """Extract user info from update"""
    if update.effective_user:
        user = update.effective_user
        return user.id, user.username or "", user.first_name or ""
    return 0, "", ""

# ===== AUTHENTICATION FUNCTIONS =====

async def check_admin_access(content_manager, user_id: int, username: str = "") -> bool:
    """Check if user has admin access (by user_id or username in admin db)"""
    try:
        await content_manager.refresh_cache(True)
        user_id_str = str(user_id)
        logger.info(f"Checking admin access for user_id: {user_id_str}, username: {username}")
        logger.debug(f"Auth cache: {content_manager.auth_cache}")
        for phone, auth_data in content_manager.auth_cache.items():
            logger.debug(f"Checking phone {phone}: {auth_data}")
            if auth_data.get("user_id") == user_id_str:
                logger.info(f"Admin access granted for user {user_id_str} (matched by user_id)")
                return True
            if username and auth_data.get("username") == username:
                logger.info(f"Admin access granted for user {user_id_str} (matched by username: {username})")
                return True
        logger.info(f"Admin access denied for user {user_id_str}")
        return False
    except Exception as e:
        logger.error(f"Error checking admin access: {e}")
        return False

async def refresh_admin_verification(state, content_manager, user_id: int, username: str = ""):
    """
    Refresh admin verification if expired
    Returns updated state
    """
    if state.verified_at == 0:
        # Not admin, don't check
        return state
    if not is_verification_expired(state.verified_at):
        # Still valid
        return state
    # Verification expired, re-check
    new_verified_at = await verify_admin_access(content_manager, user_id, username)
    state = StateManager.update_state(state, verified_at = new_verified_at)
    if new_verified_at == 0:
        logger.info(f"Admin access revoked for user {user_id}")
    else:
        logger.info(f"Admin access refreshed for user {user_id}")
    return state

# ===== AUTH LOGGING =====
def log_admin_action(user_id: int, username: str, action: str, details: str = ""):
    """Log admin actions for audit trail"""
    log_msg = f"ADMIN ACTION: {action} by user_id={user_id} (@{username})"
    if details:
        log_msg += f" - {details}"
    logger.info(log_msg)