import logging
from typing import Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# Import auth functions (mainly for get_user_info and logging)
from auth import get_user_info, log_admin_action, check_admin_access, refresh_admin_verification
# Import user handlers for shared functions
from user_handlers import show_promo, show_status, start_command
# Import stateless utilities (now in utils)
from utils import (
    check_promos_available, cleanup_chat_messages, log_update, extract_message_components, validate_promo_data,
    safe_edit_message, safe_send_message, handle_telegram_error, get_status_emoji, truncate_text,
    format_admin_summary, format_promo_preview,
)
from state_manager import StateManager

logger = logging.getLogger(__name__)

# Global pending messages storage (stateless alternative)
# We'll use user_id as key and store pending message data
pending_messages_store: Dict[int, Dict[str, Any]] = {}

# ===== ADMIN ACCESS HELPERS =====

async def ensure_admin_access(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager) -> bool:
    """Ensure user has admin access (stateless check)"""
    user_id, username, _ = get_user_info(update)
    
    is_admin = await check_admin_access(content_manager, user_id, username)
    
    if not is_admin:
        await safe_send_message(
            update,
            text=f"🔐 Access denied. This command requires admin privileges.\n\n"
                 f"**Your Info:**\n"
                 f"• User ID: `{user_id}`\n"
                 f"• Username: @{username}" if username else f"• Username: Not set",
            parse_mode="Markdown"
        )
        logger.warning(f"Admin access denied for user {user_id} (@{username})")
        return False
    
    logger.info(f"Admin access granted for user {user_id} (@{username})")
    return True

# ===== ADMIN COMMANDS =====

