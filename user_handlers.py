import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# Import auth functions
from auth import get_user_info, verify_admin_access
# Import stateless utilities (now in utils)
from keyboard_builder import KeyboardBuilder
from state_manager import BotState, StateManager
from utils import (
    check_promos_available, get_promo_id_from_promos_index, log_update, log_response, safe_edit_message, safe_send_message, handle_telegram_error, get_promos_index_from_promo_id
)

logger = logging.getLogger(__name__)

# ===== MAIN USER COMMANDS =====

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Start command - shows promos for everyone"""
    log_update(update, "START COMMAND")
    
    user_id, username, first_name = get_user_info(update)
    
    logger.info(f"User {user_id} (@{username}) started bot")
    
    # Check admin status and get verified_at timestamp
    verified_at = await verify_admin_access(content_manager, user_id, username)
    
    # Create initial state with status message ID
    state = StateManager.create_state(
        promo_id=0,  # First promo
        verified_at=verified_at,
        status_message_id=0,
        promo_message_id=0  # Will be set when promo is sent
    )
    
    # Send welcome message
    welcome_text = f"🎉 Добро пожаловать в Business Club, {first_name}!"
    
    # Send welcome message and capture message ID
    state = await show_status(update, state, text=welcome_text)

    init_text = f"⏲️ Собираем предложения для вас... Пожалуйста, подождите."

    # Show initial status message
    response = await safe_send_message(update, text=init_text)
    promo_message_id = response.message_id if response else 0

    state = StateManager.update_state(state, promo_message_id=promo_message_id)

    state_with_promo = await check_promos_available(update, state, content_manager)

    if not state_with_promo:
        logger.error("No valid promo found.")
        return
    
    # Show first promo with state
    await show_promo(update, context, content_manager, state_with_promo)
    

# ===== PROMO DISPLAY =====

async def show_status(update: Update, state, text, parse_mode="Markdown") -> BotState:
    """
    Post or update status message based on current state
    If state.status_message_id exists, edit it; otherwise, send a new message
    Returns updated state with status_message_id set
    """
    if state.status_message_id:
        await safe_edit_message(update, text=text, parse_mode=parse_mode, message_id=state.status_message_id)
    else:
        response = await safe_send_message(update, text=text, parse_mode=parse_mode)
        if response:
            state = StateManager.update_state(state, status_message_id=response.message_id)
        else:
            logger.error("Failed to send status message")

    return state

async def show_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, state: BotState) -> BotState:
    """Display promo using state management"""
    active_promos = content_manager.get_active_promos()
    
    # Find the promo by ID
    promo = next((p for p in active_promos if p["id"] == state.promo_id), None)
    if not promo:
        await show_status(update, state, "❌ Не удалось найти это предложение.")
        return state
    
    # Extract link for keyboard
    promo_link = promo.get("link", "")
    
    # Build keyboard with current state and link
    reply_markup = KeyboardBuilder.user_navigation(state, promo_link)

    # Validate and clean image_file_id
    image_file_id = promo.get("image_file_id", "")
    has_image = image_file_id and image_file_id.strip() and image_file_id != "None"
    
    # Log the image status for debugging
    logger.info(f"Promo {state.promo_id} image status: '{image_file_id}' -> has_image: {has_image}")

    if state.promo_message_id:
        # Editing existing message - use media/text format
        if has_image:
            message_kwargs = {
                "media": InputMediaPhoto(media=image_file_id, caption=promo["text"], parse_mode="Markdown"),
                "reply_markup": reply_markup,
                "message_id": state.promo_message_id
            }
        else:
            message_kwargs = {
                "text": promo["text"],
                "reply_markup": reply_markup,
                "message_id": state.promo_message_id,
                "parse_mode": "Markdown",
            }
        
        # Try to edit existing message
        logger.info(f"EDITING MESSAGE ID: {state.promo_message_id}")
        response = await safe_edit_message(update, **message_kwargs)
        if not response:
            logger.error("Failed to edit promo message")
            await show_status(update, state, "❌ Не удалось обновить чат")
        return state
    else:
        # Sending new message - use photo/text format
        if promo["image_file_id"]:
            message_kwargs = {
                "photo": promo["image_file_id"],
                "caption": promo["text"],
                "reply_markup": reply_markup,
                "parse_mode": "Markdown"
            }
        else:
            message_kwargs = {
                "text": promo["text"],
                "reply_markup": reply_markup,
                "parse_mode": "Markdown"
            }
        
        # Send new message
        logger.info("SENDING NEW PROMO MESSAGE")
        response = await safe_send_message(update, **message_kwargs)
        
        if response:
            logger.info(f"NEW PROMO MESSAGE ID: {response.message_id}")
            return StateManager.update_state(state, promo_message_id=response.message_id)
        else:
            logger.error("Failed to send promo message")
            await show_status(update, state, "❌ Не удалось отправить сообщение")
            return state

async def show_promo_with_status_message(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, index: int, verified_at: 0, user_id: int, status_message: str):
    """Show promo with an additional status message"""
    active_promos = content_manager.get_active_promos()
    
    if not active_promos or index < 0 or index >= len(active_promos):
        await safe_edit_message(update, text=f"{status_message}\n\n📭 Нет доступных предложений.")
        return
    
    promo = active_promos[index]
    
    # Add status message to promo text
    display_text = f"{status_message}\n\n{promo['text']}"
    
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.user_navigation(
        promo_id=promo["id"],
        current_index=index,
        total_promos=len(active_promos),
        verified_at=verified_at,  # now passing verified_at
        user_id=user_id,
        status_message_id=None,  # TODO: get status message ID
        is_list=False  # TODO: check if is_list
    )
    
    # Send message
    try:
        if promo["image_file_id"]:
            await update.callback_query.edit_message_media(
                media=InputMediaPhoto(media=promo["image_file_id"], caption=display_text),
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.edit_message_text(
                text=display_text,
                reply_markup=reply_markup
            )
    except TelegramError as e:
        error_msg = handle_telegram_error(e, "show_promo_with_status_message")
        logger.error(f"Failed to show promo with message: {e}")

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
    
    active_promos = content_manager.get_active_promos()
    
    # Find current index from promo_id
    current_index = get_promos_index_from_promo_id(state.promo_id, active_promos)
    
    # Calculate new index based on action
    if action == "prev":
        new_index = (current_index - 1) % len(active_promos)
    elif action == "next":
        new_index = (current_index + 1) % len(active_promos)
    else:
        logger.warning(f"Unknown navigation action: {action}")
        return
    
    # Get new promo_id from calculated index
    new_promo_id = get_promo_id_from_promos_index(new_index, active_promos)
    
    # Update state with new promo_id
    updated_state = StateManager.update_state(state, promo_id=new_promo_id)
    
    logger.info(f"Navigation: {current_index} -> {new_index}, promo_id: {state.promo_id} -> {new_promo_id}")
    
    # Show the target promo with updated state
    await show_promo(update, context, content_manager, updated_state)
        
# async def update_chat(update, context, content_manager, state):
    
#     if state.action :
#         # Handle empty state
#         status_msg = "No promos available"
#         if state.verified_at > 0:  # Admin
#             status_msg += "\n\n📝 Send message to create promo"
        
#         await update_status_message(status_msg)
#         return
    
#     # Normal promo display logic
#     promo = get_promos_index_from_promo_id(state.promo_id, active_promos)
#     if not promo:
#         promo = active_promos[0]  # Fallback to first
#         state.promo_id = promo["id"]
    
#     await show_promo(update, context, content_manager, state)