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
        
        if not message_id:
            logger.error("No message_id provided for edit")
            return None
            
        bot = update.get_bot()
        chat_id = update.effective_chat.id
        
        logger.info(f"Editing message {message_id} in chat {chat_id} with kwargs: {kwargs}")
        
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
        
        if response:
            log_response(response.to_dict(), "SAFE EDIT MESSAGE")
        return response
        
    except TelegramError as e:
        logger.error(f"Failed to edit message {message_id}: {e}")
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
    
    # Extract link from entities (works for text messages, not captions)
    if message.entities:
        components["link"] = extract_link_from_entities(components["text"], message.entities)
    
    # Fallback: extract first URL from text using regex (works for both text and captions)
    if not components["link"] and components["text"]:
        import re
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, components["text"])
        if urls:
            components["link"] = urls[0]
    
    # Clean up: remove the extracted link from text to avoid duplication
    if components["link"] and components["text"]:
        # Remove the link from text (with surrounding whitespace)
        import re
        link_escaped = re.escape(components["link"])
        # Remove link with optional surrounding whitespace/newlines
        components["text"] = re.sub(r'\s*' + link_escaped + r'\s*', '', components["text"])
        # Clean up any trailing whitespace/newlines
        components["text"] = components["text"].strip()
    
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

# ===== STATUS HELPERS =====

async def show_admin_promo_status(update: Update, state: BotState, content_manager) -> BotState:
    """
    Show admin status information for current promo
    Displays: ID, position, status, creation date
    Only shows for admins (verified_at > 0)
    """
    from user_handlers import show_status
    if state.verified_at == 0:
        return state  # Not admin, skip status
    
    # Determine which promos we're working with based on current mode
    if state.show_all_mode:
        target_promos = content_manager.get_all_promos()
        mode_text = "всех"
    else:
        target_promos = content_manager.get_active_promos()
        mode_text = "активных"
    
    if not target_promos:
        return state  # No promos to show status for
    
    # Find current promo and calculate position
    current_index = get_promos_index_from_promo_id(state.promo_id, target_promos)
    position = current_index + 1  # 1-based for display
    total = len(target_promos)
    
    # Get promo details
    promo = target_promos[current_index] if current_index < len(target_promos) else None
    if not promo:
        return state  # Promo not found
    
    # Build status text
    status_emoji = get_status_emoji(promo.get("status", "unknown"))
    status_name = "Вкл." if promo.get("status", "").title() == "Active" else "Выкл."
    created_date = promo.get("created_at", "")[:10] if promo.get("created_at") else "Unknown"
    
    status_text = f"📋 ID {state.promo_id} ({position}/{total} {mode_text}) | {status_emoji} {status_name} | {created_date}"
    
    # Show the status
    return await show_status(update, state, status_text)

    ## ===== STATE MANAGEMENT =====

def get_promos_index_from_promo_id(promo_id: int, promos: List[Dict]) -> int:
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

def get_promo_id_from_promos_index(index: int, promos: List[Dict]) -> int:
    """
    Get promo ID from index in the promos list
    Returns 0 if index is out of bounds
    """
    if not promos or index < 0 or index >= len(promos):
        logger.warning(f"Index {index} out of bounds, returning 0")
        return 0
    
    return promos[index].get("id", 0)

