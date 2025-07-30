import logging
import json
import time
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from telegram import Update
from telegram.error import TelegramError

from content_manager import ContentManager
from state_manager import BotState, StateManager

logger = logging.getLogger(__name__)

# ===== LOGGING UTILITIES =====

def log_update(update: Update, description: str = ""):
    """Log detailed information about an Update object"""
    try:
        logger.info(f"=== {description} UPDATE LOG ===")
        logger.info(f"Update ID: {update.update_id}")
        
        # Log message details
        if update.message:
            msg = update.message
            logger.info(f"MESSAGE:")
            logger.info(f"  Message ID: {msg.message_id}")
            logger.info(f"  From: {msg.from_user.id} (@{msg.from_user.username}) - {msg.from_user.first_name}")
            logger.info(f"  Chat: {msg.chat.id} ({msg.chat.type})")
            logger.info(f"  Text: {msg.text}")
            logger.info(f"  Caption: {msg.caption}")
            if msg.photo:
                logger.info(f"  Photo: {len(msg.photo)} sizes, largest: {msg.photo[-1].file_id}")
            if msg.entities:
                logger.info(f"  Entities: {[(e.type, e.offset, e.length) for e in msg.entities]}")
        
        # Log callback query details
        if update.callback_query:
            cb = update.callback_query
            logger.info(f"CALLBACK QUERY:")
            logger.info(f"  Query ID: {cb.id}")
            logger.info(f"  From: {cb.from_user.id} (@{cb.from_user.username}) - {cb.from_user.first_name}")
            logger.info(f"  Data: {cb.data}")
            if cb.message:
                logger.info(f"  Message ID: {cb.message.message_id}")
                logger.info(f"  Message Text/Caption: {cb.message.text or cb.message.caption}")
        
        logger.info(f"=== END UPDATE LOG ===")
        
    except Exception as e:
        logger.error(f"Error logging update: {e}")

def log_response(response_data: dict, description: str = ""):
    """Log detailed response information"""
    try:
        logger.info(f"=== {description} RESPONSE LOG ===")
        logger.info(f"Response: {json.dumps(response_data, indent=2, default=str)}")
        logger.info(f"=== END RESPONSE LOG ===")
    except Exception as e:
        logger.error(f"Error logging response: {e}")

# ===== MESSAGE FORMATTING =====

def format_promo_text(promo: Dict, include_status: bool = False) -> str:
    """Format promo text with optional status indicator"""
    text = promo.get("text", "No text")
    
    if include_status:
        status_emoji = get_status_emoji(promo.get("status", "unknown"))
        promo_id = promo.get("id", "Unknown")
        promo_order = promo.get("order", 0)
        text = f"{status_emoji} *ID {promo_id}* (Order: {promo_order})\n{text}"
    
    return text

def truncate_text(text: str, max_length: int = 100) -> str:
    """Safely truncate text to specified length"""
    if not text:
        return "No text"
    
    text_str = str(text)
    if len(text_str) <= max_length:
        return text_str
    
    return text_str[:max_length] + "..."

def extract_link_from_entities(text: str, entities: List) -> str:
    """Extract URL from message entities"""
    if not text or not entities:
        return ""
    
    for entity in entities:
        if entity.type == "url":
            return text[entity.offset:entity.offset + entity.length]
    
    return ""

def get_status_emoji(status: str) -> str:
    """Get emoji for promo status"""
    emoji_map = {
        "active": "✅",
        "draft": "📄", 
        "inactive": "❌"
    }
    return emoji_map.get(status, "❓")

# ===== ERROR HANDLING =====

async def safe_edit_message(update: Update, **kwargs):
    """Safely edit message with error handling - returns message object or None"""
    try:
        message_id = kwargs.pop("message_id", None)
        
        if update.callback_query:
            # Editing via callback query (button click)
            if "media" in kwargs:
                response = await update.callback_query.edit_message_media(**kwargs)
            elif "text" in kwargs:
                response = await update.callback_query.edit_message_text(**kwargs)
            else:
                logger.error("No text or media provided for edit")
                return None
        elif message_id:
            # Editing via bot.edit_message (when no callback query)
            bot = update.get_bot()
            chat_id = update.effective_chat.id
            
            if "media" in kwargs:
                response = await bot.edit_message_media(
                    chat_id=chat_id, 
                    message_id=message_id, 
                    **kwargs
                )
            elif "text" in kwargs:
                response = await bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id, 
                    **kwargs
                )
            else:
                logger.error("No text or media provided for edit")
                return None
        else:
            logger.error("No callback query or message_id provided for edit")
            return None
        
        if response:
            log_response(response.to_dict(), "SAFE EDIT MESSAGE")
        return response
        
    except TelegramError as e:
        logger.error(f"Failed to edit message: {e}")
        return None

