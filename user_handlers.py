import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# Import auth functions
from auth import get_user_info, check_admin_access
# Import stateless utilities (now in utils)
from utils import (
    log_update, log_response, safe_edit_message, safe_send_message, handle_telegram_error,
    decode_callback_state, 
    validate_callback_state,
)

logger = logging.getLogger(__name__)

# ===== MAIN USER COMMANDS =====

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Start command - shows promos for everyone"""
    log_update(update, "START COMMAND")
    
    user_id, username, first_name = get_user_info(update)
    
    logger.info(f"User {user_id} (@{username}) started bot")
    
    # Check admin access (stateless - we'll embed this in callback data)
    is_admin = await check_admin_access(content_manager, user_id, username)
    
    # Refresh content
    await content_manager.refresh_cache()
    
    # Get active promos
    active_promos = content_manager.get_active_promos()
    logger.info(f"Found {len(active_promos)} active promos")
    
    # Send welcome message
    status_text = f"🎉 Welcome to BC Loyalty, {first_name}!"
    
    if not active_promos:
        status_text += "\n\nNo promos available at the moment."
        if is_admin:
            status_text += "\n\n📝 As an admin, you can create promos by sending a message with text, image, and link."
        
        await safe_send_message(update, text=status_text, parse_mode="Markdown")
        logger.warning("No active promos found")
        return
    
    # Show welcome first
    await safe_send_message(update, text=status_text, parse_mode="Markdown")
    
    # Show first promo
    await show_promo_by_index(update, context, content_manager, 0, is_admin, user_id)

# ===== PROMO DISPLAY =====

async def show_promo_by_index(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, index: int, is_admin: bool, user_id: int):
    """Display promo at specific index"""
    logger.info(f"SHOW_PROMO_BY_INDEX: index={index}, is_admin={is_admin}, user_id={user_id}")
    
    active_promos = content_manager.get_active_promos()
    
    if not active_promos or index < 0 or index >= len(active_promos):
        await safe_send_message(update, text="📭 No promos available.")
        return
    
    promo = active_promos[index]
    logger.info(f"PROMO DATA: {promo}")
    
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.user_navigation(
        promo_id=promo["id"],
        current_index=index, 
        total_promos=len(active_promos),
        is_admin=is_admin,
        verified_at=0,  # TODO: get verified_at from auth
        user_id=user_id,
        status_message_id=None,  # TODO: get status message ID
        is_list=False  # TODO: check if is_list 
    )
    
    # Send message
    try:
        if promo["image_file_id"]:
            if update.callback_query:
                # Edit existing message
                logger.info("EDITING MESSAGE WITH MEDIA")
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(media=promo["image_file_id"], caption=promo["text"]),
                    reply_markup=reply_markup
                )
            else:
                # Send new message
                logger.info("SENDING NEW PHOTO MESSAGE")
                response = await update.message.reply_photo(
                    photo=promo["image_file_id"],
                    caption=promo["text"],
                    reply_markup=reply_markup
                )
                log_response(response.to_dict(), "SEND PHOTO MESSAGE")
        else:
            if update.callback_query:
                logger.info("EDITING TEXT MESSAGE")
                await update.callback_query.edit_message_text(
                    text=promo["text"],
                    reply_markup=reply_markup
                )
            else:
                logger.info("SENDING NEW TEXT MESSAGE")
                response = await update.message.reply_text(
                    text=promo["text"],
                    reply_markup=reply_markup
                )
                log_response(response.to_dict(), "SEND TEXT MESSAGE")
                
    except TelegramError as e:
        error_msg = handle_telegram_error(e, "show_promo")
        logger.error(f"Failed to show promo: {e}")
        await safe_send_message(update, text=f"❌ {error_msg}")

async def show_promo_with_status_message(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, index: int, is_admin: bool, user_id: int, status_message: str):
    """Show promo with an additional status message"""
    active_promos = content_manager.get_active_promos()
    
    if not active_promos or index < 0 or index >= len(active_promos):
        await safe_edit_message(update, text=f"{status_message}\n\n📭 No promos available.")
        return
    
    promo = active_promos[index]
    
    # Add status message to promo text
    display_text = f"{status_message}\n\n{promo['text']}"
    
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.user_navigation(
        promo_id=promo["id"],
        current_index=index,
        total_promos=len(active_promos),
        is_admin=is_admin,
        verified_at=0,  # TODO: get verified_at from auth
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
    action, state = decode_callback_state(query.data)
    
    # Validate callback state (not too old)
    if not validate_callback_state(query.data, max_age=3600):
        await safe_send_message(update, text="⏰ This action has expired. Please use /start to refresh.")
        return
    
    # Get target index from state
    target_index = state.get("idx", 0)
    
    # Check if user is admin (fresh check since it's stateless)
    user_id, username, _ = get_user_info(update)
    is_admin = await check_admin_access(content_manager, user_id, username)
    
    # Show the target promo
    await show_promo_by_index(update, context, content_manager, target_index, is_admin, user_id)

async def visit_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Handle visit link button"""
    log_update(update, "VISIT LINK")
    
    query = update.callback_query
    await query.answer()
    
    # Decode state from callback data
    action, state = decode_callback_state(query.data)
    
    # Validate callback state
    if not validate_callback_state(query.data, max_age=3600):
        await safe_send_message(update, text="⏰ This action has expired. Please use /start to refresh.")
        return
    
    promo_id = state.get("promoId")
    if not promo_id:
        await query.message.reply_text("❌ Invalid link request.")
        return
    # Get promo by ID (ensure int comparison)
    active_promos = content_manager.get_active_promos()
    target_promo = None
    for promo in active_promos:
        if str(promo["id"]) == str(promo_id):
            target_promo = promo
            break
    if target_promo and target_promo.get("link"):
        await query.message.reply_text(
            f"🔗 **Visit Link:**\n{target_promo['link']}",
            parse_mode="Markdown"
        )
        logger.info(f"User visited link for promo {promo_id}: {target_promo['link']}")
    else:
        await query.message.reply_text("❌ Link not found or unavailable.")
        logger.warning(f"Link not found for promo {promo_id}")