async def sign_in_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Sign in command for admin access verification"""
    user_id, username, first_name = get_user_info(update)
    return

async def list_promos_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: List all promos with management buttons (creates new messages)"""
    if not await ensure_admin_access(update, context, content_manager):
        return
    
    await content_manager.refresh_cache()
    all_promos = content_manager.get_all_promos()
    
    if not all_promos:
        await safe_send_message(update, text="📭 No promos found.")
        return
    
    user_id, username, _ = get_user_info(update)
    log_admin_action(user_id, username, "LIST_PROMOS", f"total={len(all_promos)}")
    
    logger.info(f"Found {len(all_promos)} promos to display")
    
    # Send detailed list with individual messages for each promo
    from keyboard_builder import KeyboardBuilder
    for i, promo in enumerate(all_promos[:10]):  # Limit to 10 to avoid spam
        try:
            if not validate_promo_data(promo):
                logger.error(f"Invalid promo data at index {i}: {promo}")
                continue
            promo_id = promo.get("id")
            promo_order = promo.get("order", 0)
            promo_status = promo.get("status", "unknown")
            promo_text = promo.get("text", "No text")
            promo_image_file_id = promo.get("image_file_id", "")
            status_emoji = get_status_emoji(promo_status)
            display_text = f"{status_emoji} *ID {promo_id}* (Order: {promo_order})\n{truncate_text(promo_text, 100)}"
            reply_markup = KeyboardBuilder.admin_promo_actions(promo_id, i)
            if promo_image_file_id:
                await update.message.reply_photo(
                    photo=promo_image_file_id,
                    caption=display_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    text=display_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Failed to send promo {i}: {e}")
            await safe_send_message(update, text=f"❌ Ошибка отображения предложения {i}: {str(e)}\n\nПожалуйста, попробуйте еще раз: /start")

async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Toggle promo status command"""
    if not await ensure_admin_access(update, context, content_manager):
        return
    
    if not context.args:
        await safe_send_message(update, text="📝 Используйте так: `/toggle {promo_id}`", parse_mode="Markdown")
        return
    
    try:
        promo_id = int(context.args[0])
        await toggle_promo_status(update, context, content_manager, promo_id)
        
    except ValueError:
        await safe_send_message(update, text="❌ Неверный ID предложения. Пожалуйста, укажите число.")

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Delete promo command"""
    if not await ensure_admin_access(update, context, content_manager):
        return
    
    if not context.args:
        await safe_send_message(update, text="📝 Используйте так: `/delete {promo_id}`", parse_mode="Markdown")
        return
    
    try:
        promo_id = int(context.args[0])
        await delete_promo(update, context, content_manager, promo_id)
    except ValueError:
        await safe_send_message(update, text="❌ Неверный ID предложения. Пожалуйста, укажите число.")

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Edit promo command"""
    if not await ensure_admin_access(update, context, content_manager):
        return
    
    if context.args:
        try:
            promo_id = int(context.args[0])
            await safe_send_message(update, text=f"📝 Чтобы отредактировать предложение {promo_id}, отправьте новое сообщение с обновленным содержимым.")

            # Store promo_id for next message (stateless alternative)
            user_id, _, _ = get_user_info(update)
            pending_messages_store[user_id] = {"edit_id": promo_id}
            
        except ValueError:
            await safe_send_message(update, text="❌ Неверный ID предложения. Пожалуйста, укажите число.")
    else:
        await safe_send_message(update, text="📝 Используйте так: `/edit {promo_id}`", parse_mode="Markdown")

# ===== INLINE ADMIN HANDLERS =====

async def list_promos_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Show brief list of promos in current message"""
    await content_manager.refresh_cache()
    all_promos = content_manager.get_all_promos()
    
    if not all_promos:
        await safe_edit_message(update, text="📭 No promos found.")
        return
    
    # Get current index from callback for back button
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    current_index = state.get("idx", 0)
    
    # Create summary text
    summary_text = format_admin_summary(all_promos, max_count=10)
    
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.admin_back_to_promo(current_index)
    await safe_edit_message(update, text=summary_text, reply_markup=reply_markup, parse_mode="Markdown")

async def toggle_promo_status_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Toggle promo status and update current message"""
    await content_manager.refresh_cache(True)
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    logger.info(f"TOGGLE PROMO STATUS: action={action}, state={state}")
    
    promo_id = state.promo_id
    
    promos = content_manager.get_all_promos()
    
    promo = next((p for p in promos if int(p["id"]) == promo_id), None)
    if not promo:
        await show_status(update, state, text=f"❌ Предложение {promo_id} не найдено")
        return
    
    old_status = promo["status"]
    new_status = "inactive" if old_status == "active" else "active"
    
    user_id, username, _ = get_user_info(update)
    
    if await content_manager.update_promo_status(promo_id, new_status):
        log_admin_action(user_id, username, "TOGGLE_PROMO", f"promo_id={promo_id}, {old_status}→{new_status}")
        
        # Show success status message
        success_msg = f"✅ Предложение {promo_id}: {old_status} → {new_status}"
        await show_status(update, state, success_msg)

        # Determine which promo to show
        if new_status == "inactive":
            # If deactivated, show next active promo or error message
            state = await check_promos_available(update, state, content_manager)

        if state:
            await show_promo(update, context, content_manager, action, state)
        
        return

    else:
        # Show error status message
        error_msg = f"❌ Не удалось обновить предложение {promo_id}"
        await show_status(update, state, error_msg)
        
    return

async def delete_promo_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
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
        state = await check_promos_available(update, state, content_manager)
        
        if state:
            await show_promo(update, context, content_manager, action, state)
        return
    
    # Show confirmation in status message (text only)
    confirmation_text = f"🗑️ Удалить предложение {promo_id}? Это действие нельзя отменить."
    await show_status(update, state, confirmation_text)
    
    # Show current promo with confirmation keyboard
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.admin_confirmation("Delete", state)
    # Update the promo message with confirmation buttons
    await show_promo(update, context, content_manager, action, state)

async def confirm_delete_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
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
        
        # Find next available promo to show
        state = await check_promos_available(update, state, content_manager)
        
        if state:
            await show_promo(update, context, content_manager, action, state)

    else:
        # Show error status message
        error_msg = f"❌ Не удалось удалить предложение {promo_id}"
        await show_status(update, state, error_msg)

async def edit_promo_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Show editing options for specific promo"""
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    
    promo_id = state.get("promo_id")
    current_index = state.get("idx", 0)
    
    # Get the promo data
    all_promos = content_manager.get_all_promos()
    promo = next((p for p in all_promos if p["id"] == promo_id), None)
    
    if not promo:
        await safe_edit_message(update, text=f"❌ Promo {promo_id} not found")
        return
    
    # Store the promo data for editing
    user_id, _, _ = get_user_info(update)
    pending_messages_store[user_id] = {
        "edit_id": promo_id,
        "current_promo": promo,
        "edit_mode": "menu",
        "current_index": current_index
    }
    
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.admin_promo_actions(promo_id, current_index)
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except TelegramError as e:
        error_msg = handle_telegram_error(e, "edit_promo_inline")
        logger.error(f"Failed to update edit keyboard: {e}")
        await safe_send_message(update, text=f"❌ {error_msg}")
    
async def edit_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Handle text editing for specific promo"""
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    
    promo_id = state.get("promo_id")
    current_index = state.get("idx", 0)
    status_msg_id = state.get("status_message_id")  # Get status message ID from callback
    
    try:
        promo_id = int(promo_id)
    except (TypeError, ValueError):
        await safe_edit_message(update, text=f"❌ Invalid promo_id: {promo_id}")
        return
    
    # Get the promo data
    all_promos = content_manager.get_all_promos()
    promo = next((p for p in all_promos if int(p["id"]) == promo_id), None)
    
    if not promo:
        await safe_edit_message(update, text=f"❌ Promo {promo_id} not found")
        return
    
    # Store editing context in pending_messages_store
    user_id, username, first_name = get_user_info(update)
    pending_messages_store[user_id] = {
        "edit_id": promo_id,
        "current_promo": promo,
        "edit_mode": "text_only",
        "current_index": current_index,
        "status_msg_id": status_msg_id  # Store for later use
    }
    
    # Edit the status message to show instruction
    instruction_text = f"📝 Send new text for promo {promo_id}, {first_name}:"
    
    if status_msg_id:
        try:
            await update.effective_chat.edit_message_text(
                message_id=status_msg_id,
                text=instruction_text,
                parse_mode="Markdown"
            )
            logger.info(f"Updated status message {status_msg_id} with edit instruction")
        except Exception as e:
            logger.error(f"Failed to edit status message {status_msg_id}: {e}")
            # Fallback: send new message
            await update.effective_chat.send_message(
                text=instruction_text,
                parse_mode="Markdown"
            )
    else:
        logger.warning("No status message ID in callback, sending new message")
        await update.effective_chat.send_message(
            text=instruction_text,
            parse_mode="Markdown"
        )
    
    logger.info(f"Text edit mode activated for promo {promo_id} by user {user_id}")

async def back_to_promo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Handle back to promo button"""
    log_update(update, "BACK TO PROMO")
    
    query = update.callback_query
    await query.answer()
    
    # Decode state from callback
    action, state = StateManager.decode_callback_data(query.data)
    
    # Return to promo view
    await show_promo(update, context, content_manager, action, state)

# ===== MESSAGE CREATION AND EDITING =====

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
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

    # Clean up existing messages before showing new promo
    await cleanup_chat_messages(update)
    
    # Check if user has admin access after verification  
    if state.verified_at == 0:
        logger.info("Non-admin user sent message, redirecting to /start")
        await start_command(update, context, content_manager)
        return
    
    # Extract message components
    components = extract_message_components(update.message)
    logger.info(f"EXTRACTED MESSAGE DATA: {components}")
    
    # Immediately save as draft to DB
    promo_id = await content_manager.add_promo(
        text=components["text"],
        image_file_id=components["image_file_id"],
        link=components["link"],
        created_by=str(user_id)
        # status defaults to "draft" in add_promo
    )
    
    if not promo_id:
        await safe_send_message(update, text="❌ Не удалось сохранить предложение. Побробуйте еще раз: /start")
        return
    
    logger.info(f"Created draft promo with ID: {promo_id}")
    response = await safe_send_message(update, text=f"📝 Готовим новое предложение")
    promo_message_id = response.message_id if response else 0
    
    # Show status "promo saved as draft" and update state with status_message_id
    state = await show_status(update, state, "📄 Предложение сохранено как черновик")
    
    # Update state with new promo_id
    state = StateManager.update_state(state, promo_id=promo_id, promo_message_id=promo_message_id)
    # Show the new promo with preview buttons (this will update promo_message_id in state)
    await show_promo(update, context, content_manager, "adminPreview", state)
    
    # Log admin action
    log_admin_action(user_id, username, "CREATE_DRAFT", f"promo_id={promo_id}")

# ===== MAIN ADMIN CALLBACK HANDLER =====

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Handle admin callback queries"""
    log_update(update, "ADMIN CALLBACK HANDLER")
    
    query = update.callback_query
    await query.answer()
    
    user_id, username, _ = get_user_info(update)
    data = query.data
    
    logger.info(f"ADMIN CALLBACK: user_id={user_id}, data={data}")
    
    # Decode callback data
    action, state = StateManager.decode_callback_data(data)
    
    # Check admin access (stateless)
    is_admin = await check_admin_access(content_manager, user_id, username)
    if not is_admin:
        await safe_send_message(update, text="🔐 Access denied.")
        return
    
    # Route to appropriate handler
    if action == "adminPublish":
        await toggle_promo_status_inline(update, context, content_manager)
        logger.info(f"Admin {user_id} published promo {state.promo_id}")
    elif action == "adminEditText":
        await query.message.reply_text("📝 Пришлите новый текст:")
    elif action == "adminCancel":
        # Clear pending and return to promo view
        user_id_int = int(user_id) if isinstance(user_id, str) else user_id
        if user_id_int in pending_messages_store:
            del pending_messages_store[user_id_int]
        await back_to_promo_handler(update, context, content_manager)
    elif action == "adminList":
        await list_promos_inline(update, context, content_manager)
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
    elif action.startswith("edit"):
        # Placeholder: handle editAll, editLink, editImage, etc.
        await query.message.reply_text("📝 Edit action selected. Implement handler for: " + action)
    else:
        logger.warning(f"Unknown admin callback action: {action}")

# ===== HELPER FUNCTIONS =====

async def toggle_promo_status(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, promo_id: int):
    """Toggle promo status (for command version)"""
    promos = content_manager.get_all_promos()
    promo = next((p for p in promos if p["id"] == promo_id), None)
    
    if not promo:
        await safe_send_message(update, text=f"❌ Promo {promo_id} not found")
        return
    
    old_status = promo["status"]
    new_status = "inactive" if old_status == "active" else "active"
    
    user_id, username, _ = get_user_info(update)
    
    if await content_manager.update_promo_status(promo_id, new_status):
        log_admin_action(user_id, username, "TOGGLE_PROMO_CMD", f"promo_id={promo_id}, {old_status}→{new_status}")
        await safe_send_message(update, text=f"✅ Promo {promo_id} status changed from {old_status} to {new_status}")
    else:
        await safe_send_message(update, text=f"❌ Failed to update promo {promo_id}")

async def delete_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, promo_id: int):
    """Delete promo (for command version)"""
    user_id, username, _ = get_user_info(update)
    
    if await content_manager.delete_promo(promo_id):
        log_admin_action(user_id, username, "DELETE_PROMO_CMD", f"promo_id={promo_id}")
        await safe_send_message(update, text=f"✅ Promo {promo_id} deleted successfully")
    else:
        await safe_send_message(update, text=f"❌ Failed to delete promo {promo_id}")