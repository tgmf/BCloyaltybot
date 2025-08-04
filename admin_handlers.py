import asyncio
import re
import logging
from typing import Tuple, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# Import auth functions (mainly for get_user_info and logging)
from auth import get_user_info, log_admin_action, check_admin_access, refresh_admin_verification
# Import user handlers for shared functions
from content_manager import ContentManager
from user_handlers import show_promo, show_status, start_command
# Import stateless utilities (now in utils)
from utils import (
    check_promos_available, cleanup_chat_messages, log_update, extract_message_components, show_admin_promo_status, update_keyboard_by_action, safe_send_message,
)
from state_manager import StateManager
from keyboard_builder import KeyboardBuilder

logger = logging.getLogger(__name__)

# ===== ADMIN COMMANDS =====

async def sign_in_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Sign in command for admin access verification"""
    user_id, username, first_name = get_user_info(update)
    return

# ===== INLINE ADMIN HANDLERS =====

async def toggle_view_mode_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Toggle between 'active only' and 'show all' modes"""
    log_update(update, "TOGGLE VIEW MODE")
    await content_manager.refresh_cache()
    query = update.callback_query
    await query.answer()
    
    # Decode state from callback
    action, state = StateManager.decode_callback_data(query.data)
    
    # Toggle the mode
    new_show_all_mode = not state.show_all_mode
    updated_state = StateManager.update_state(state, show_all_mode=new_show_all_mode)
    
    user_id, username, _ = get_user_info(update)
    
    # Log the action
    mode_from = "all" if state.show_all_mode else "active"
    mode_to = "all" if new_show_all_mode else "active"
    log_admin_action(user_id, username, "TOGGLE_VIEW_MODE", f"{mode_from} → {mode_to}")
    
    # Show status notification
    if new_show_all_mode:
        status_text = "👁️ Режим просмотра: ВСЕ предложения"
    else:
        status_text = "👁️ Режим просмотра: только АКТИВНЫЕ предложения"
    
    await show_status(update, updated_state, status_text)
    
    # Find appropriate promo to show in new mode
    updated_state = await check_promos_available(update, updated_state, content_manager, preserve_position=True)
    
    if updated_state:
        # Show promo with updated state and keyboard
        await show_promo(update, context, content_manager, action, updated_state)
        
        # Wait 3 seconds, then show detailed admin status
        await asyncio.sleep(3)
        await show_admin_promo_status(update, updated_state, content_manager)

async def toggle_promo_status_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Toggle promo status and update current message"""
    await content_manager.refresh_cache(True)
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    logger.info(f"TOGGLE PROMO STATUS: action={action}, state={state}")
    
    promo_id = state.promo_id
    
    # Get all promos to find current promo
    promos = content_manager.get_all_promos()
    
    promo = next((p for p in promos if int(p["id"]) == promo_id), None)
    if not promo:
        await show_status(update, state, text=f"❌ Предложение {promo_id} не найдено")
        state = await check_promos_available(update, state, content_manager, preserve_position=True)
        if state:
            await show_promo(update, context, content_manager, action, state)
        return
    
    old_status = promo["status"]
    new_status = "inactive" if old_status == "active" else "active"
    
    user_id, username, _ = get_user_info(update)
    
    if await content_manager.update_promo_status(promo_id, new_status):
        log_admin_action(user_id, username, "TOGGLE_PROMO", f"promo_id={promo_id}, {old_status}→{new_status}")
        
        # Always stay on the current promo regardless of new status or mode
        # show_promo can handle any promo (active/inactive/draft)
        await show_promo(update, context, content_manager, action, state)
        
        # Show rich admin status with updated information
        await show_admin_promo_status(update, state, content_manager)
        
    else:
        # DB error - show error message and find fallback promo
        error_msg = f"❌ Не удалось обновить предложение {promo_id}"
        await show_status(update, state, error_msg)
        
        # Find fallback promo and show it
        state = await check_promos_available(update, state, content_manager, preserve_position=True)
        if state:
            await show_promo(update, context, content_manager, action, state)

async def delete_promo_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Delete promo with confirmation"""
    # Force refresh cache to get latest data
    
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)

    show_status(update, state, "🗑️ Готовимся к удалению...")
    await content_manager.refresh_cache(True)
    
    promo_id = state.promo_id
    
    # Check if promo still exists
    promos = content_manager.get_all_promos()
    promo = next((p for p in promos if int(p["id"]) == promo_id), None)
    if not promo:
        await show_status(update, state, f"❌ Предложение {promo_id} не найдено")
        
        # Find next available promo to show
        state = await check_promos_available(update, state, content_manager, preserve_position=True)
        
        if state:
            await show_promo(update, context, content_manager, action, state)
        return
    
    # Show confirmation in status message (text only)
    confirmation_text = f"🗑️ Удалить предложение {promo_id}? Это действие нельзя отменить."
    await show_status(update, state, confirmation_text)
    
    # Show current promo with confirmation keyboard
    await update_keyboard_by_action(update, query, action, state, content_manager)

