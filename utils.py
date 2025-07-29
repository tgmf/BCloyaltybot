import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

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

# ===== STATELESS STATE MANAGEMENT =====

REQUIRED_STATE_FIELDS = ["idx", "promoId", "verifiedAt", "userId", "statusMessageId", "timestamp", "isList"]

# Updated encode_callback_state function with shorter keys
def encode_callback_state(action: str, **state_vars) -> str:
    """
    Encode action and state variables into callback data with short keys
    Short key mappings:
    - idx -> i (index)
    - promoId -> p (promo ID)  
    - ts -> t (timestamp)
    - statusMessageId -> s (status message ID)
    - userId -> u (user ID)
    """
    # Key mapping for shorter names
    key_mapping = {
        "idx": "i",
        "promoId": "p", 
        "ts": "t",
        "statusMessageId": "s",
        "userId": "u",
        "isList": "l",
        "verifiedAt": "v"
    }
    
    # Use camelCase for action
    def to_camel(s):
        parts = s.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:]) if len(parts) > 1 else s

    action_camel = to_camel(action)
    parts = [action_camel]
    
    for key, value in state_vars.items():
        short_key = key_mapping.get(key, key)
        parts.extend([short_key, str(value)])
    
    callback_data = "_".join(parts)
    
    if len(callback_data) > 64:
        # If too long, use JSON encoding with compression
        state_json = json.dumps({
            "a": action_camel, 
            **{key_mapping.get(k, k): v for k, v in state_vars.items()}
        }, separators=(',', ':'))
        return f"state_{state_json}"[:64]
    
    return callback_data

def decode_callback_state(callback_data: str) -> Tuple[str, Dict[str, Any]]:
    """
    Decode callback data back into action and state variables
    Handles both short keys and full keys for backward compatibility
    """
    # Reverse key mapping
    reverse_mapping = {
        "i": "idx",
        "p": "promoId",
        "t": "ts", 
        "s": "statusMessageId",
        "u": "userId",
        "l": "isList",
        "v": "verifiedAt",
    }
    
    if callback_data.startswith("state_"):
        # JSON encoded state
        try:
            state_json = callback_data[6:]
            data = json.loads(state_json)
            action = data.pop("a")
            # Convert short keys back to full keys
            expanded_state = {}
            for k, v in data.items():
                full_key = reverse_mapping.get(k, k)
                expanded_state[full_key] = v
            return action, expanded_state
        except (json.JSONDecodeError, KeyError):
            return callback_data, {}
    
    # Simple underscore-separated format
    parts = callback_data.split("_")
    if len(parts) < 1:
        return callback_data, {}
    
    action = parts[0]
    state = {}
    i = 1
    while i < len(parts):
        if i + 1 < len(parts):
            key = parts[i]
            value = parts[i + 1]
            
            # Convert short key to full key
            full_key = reverse_mapping.get(key, key)
            
            try:
                if value.isdigit():
                    state[full_key] = int(value)
                elif value.replace(".", "").isdigit():
                    state[full_key] = float(value)
                elif value.lower() in ("true", "false"):
                    state[full_key] = value.lower() == "true"
                else:
                    state[full_key] = value
            except:
                state[full_key] = value
            i += 2
        else:
            i += 1
    
    return action, state

def validate_callback_state(callback_data: str, max_age: int = 3600) -> bool:
    """Validate that callback state is not too old"""
    _, state = decode_callback_state(callback_data)
    # Validate all required fields are present and log missing ones
    missing_fields = [field for field in REQUIRED_STATE_FIELDS if field not in state]
    if missing_fields:
        logger.warning(f"Callback data missing required fields: {missing_fields} | data: {callback_data}")
        return False

def get_current_promo_index_from_callback(callback_data: str) -> int:
    """Extract current promo index from callback data"""
    _, state = decode_callback_state(callback_data)
    return state.get("idx", 0)

# ===== STATELESS KEYBOARD BUILDERS =====


# ===== KEYBOARD BUILDERS (LEGACY - USE STATELESS VERSIONS ABOVE) =====

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

async def safe_edit_message(update: Update, **kwargs) -> bool:
    """Safely edit message with error handling"""
    try:
        if "media" in kwargs:
            response = await update.callback_query.edit_message_media(**kwargs)
        elif "text" in kwargs:
            response = await update.callback_query.edit_message_text(**kwargs)
        else:
            logger.error("No text or media provided for edit")
            return False
        
        if response:
            log_response(response.to_dict(), "SAFE EDIT MESSAGE")
        return True
        
    except TelegramError as e:
        logger.error(f"Failed to edit message: {e}")
        return False

async def safe_send_message(update: Update, **kwargs) -> bool:
    """Safely send message with error handling"""
    try:
        if "photo" in kwargs:
            response = await update.effective_message.reply_photo(**kwargs)
        elif "text" in kwargs:
            response = await update.effective_message.reply_text(**kwargs)
        else:
            logger.error("No text or photo provided for send")
            return False
        
        if response:
            log_response(response.to_dict(), "SAFE SEND MESSAGE")
        return True
        
    except TelegramError as e:
        logger.error(f"Failed to send message: {e}")
        return False

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

# ===== DEBUGGING FUNCTIONS =====

def test_callback_parsing():
    """Test callback data parsing"""
    test_data = "admin_edit_promo_id_1_idx_0_ts_1753678528"
    action, state = decode_callback_state(test_data)
    print(f"Test callback: {test_data}")
    print(f"Parsed action: {action}")
    print(f"Parsed state: {state}")
    return action, state

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