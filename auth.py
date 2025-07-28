import logging
from typing import Tuple, Optional
from telegram import Update
from telegram.ext import ContextTypes

from utils import log_update

logger = logging.getLogger(__name__)

# ===== USER INFO EXTRACTION =====

def get_user_info(update: Update) -> Tuple[int, str, str]:
    """Extract user info from update"""
    if update.effective_user:
        user = update.effective_user
        return user.id, user.username or "", user.first_name or ""
    return 0, "", ""

# ===== AUTHENTICATION FUNCTIONS =====

async def check_admin_access(content_manager, user_id: int, username: str = "") -> bool:
    """Check if user has admin access"""
    try:
        # Refresh auth cache to get latest data
        await content_manager.refresh_cache()
        
        user_id_str = str(user_id)
        
        logger.info(f"Checking admin access for user_id: {user_id_str}, username: {username}")
        logger.debug(f"Auth cache: {content_manager.auth_cache}")
        
        # Check authorization by user_id or username
        for phone, auth_data in content_manager.auth_cache.items():
            logger.debug(f"Checking phone {phone}: {auth_data}")
            
            # Check by user_id
            if auth_data.get("user_id") == user_id_str:
                logger.info(f"Admin access granted for user {user_id_str} (matched by user_id)")
                return True
            
            # Check by username (if provided and not empty)
            if username and auth_data.get("username") == username:
                logger.info(f"Admin access granted for user {user_id_str} (matched by username: {username})")
                return True
        
        logger.info(f"Admin access denied for user {user_id_str}")
        return False
        
    except Exception as e:
        logger.error(f"Error checking admin access: {e}")
        return False

async def admin_required(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager) -> bool:
    """Check if user is admin, send error message if not"""
    log_update(update, "ADMIN ACCESS CHECK")
    
    user_id, username, first_name = get_user_info(update)
    
    if not await check_admin_access(content_manager, user_id, username):
        # Send access denied message
        error_message = (
            "🔐 Access denied. This command requires admin privileges.\n\n"
            f"**Your Info:**\n"
            f"• User ID: `{user_id}`\n"
            f"• Username: @{username}" if username else f"• Username: Not set\n"
            f"• Name: {first_name}"
        )
        
        await update.effective_message.reply_text(
            error_message,
            parse_mode="Markdown"
        )
        
        logger.warning(f"Admin access denied for user {user_id} (@{username})")
        return False
    
    logger.info(f"Admin access granted for user {user_id} (@{username})")
    return True

async def refresh_auth_cache(content_manager) -> bool:
    """Refresh authentication cache"""
    try:
        success = await content_manager.refresh_cache(force=True)
        if success:
            logger.info("Authentication cache refreshed successfully")
        else:
            logger.warning("Failed to refresh authentication cache")
        return success
    except Exception as e:
        logger.error(f"Error refreshing auth cache: {e}")
        return False

# ===== AUTHORIZATION HELPERS =====

def is_authorized_phone(content_manager, phone_number: str) -> bool:
    """Check if phone number is in authorized list"""
    return content_manager.is_authorized(phone_number)

def get_user_permissions(content_manager, user_id: int, username: str = "") -> dict:
    """Get user permissions and info"""
    permissions = {
        "is_admin": False,
        "user_data": None,
        "phone_number": None
    }
    
    try:
        user_id_str = str(user_id)
        
        # Find user in auth cache
        for phone, auth_data in content_manager.auth_cache.items():
            if (auth_data.get("user_id") == user_id_str or 
                (username and auth_data.get("username") == username)):
                
                permissions["is_admin"] = True
                permissions["user_data"] = auth_data
                permissions["phone_number"] = phone
                break
        
        return permissions
        
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}")
        return permissions

# ===== ADMIN DECORATORS =====

def admin_only(func):
    """Decorator to ensure only admins can access a function"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, *args, **kwargs):
        if not await admin_required(update, context, content_manager):
            return None
        return await func(update, context, content_manager, *args, **kwargs)
    return wrapper

# ===== AUTH VALIDATION =====

async def validate_user_session(content_manager, user_id: int, username: str = "") -> dict:
    """Validate user session and return complete auth info"""
    result = {
        "is_valid": False,
        "is_admin": False,
        "user_info": None,
        "error": None
    }
    
    try:
        # Refresh cache first
        await refresh_auth_cache(content_manager)
        
        # Check admin access
        is_admin = await check_admin_access(content_manager, user_id, username)
        
        result["is_valid"] = True
        result["is_admin"] = is_admin
        
        if is_admin:
            # Get user permissions and data
            permissions = get_user_permissions(content_manager, user_id, username)
            result["user_info"] = permissions
        
        return result
        
    except Exception as e:
        logger.error(f"Error validating user session: {e}")
        result["error"] = str(e)
        return result

# ===== AUTH LOGGING =====

def log_auth_attempt(user_id: int, username: str, success: bool, reason: str = ""):
    """Log authentication attempts"""
    status = "SUCCESS" if success else "FAILED"
    log_msg = f"AUTH {status}: user_id={user_id}, username={username}"
    
    if reason:
        log_msg += f", reason={reason}"
    
    if success:
        logger.info(log_msg)
    else:
        logger.warning(log_msg)

def log_admin_action(user_id: int, username: str, action: str, details: str = ""):
    """Log admin actions for audit trail"""
    log_msg = f"ADMIN ACTION: {action} by user_id={user_id} (@{username})"
    
    if details:
        log_msg += f" - {details}"
    
    logger.info(log_msg)

# ===== AUTH CONSTANTS =====

class AuthLevel:
    """Authentication levels"""
    NONE = 0
    USER = 1
    ADMIN = 2

def get_auth_level(content_manager, user_id: int, username: str = "") -> int:
    """Get user authentication level"""
    try:
        if check_admin_access(content_manager, user_id, username):
            return AuthLevel.ADMIN
        else:
            return AuthLevel.USER
    except:
        return AuthLevel.NONE

# ===== ERROR MESSAGES =====

def get_access_denied_message(user_id: int, username: str, required_level: str = "admin") -> str:
    """Get formatted access denied message"""
    message = f"🔐 Access denied. This action requires {required_level} privileges.\n\n"
    message += "**Your Information:**\n"
    message += f"• User ID: `{user_id}`\n"
    
    if username:
        message += f"• Username: @{username}\n"
    else:
        message += "• Username: Not set\n"
    
    message += "\nPlease contact an administrator if you believe this is an error."
    
    return message