async def confirm_delete_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Confirm and execute promo deletion"""
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)

    show_status(update, state, "🗑️ Удаляем...")
    await content_manager.refresh_cache(True)
    
    promo_id = state.promo_id
    
    user_id, username, _ = get_user_info(update)
    
    if await content_manager.delete_promo(promo_id):
        log_admin_action(user_id, username, "DELETE_PROMO", f"promo_id={promo_id}")
        
        # Show success status message
        success_msg = f"✅ Предложение {promo_id} удалено"
        await show_status(update, state, success_msg)

    else:
        # Show error status message
        error_msg = f"❌ Не удалось удалить предложение {promo_id}"
        await show_status(update, state, error_msg)
        
    # Find available promo to show
    state = await check_promos_available(update, state, content_manager, preserve_position=True)
    
    if state:
        await show_promo(update, context, content_manager, action, state)

async def edit_promo_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Show editing options for specific promo"""
    query = update.callback_query
    await query.answer()
    action, state = StateManager.decode_callback_data(query.data)
    
    promo_id = state.promo_id
    
    # Get the promo data
    all_promos = content_manager.get_all_promos()
    promo = next((p for p in all_promos if p["id"] == promo_id), None)
    
    if not promo:
        await show_status(update, state, text=f"❌ Предложение {promo_id} не найдено")
        return
    
    await update_keyboard_by_action(update, query, action, state, content_manager)

    await show_status(update, state, f"📝 Что надо отредактировать?")

async def edit_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Handle text editing for specific promo"""
    query = update.callback_query
    await query.answer()
    action, state = StateManager.decode_callback_data(query.data)
    promo_id = state.promo_id
    
    await update_keyboard_by_action(update, query, action, state, content_manager)
    
    # Show instruction in status message
    instruction_text = f"📝 Отправь новый текст для предложения {promo_id}, \n*в ответе на это сообщение* ‼️"
    await show_status(update, state, instruction_text)
    
    logger.info(f"Text edit mode activated for promo {promo_id}")
    
async def edit_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Handle link editing for specific promo"""
    query = update.callback_query
    await query.answer()
    action, state = StateManager.decode_callback_data(query.data)
    promo_id = state.promo_id
    
    await update_keyboard_by_action(update, query, action, state, content_manager)
    
    # Show instruction in status message
    instruction_text = f"🔗 Отправь новую ссылку для предложения {promo_id}, \n*в ответе на это сообщение* ‼️"
    await show_status(update, state, instruction_text)

    logger.info(f"Link edit mode activated for promo {promo_id}")

