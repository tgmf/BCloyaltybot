import logging
from typing import Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# Import auth functions (mainly for get_user_info and logging)
from auth import get_user_info, log_admin_action, check_admin_access
# Import user handlers for shared functions
from user_handlers import show_promo, show_promo_with_status_message, show_status
# Import stateless utilities (now in utils)
from utils import (
    log_update, log_response, extract_message_components, validate_promo_data,
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
    
    # state_manager = get_state_manager()
    # verified_at = await state_manager.verify_admin_access(user_id, username)
    
    # if verified_at > 0:
    #     await update.message.reply_text(f"✅ Welcome {first_name}! You now have admin access.")
    #     # Show first promo with admin controls using existing show_promo
    # else:
    #     await update.message.reply_text("❌ Admin access not found. Contact administrator.")

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
            await safe_send_message(update, text=f"❌ Error displaying promo {i}: {str(e)}")

async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Toggle promo status command"""
    if not await ensure_admin_access(update, context, content_manager):
        return
    
    if not context.args:
        await safe_send_message(update, text="📝 Usage: `/toggle {promo_id}`", parse_mode="Markdown")
        return
    
    try:
        promo_id = int(context.args[0])
        await toggle_promo_status(update, context, content_manager, promo_id)
        
    except ValueError:
        await safe_send_message(update, text="❌ Invalid promo ID. Please provide a number.")

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Delete promo command"""
    if not await ensure_admin_access(update, context, content_manager):
        return
    
    if not context.args:
        await safe_send_message(update, text="📝 Usage: `/delete {promo_id}`", parse_mode="Markdown")
        return
    
    try:
        promo_id = int(context.args[0])
        await delete_promo(update, context, content_manager, promo_id)
    except ValueError:
        await safe_send_message(update, text="❌ Invalid promo ID. Please provide a number.")

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Edit promo command"""
    if not await ensure_admin_access(update, context, content_manager):
        return
    
    if context.args:
        try:
            promo_id = int(context.args[0])
            await safe_send_message(update, text=f"📝 To edit promo {promo_id}, send a new message with updated content.")
            
            # Store promo_id for next message (stateless alternative)
            user_id, _, _ = get_user_info(update)
            pending_messages_store[user_id] = {"edit_id": promo_id}
            
        except ValueError:
            await safe_send_message(update, text="❌ Invalid promo ID. Please provide a number.")
    else:
        await safe_send_message(update, text="📝 Usage: `/edit {promo_id}`", parse_mode="Markdown")

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
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    
    promo_id = state.promo_id
    try:
        promo_id = int(promo_id)
    except (TypeError, ValueError):
        await show_status(update, text=f"❌ Неверный promo_id: {promo_id}")
        return
    
    promos = content_manager.get_all_promos()
    logger.info(f"promo_id from state: {promo_id} (type: {type(promo_id)})")
    logger.info(f"promo ids in list: {[p['id'] for p in promos]}")
    
    promo = next((p for p in promos if int(p["id"]) == promo_id), None)
    if not promo:
        await show_status(update, text=f"❌ Предложение {promo_id} не найдено")
        return
    
    old_status = promo["status"]
    new_status = "inactive" if old_status == "active" else "active"
    
    user_id, username, _ = get_user_info(update)
    
    if await content_manager.update_promo_status(promo_id, new_status):
        log_admin_action(user_id, username, "TOGGLE_PROMO", f"promo_id={promo_id}, {old_status}→{new_status}")
        
        # Show success status message
        success_msg = f"✅ Предложение {promo_id}: {old_status} → {new_status}"
        updated_state = await show_status(update, state, success_msg)
        
        # Determine which promo to show
        if new_status == "active":
            # We activated it, show this promo
            target_promo_id = promo_id
        else:
            # We deactivated it, show next active promo
            active_promos = content_manager.get_active_promos()
            if active_promos:
                target_promo_id = active_promos[0]["id"]  # Show first active promo
            else:
                # No active promos, show "no promos" message
                await show_status(update, updated_state, "📭 Нет активных предложений.")
                return
        
        # Update state with target promo and show it
        final_state = StateManager.update_state(updated_state, promo_id=target_promo_id)
        await show_promo(update, context, content_manager, final_state)
        
    else:
        # Show error status message
        error_msg = f"❌ Не удалось обновить предложение {promo_id}"
        await show_status(update, state, error_msg)

async def delete_promo_inline(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Delete promo with confirmation"""
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    
    promo_id = state.get("promo_id")
    current_index = state.get("idx", 0)
    
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.admin_confirmation("Delete", promo_id, current_index)
    await safe_edit_message(
        update,
        text=f"🗑️ **Delete Promo {promo_id}?**\n\nThis action cannot be undone.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def confirm_delete_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Admin: Confirm and execute promo deletion"""
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    
    promo_id = state.get("promo_id")
    current_index = state.get("idx", 0)
    
    user_id, username, _ = get_user_info(update)
    
    if await content_manager.delete_promo(promo_id):
        log_admin_action(user_id, username, "DELETE_PROMO", f"promo_id={promo_id}")
        
        # Check if user is still admin for displaying result
        is_admin = await check_admin_access(content_manager, user_id, username)
        
        success_msg = f"✅ Promo {promo_id} deleted successfully"
        await show_promo_with_status_message(update, context, content_manager, current_index, is_admin, user_id, success_msg)
    else:
        # Check if user is still admin for displaying result
        is_admin = await check_admin_access(content_manager, user_id, username)
        
        error_msg = f"❌ Failed to delete promo {promo_id}"
        await show_promo_with_status_message(update, context, content_manager, current_index, is_admin, user_id, error_msg)

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
    current_index = state.get("idx", 0)
    
    # Check if user is admin
    user_id, username, _ = get_user_info(update)
    is_admin = await check_admin_access(content_manager, user_id, username)
    
    # Return to promo view
    await show_promo(update, context, content_manager, current_index, is_admin, user_id)

# ===== MESSAGE CREATION AND EDITING =====

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Handle new message from admin (create/edit promo)"""
    log_update(update, "ADMIN MESSAGE HANDLER")
    
    user_id, username, _ = get_user_info(update)
    
    # Check if user is admin (stateless)
    is_admin = await check_admin_access(content_manager, user_id, username)
    if not is_admin:
        logger.info("Non-admin user sent message, ignoring")
        return  # Ignore messages from non-admins
    
    message = update.message
    
    # Extract message components
    components = extract_message_components(message)
    logger.info(f"EXTRACTED MESSAGE DATA: {components}")
    
    # Check if this is an edit operation
    existing_pending = pending_messages_store.get(user_id, {})
    edit_id = existing_pending.get("edit_id")
    
    # Store pending message
    pending_data = {
        "text": components["text"],
        "image_file_id": components["image_file_id"],
        "link": components["link"],
        "created_by": str(user_id),
        "edit_id": edit_id
    }
    
    pending_messages_store[user_id] = pending_data
    logger.info(f"STORED PENDING MESSAGE: {pending_data}")
    
    # Show preview
    await show_admin_preview(update, context, content_manager, user_id)

async def show_admin_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, user_id: int):
    """Show preview of pending message"""
    pending = pending_messages_store.get(user_id)
    
    if not pending:
        await safe_send_message(update, text="❌ No pending message found.")
        return
    
    edit_id = pending.get("edit_id")
    preview_text = format_promo_preview(pending, edit_id)
    
    from keyboard_builder import KeyboardBuilder
    reply_markup = KeyboardBuilder.admin_preview(user_id)
    try:
        if pending["image_file_id"]:
            await update.message.reply_photo(
                photo=pending["image_file_id"],
                caption=preview_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                text=preview_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except TelegramError as e:
        error_msg = handle_telegram_error(e, "show_admin_preview")
        logger.error(f"Failed to show admin preview: {e}")
        await safe_send_message(update, text=f"❌ {error_msg}")

async def publish_pending_message(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager, status: str):
    """Publish pending message with given status"""
    query = update.callback_query
    action, state = StateManager.decode_callback_data(query.data)
    
    user_id = state.get("userId")
    if not user_id:
        logger.error("No userId in callback state")
        await safe_send_message(update, text="❌ Invalid request.")
        return
    
    pending = pending_messages_store.get(user_id)
    
    if not pending:
        await safe_send_message(update, text="❌ No pending message found.")
        return
    
    user_id_str, username, _ = get_user_info(update)
    edit_id = pending.get("edit_id")
    
    logger.info(f"Publishing message: user_id={user_id}, status={status}, edit_id={edit_id}")
    
    if edit_id:
        # This is an edit operation - update existing promo
        success = await content_manager.update_promo(
            edit_id,
            text=pending["text"],
            image_file_id=pending["image_file_id"],
            link=pending["link"]
        )
        
        if success:
            await content_manager.update_promo_status(edit_id, status)
            # Clear pending message
            if user_id in pending_messages_store:
                del pending_messages_store[user_id]
            
            log_admin_action(user_id_str, username, "EDIT_PROMO", f"promo_id={edit_id}, status={status}")
            
            await update.callback_query.message.reply_text(
                f"✅ Promo {edit_id} updated and set to {status}!"
            )
        else:
            await update.callback_query.message.reply_text("❌ Failed to update promo.")
    else:
        # This is a new promo
        logger.info(f"Creating new promo with data: {pending}")
        
        promo_id = await content_manager.add_promo(
            text=pending["text"],
            image_file_id=pending["image_file_id"],
            link=pending["link"],
            created_by=pending["created_by"]
        )
        
        if promo_id:
            await content_manager.update_promo_status(promo_id, status)
            # Clear pending message
            if user_id in pending_messages_store:
                del pending_messages_store[user_id]
            
            log_admin_action(user_id_str, username, "CREATE_PROMO", f"promo_id={promo_id}, status={status}")
            
            await update.callback_query.message.reply_text(
                f"✅ Promo {promo_id} {'published' if status == 'active' else 'saved as draft'}!"
            )
        else:
            await update.callback_query.message.reply_text("❌ Failed to save promo.")

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
        logger.info("Routing to publish_pending_message with status 'active'")
        await publish_pending_message(update, context, content_manager, "active")
    elif action == "adminDraft":
        logger.info("Routing to publish_pending_message with status 'draft'")
        await publish_pending_message(update, context, content_manager, "draft")
    elif action == "adminEditText":
        await query.message.reply_text("📝 Send the updated message:")
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