async def check_promos_available(update: Update, state: BotState, content_manager: ContentManager, preserve_position: bool = False) -> BotState:
    """
    Check if there are any promos available and update state accordingly
    For users: only active promos matter
    For admins: 
        - In show_all_mode: all promos
        - In active mode: active promos only, but can see all if no active
    Returns updated state with first available promo_id, or original state if none found
    """
    # Buffer current position before refreshing cache
    current_index = 0
    if preserve_position and state.promo_id > 0:
        if state.show_all_mode:
            current_promos = content_manager.get_all_promos()
        else:
            current_promos = content_manager.get_active_promos()
        
        current_index = get_promos_index_from_promo_id(state.promo_id, current_promos)
    
    await content_manager.refresh_cache()
    
    is_admin = state.verified_at > 0
    
    if is_admin and state.show_all_mode:
        # Admin in "show all" mode
        promos = content_manager.get_all_promos()
        mode_description = "all"
    else:
        # Regular user or admin in "active only" mode
        promos = content_manager.get_active_promos()
        mode_description = "active"

    # Fast path: if we have active promos, use first one
    if promos:
        # Use buffered position (0 for default, actual index for preserve_position)
        if current_index >= len(promos):
            current_index = len(promos) - 1  # Use last promo if out of bounds
        
        target_promo_id = promos[current_index]["id"]
        logger.info(f"Using first promo from {mode_description} promos: ID {target_promo_id}")
        return StateManager.update_state(state, promo_id=target_promo_id)
    
    # No active promos - show appropriate message
    if is_admin:
        if state.show_all_mode:
            # Admin in "show all" mode but no promos at all
            no_promos_text = ("📭 Нет предложений.\n\n"
                             "📝 Создай новое предложение, отправив сообщение с текстом, "
                             "изображением и ссылкой.")

        else:
            all_promos = content_manager.get_all_promos()
            # Admin in "active only" mode but no active promos
            no_promos_text = "📭 Нет активных предложений.\n\n📋 Список всех предложений:"
            for promo in all_promos[:10]:  # Limit to 10 to avoid long messages
                status_emoji = get_status_emoji(promo.get("status", "unknown"))
                promo_text = truncate_text(promo.get("text", "No text"), 40)
                no_promos_text += f"\n{status_emoji} ID {promo.get('id', '?')}: {promo_text}"

            if len(promos) > 10:
                no_promos_text += f"\n... и ещё {len(promos) - 10}"
            no_promos_text += "\n\n💡 Нажми '👁️ Активные' чтобы переключиться на все предложения"

    else:
        # Regular user with no active promos
        no_promos_text = "📭 Нет доступных предложений. Попробуйте позже: /start"
    
    # Show no promos message
    if state.promo_message_id > 0:
        await safe_edit_message(update, message_id=state.promo_message_id, text=no_promos_text)
    else:
        response = await safe_send_message(update, text=no_promos_text)
        if response:
            state = StateManager.update_state(state, promo_message_id=response.message_id)
    
    return state

async def cleanup_chat_messages(update):
    """Clean up all messages in chat before showing new content"""
    bot = update.get_bot()
    chat_id = update.effective_chat.id
    current_msg_id = update.message.message_id
    
    # Delete user's message + try to delete recent bot messages
    # We only ever have 2 bot messages max, so range 1-3 should cover everything
    messages_to_delete = [current_msg_id]  # User's message

    for i in range(1, 3):  # Try 4 messages before user's message
        messages_to_delete.append(current_msg_id - i)
    
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=messages_to_delete)
        logger.info(f"Deleted messages: {messages_to_delete}")
    except TelegramError as e:
        logger.warning(f"Failed to delete some messages: {e}")
        # Individual deletion fallback
        for msg_id in messages_to_delete:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except TelegramError:
                pass  # Ignore individual failures

    ## ===== KEYBOARD MANAGEMENT =====

async def update_keyboard_by_action(update: Update, query, action: str, state: BotState, content_manager: ContentManager):
    from keyboard_builder import KeyboardBuilder
    from user_handlers import show_status
    """Update keyboard based on action"""
    
    # Update promo keyboard to show only back button
    reply_markup = KeyboardBuilder.build_keyboard(action=action, state=state, content_manager=content_manager)
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except TelegramError as e:
        error_msg = handle_telegram_error(e, f"update_keyboard_by_action {action}")
        logger.error(f"Failed to update keyboard: {e}")
        await show_status(update, state, text=f"❌ {error_msg}")