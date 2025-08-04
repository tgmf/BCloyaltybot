import logging
import os
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# Import auth functions
from auth import get_user_info, refresh_admin_verification
# Import stateless utilities (now in utils)
from keyboard_builder import KeyboardBuilder
from state_manager import BotState, StateManager
from utils import (
    check_promos_available, cleanup_chat_messages, get_promo_id_from_promos_index, get_status_emoji, log_update, safe_edit_message, safe_send_message, get_promos_index_from_promo_id, show_admin_promo_status
)

logger = logging.getLogger(__name__)

# ===== MAIN USER COMMANDS =====

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Start command - shows promos for everyone"""
    log_update(update, "START COMMAND")
    
    user_id, username, first_name = get_user_info(update)
    
    await cleanup_chat_messages(update)
    
    chat_id = update.effective_chat.id
    bot = update.get_bot()
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    
    logger.info(f"User {user_id} (@{username}) started bot")
    
    # Create initial state with status message ID
    state = StateManager.create_state(
        promo_id=0,  # Will be updated after showing first promo
        verified_at=1,  # Will be updated after verification
        status_message_id=0, # Will be set when status is sent
        promo_message_id=0  # Will be set when promo is sent
    )
    
    # Check admin status and get verified_at timestamp
    state = await refresh_admin_verification(state, content_manager, user_id, username)
    
    if state.verified_at == 0:
        welcome_text = f"🎉 Привет, {first_name},\nдля вас сегодня доступно {len(content_manager.get_active_promos())} предложений!"
        # Send welcome message and capture message ID
        state = await show_status(update, state, text=welcome_text)

    init_text = f"🎉 Добро пожаловать в Business Club, {first_name}!"

    # Show initial status message
    response = await safe_send_message(update, text=init_text)
    promo_message_id = response.message_id if response else 0

    state = StateManager.update_state(state, promo_message_id=promo_message_id)
    
    if state.verified_at > 0:
        welcome_text = f"🎉 Привет, {first_name}, доступно {len(content_manager.get_all_promos())} предложений (активно: {len(content_manager.get_active_promos())})"
        welcome_text += f"\nЧтобы добавить новое предложение отправь его в чат"
        # Send welcome message and capture message ID
        state = await show_status(update, state, text=welcome_text)
    
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    state_with_promo = await check_promos_available(update, state, content_manager)
    

    if not state_with_promo:
        logger.error("No valid promo found.")
        return
    
    # Show first promo with state
    await show_promo(update, context, content_manager, "start", state_with_promo)
    

# ===== PROMO DISPLAY =====

async def show_status(update: Update, state, text, parse_mode="Markdown") -> BotState:
    """
    Post or update status message based on current state
    If state.status_message_id exists, edit it; otherwise, send a new message
    Returns updated state with status_message_id set
    """
    if state.status_message_id:
        logger.info(f"SHOW STATUS editing existing status message ID: {state.status_message_id}")
        await safe_edit_message(update, text=text, parse_mode=parse_mode, message_id=state.status_message_id)
    else:
        response = await safe_send_message(update, text=text, parse_mode=parse_mode)
        if response:
            state = StateManager.update_state(state, status_message_id=response.message_id)
        else:
            logger.error("Failed to send status message")

    return state

async def show_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, action, state: BotState) -> BotState:
    """Display promo using state management"""
    promos = content_manager.get_all_promos()
    
    # Find the promo by ID
    promo = next((p for p in promos if p["id"] == state.promo_id), None)
    if not promo:
        await show_status(update, state, "❌ Не удалось найти это предложение.")
        return state
    
    # Extract link for keyboard
    promo_link = promo.get("link", "")
    
    # Build keyboard with current state and link
    reply_markup = KeyboardBuilder.build_keyboard(action, state, promo_link, content_manager)

    # Validate and clean image_file_id
    image_file_id = promo.get("image_file_id", "")
    has_image = image_file_id and image_file_id.strip() and image_file_id != "None"
    # Log the image status for debugging
    logger.info(f"Promo {state.promo_id} image status: '{image_file_id}' -> has_image: {has_image}")
    
    # If no image, use bot's description picture
    if not has_image:
        # Ensure bot image is cached
        default_image = os.getenv("DEFAULT_IMAGE_FILE_ID")
        if default_image:
            image_file_id = default_image
            has_image = True
            logger.info(f"Using default image for promo {state.promo_id}")
    
    
    if state.promo_message_id:
        # Always use edit_message_media since we always have an image now
        message_kwargs = {
            "media": InputMediaPhoto(media=image_file_id, caption=promo["text"], parse_mode="Markdown"),
            "reply_markup": reply_markup,
            "message_id": state.promo_message_id
        }
        
        logger.info(f"EDITING MESSAGE ID: {state.promo_message_id}")
        response = await safe_edit_message(update, **message_kwargs)
        
        if response:
            # Edit was successful
            return state
        else:
            logger.error("Failed to edit promo message")
            await show_status(update, state, "❌ Не удалось обновить чат")
            return state
    else:
        # Send new message - always use photo format since we always have an image
        message_kwargs = {
            "photo": image_file_id,
            "caption": promo["text"],
            "reply_markup": reply_markup,
            "parse_mode": "Markdown"
        }
        
        logger.info("SENDING NEW PROMO MESSAGE")
        response = await safe_send_message(update, **message_kwargs)
        
        if response:
            logger.info(f"NEW PROMO MESSAGE ID: {response.message_id}")
            return StateManager.update_state(state, promo_message_id=response.message_id)
        else:
            logger.error("Failed to send promo message")
            await show_status(update, state, "❌ Не удалось отправить сообщение")
            return state

# ===== NAVIGATION HANDLERS =====

async def navigation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Handle navigation buttons (prev/next) with stateless approach"""
    log_update(update, "NAVIGATION")
    query = update.callback_query
    await query.answer()
    
    # Decode state from callback data
    action, state = StateManager.decode_callback_data(query.data)
    
    # Check for available promos
    if not await check_promos_available(update, state, content_manager):
        return
    
    # Determine which promos to navigate through based on state
    is_admin = state.verified_at > 0
    
    if is_admin and state.show_all_mode:
        # Admin in "show all" mode - navigate through all promos
        target_promos = content_manager.get_all_promos()
        logger.info("Navigation: using ALL promos (admin show_all_mode)")
    else:
        # Regular user or admin in "active only" mode - navigate through active promos
        target_promos = content_manager.get_active_promos()
        logger.info("Navigation: using ACTIVE promos only")
    
    # Find current index from promo_id
    current_index = get_promos_index_from_promo_id(state.promo_id, target_promos)

    # Calculate new index based on action
    if action == "prev":
        new_index = (current_index - 1) % len(target_promos)
    elif action == "next":
        new_index = (current_index + 1) % len(target_promos)
    else:
        logger.warning(f"Unknown navigation action: {action}")
        return
    
    # Get new promo_id from calculated index
    new_promo_id = get_promo_id_from_promos_index(new_index, target_promos)

    # Update state with new promo_id
    updated_state = StateManager.update_state(state, promo_id=new_promo_id)
    
    logger.info(f"Navigation: {current_index} -> {new_index}, promo_id: {state.promo_id} -> {new_promo_id}")
    
    # Show the target promo with updated state
    await show_promo(update, context, content_manager, action, updated_state)
    
    if state.verified_at > 0:
        await show_admin_promo_status(update, updated_state, content_manager)