async def safe_send_message(update: Update, **kwargs):
    """Safely send message with error handling - returns message object or None"""
    try:
        if "photo" in kwargs:
            response = await update.effective_message.reply_photo(**kwargs)
        elif "text" in kwargs:
            response = await update.effective_message.reply_text(**kwargs)
        else:
            logger.error("No text or photo provided for send")
            return None
        
        if response:
            log_response(response.to_dict(), "SAFE SEND MESSAGE")
        return response  # Return the actual message object
        
    except TelegramError as e:
        logger.error(f"Failed to send message: {e}")
        return None

def handle_telegram_error(error: TelegramError, context: str = "") -> str:
    """Handle telegram errors and return user-friendly message"""
    error_msg = str(error)
    
    if "message is not modified" in error_msg.lower():
        return "Content is already up to date"
    elif "message to edit not found" in error_msg.lower():
        return "Message not found"
    elif "bad request" in error_msg.lower():
        return "Invalid request"
    else:
        logger.error(f"Telegram error in {context}: {error}")
        return "An error occurred. Please try again."

# ===== DATA EXTRACTION =====

def extract_message_components(message) -> Dict[str, str]:
    """Extract text, image, and link from message"""
    components = {
        "text": "",
        "image_file_id": "",
        "link": ""
    }
    
    # Get text
    components["text"] = message.text or message.caption or ""
    
    # Get image file_id
    if message.photo:
        components["image_file_id"] = message.photo[-1].file_id
    
    # Extract link from entities
    if message.entities:
        components["link"] = extract_link_from_entities(components["text"], message.entities)
    
    return components

def validate_promo_data(promo: Dict) -> bool:
    """Validate promo data structure"""
    required_fields = ["id", "text", "order", "status"]
    
    if not isinstance(promo, dict):
        return False
    
    for field in required_fields:
        if field not in promo:
            logger.error(f"Missing required field: {field}")
            return False
    
    return True

# ===== FORMATTING HELPERS =====

def format_admin_summary(promos: List[Dict], max_count: int = 10) -> str:
    """Format admin summary of promos"""
    if not promos:
        return "📭 No promos found."
    
    summary_lines = ["📋 **All Promos:**\n"]
    
    for promo in promos[:max_count]:
        if not validate_promo_data(promo):
            continue
            
        status_emoji = get_status_emoji(promo.get("status"))
        promo_text = truncate_text(promo.get("text"), 50)
        summary_lines.append(f"{status_emoji} **ID {promo.get('id')}**: {promo_text}")
    
    if len(promos) > max_count:
        summary_lines.append(f"\n... and {len(promos) - max_count} more")
    
    return "\n".join(summary_lines)

def format_promo_preview(pending_data: Dict, edit_id: Optional[int] = None) -> str:
    """Format promo preview text (shows exactly how it will look)"""
    # Just return the text as-is, no preview prefix
    preview_text = pending_data.get('text', '')
    
    # Don't add any preview indicators - show exactly as it will appear
    return preview_text

    ## ===== STATE MANAGEMENT =====

def get_promos_index_from_promoId(promo_id: int, promos: List[Dict]) -> int:
    """
    Find the index of a promo by its ID in the promos list
    Returns 0 if promo not found (fallback to first promo)
    """
    if not promos:
        return 0
    
    for i, promo in enumerate(promos):
        if promo.get("id") == promo_id:
            return i
    
    # Promo not found, return 0 as fallback
    logger.warning(f"Promo ID {promo_id} not found in promos list, falling back to index 0")
    return 0

def get_promoId_from_promos_index(index: int, promos: List[Dict]) -> int:
    """
    Get promo ID from index in the promos list
    Returns 0 if index is out of bounds
    """
    if not promos or index < 0 or index >= len(promos):
        logger.warning(f"Index {index} out of bounds, returning 0")
        return 0
    
    return promos[index].get("id", 0)

async def check_promos_available(update, state, promos: List[Dict] = None) -> BotState:
    """
    Check if there are any active promos available
    Returns True if at least one active promo exists
    """
    if promos is None:
        promos = ContentManager.get_active_promos()
    if promos:
        for promo in promos:
            if promo.get("status") == "active":
                logger.info(f"Active promo found: ID {promo.get('id')}")
                state = StateManager.update_state(state, promo_id=promo.get("id", 0))
                return state

    logger.info("📭 No promos available at the moment.")
    no_promos_text = "📭 No promos available at the moment. Try again later: /start"
    if state.verifiedAt > 0:  # Is admin
        no_promos_text += "\n\n📝 As an admin, you can create promos by sending a message with text, image, and link."
    if state.promoMessageId > 0:
        # If we have a promo message, edit it to show no promos
        await safe_edit_message(update, message_id=state.promoMessageId, text=no_promos_text)
    else:
        await safe_send_message(update, text=no_promos_text)
    return None