async def edit_image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Handle image editing for specific promo"""
    query = update.callback_query
    await query.answer()
    action, state = StateManager.decode_callback_data(query.data)
    promo_id = state.promo_id
    
    await update_keyboard_by_action(update, query, action, state, content_manager)
    
    # Show instruction in status message
    instruction_text = f"🖼️ Отправь новое изображение для предложения {promo_id}, \n*в ответе на это сообщение* ‼️"
    await show_status(update, state, instruction_text)

    logger.info(f"Image edit mode activated for promo {promo_id}")

async def edit_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Admin: Handle complete promo replacement"""
    query = update.callback_query
    await query.answer()
    action, state = StateManager.decode_callback_data(query.data)
    promo_id = state.promo_id
    
    await update_keyboard_by_action(update, query, action, state, content_manager)
    
    # Show instruction in status message
    instruction_text = f"🔄 Отправь полное сообщение для замены предложения {promo_id}, \n*в ответе на это сообщение* ‼️"
    await show_status(update, state, instruction_text)

    logger.info(f"Complete edit mode activated for promo {promo_id}")

async def back_to_promo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Handle back to promo button"""
    log_update(update, "BACK TO PROMO")
    
    query = update.callback_query
    await query.answer()
    
    # Decode state from callback
    action, state = StateManager.decode_callback_data(query.data)
    
    # Return to promo view
    await update_keyboard_by_action(update, query, action, state, content_manager)
    await show_admin_promo_status(update, state, content_manager)

# ===== MESSAGE CREATION AND EDITING =====

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager: ContentManager):
    """Handle new message from admin (create promo as draft immediately)"""
    log_update(update, "ADMIN MESSAGE HANDLER")
    
    user_id, username, _ = get_user_info(update)
    
    # Create state with admin verification
    state = StateManager.create_state(
        promo_id=0,  # Will be updated after saving
        verified_at=1, # Will be updated after verification
        status_message_id=0,  # Will be updated after cleanup
        promo_message_id=0   # Will be updated after showing promo
    )
    
    # Get current state (admin should have verified_at > 0)
    state = await refresh_admin_verification(state, content_manager, user_id, username)

    # Check if user has admin access after verification  
    if state.verified_at == 0:
        # Redirecting non-admin user to /start
        logger.info("Non-admin user sent message, redirecting to /start")
        await start_command(update, context, content_manager)
        return

    # Check for edit mode by looking at previous messages
    edit_mode, promo_id = await detect_edit_mode(update)
    components = extract_message_components(update.message)

    if promo_id == 0:
        # CREATE NEW PROMO
        promo_id = await content_manager.add_promo(
            text=components["text"],
            image_file_id=components["image_file_id"], 
            link=components["link"],
            created_by=str(user_id)
        )
        
        init_text = "📝 Готовим новое предложение"
        status_text = "📄 Предложение сохранено как черновик"
        action = "adminPreview"
        log_action = "CREATE_DRAFT"
        
    else:
        # EDIT EXISTING PROMO
        await content_manager.refresh_cache(True)
        update_data = build_update_data(edit_mode, components)
        if await content_manager.update_promo(promo_id, **update_data):
            # Success path
            init_text = "✏️ Обновляем предложение"
            status_text = f"✅ Предложение {promo_id} обновлено ({edit_mode})"
            action = "adminEdit"
            log_action = f"EDIT_PROMO_{edit_mode.upper()}"
        else:
            # Error path
            init_text = "❌ Ошибка обновления"
            status_text = f"❌ Не удалось обновить предложение {promo_id}"
            state = await check_promos_available(update, state, content_manager, preserve_position=True)
            action = "backToPromo"
            log_action = f"EDIT_PROMO_{edit_mode.upper()}_FAILED"
    
    await cleanup_chat_messages(update)
    
    # Common flow for both
    logger.info(f"Action: {log_action}, promo_id: {promo_id}")
    response = await safe_send_message(update, text=init_text)
    promo_message_id = response.message_id if response else 0
    
    state = await show_status(update, state, status_text)
    state = StateManager.update_state(state, promo_id=promo_id, promo_message_id=promo_message_id)
    
    await show_promo(update, context, content_manager, action, state)
    
    log_admin_action(user_id, username, log_action, f"promo_id={promo_id}")
    
def build_update_data(edit_mode: str, components: Dict[str, str]) -> Dict[str, str]:
    """Build update data based on edit mode and message components"""
    
    if edit_mode == "text":
        return {"text": components["text"]}
    
    elif edit_mode == "link":
        return {"link": components["link"]}
    
    elif edit_mode == "image":
        return {"image_file_id": components["image_file_id"]}
    
    elif edit_mode == "all":
        return components  # Replace everything, including with empty strings
    
    else:
        logger.warning(f"Unknown edit_mode: {edit_mode}")
        return {}
    
async def detect_edit_mode(update: Update) -> Tuple[str, int]:
    """
    Detect edit mode by checking if message is a reply to instruction
    Much more efficient than forwarding messages - 0 API calls!
    
    Returns: (edit_mode, promo_id) or ("", 0) if not in edit mode
    
    Patterns to match in replied-to message:
    - "📝 Отправь новый текст для предложения {promo_id}"
    - "🔗 Отправь новую ссылку для предложения {promo_id}"
    - "🖼️ Отправь новое изображение для предложения {promo_id}"
    - "🔄 Отправь полное сообщение для замены предложения {promo_id}"
    """
    try:
        # Check if this message is a reply
        if not update.message.reply_to_message:
            logger.debug("Message is not a reply - no edit mode detected")
            return ("", 0)
        
        reply_msg = update.message.reply_to_message
        text = reply_msg.text or reply_msg.caption or ""
        
        # Define patterns for each edit mode
        patterns = {
            "text": r"📝 Отправь новый текст для предложения (\d+)",
            "link": r"🔗 Отправь новую ссылку для предложения (\d+)",
            "image": r"🖼️ Отправь новое изображение для предложения (\d+)",
            "all": r"🔄 Отправь полное сообщение для замены предложения (\d+)"
        }
        
        # Check each pattern
        for mode, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                promo_id = int(match.group(1))
                logger.info(f"Detected edit mode via reply: {mode}, promo_id: {promo_id}")
                return (mode, promo_id)
        
        logger.debug(f"Reply message doesn't match edit patterns: {text[:50]}...")
        return ("", 0)
        
    except Exception as e:
        logger.error(f"Error in detect_edit_mode: {e}")
        return ("", 0)

# ===== MAIN ADMIN CALLBACK HANDLER =====

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Handle admin callback queries"""
    log_update(update, "ADMIN CALLBACK HANDLER")
    
    chat_id = update.effective_chat.id
    bot = update.get_bot()
    await bot.send_chat_action(chat_id=chat_id, action="typing")  # Fire and forget
    query = update.callback_query
    await query.answer()
    
    user_id, username, _ = get_user_info(update)
    data = query.data
    
    logger.info(f"ADMIN CALLBACK: user_id={user_id}, data={data}")
    
    # Decode callback data
    action, state = StateManager.decode_callback_data(data)
    
    # Check admin access (stateless)
    state = await refresh_admin_verification(state, content_manager, user_id, username)
    if state.verified_at == 0:
        await show_status(update, text="🔐 Необходимы права администратора.")
        return
    
    # Route to appropriate handler
    if action == "adminPublish":
        await toggle_promo_status_inline(update, context, content_manager)
        logger.info(f"Admin {user_id} published promo {state.promo_id}")
    elif action == "adminView":
        await toggle_view_mode_inline(update, context, content_manager)
    elif action == "confirmDelete":
        await confirm_delete_promo(update, context, content_manager)
    elif action == "adminEdit":
        await edit_promo_inline(update, context, content_manager)
    elif action == "adminToggle":
        await toggle_promo_status_inline(update, context, content_manager)
    elif action == "adminDelete":
        await delete_promo_inline(update, context, content_manager)
    elif action == "editText":
        await edit_text_handler(update, context, content_manager)
    elif action == "editImage":
        await edit_image_handler(update, context, content_manager)
    elif action == "editLink":
        await edit_link_handler(update, context, content_manager)
    elif action == "editAll":
        await edit_all_handler(update, context, content_manager)
    else:
        logger.warning(f"Unknown admin callback action: {action}")