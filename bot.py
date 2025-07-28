import logging
import os
import asyncio
from typing import Dict, Optional
from datetime import datetime
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from telegram.error import TelegramError

from content_manager import ContentManager

# Enable logging with more detail
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

# Monkey patch telegram methods to add logging
original_send_message = None
original_edit_message_text = None
original_edit_message_media = None
original_send_photo = None

def setup_telegram_logging():
    """Setup logging for telegram API calls"""
    global original_send_message, original_edit_message_text, original_edit_message_media, original_send_photo
    
    # We'll add this after bot creation

class UserSession:
    """Track user session for navigation"""
    def __init__(self):
        self.current_index = 0
        self.last_activity = datetime.now()
        self.is_admin = False

class LoyaltyBot:
    """Unified bot for both users and admins"""
    
    def __init__(self, content_manager: ContentManager):
        self.content_manager = content_manager
        self.user_sessions: Dict[int, UserSession] = {}
        self.pending_messages: Dict[int, Dict] = {}
    
    # ===== AUTHENTICATION =====
    
    async def check_admin_access(self, user_id: int, username: str = "") -> bool:
        """Check if user has admin access"""
        # Refresh auth cache
        await self.content_manager.refresh_cache()
        
        user_id_str = str(user_id)
        
        logger.info(f"Checking admin access for user_id: {user_id_str}, username: {username}")
        logger.info(f"Auth cache: {self.content_manager.auth_cache}")
        
        # Check authorization by user_id or username
        for phone, auth_data in self.content_manager.auth_cache.items():
            logger.info(f"Checking phone {phone}: {auth_data}")
            if auth_data.get("user_id") == user_id_str or auth_data.get("username") == username:
                logger.info(f"Admin access granted for user {user_id_str}")
                return True
        
        logger.info(f"Admin access denied for user {user_id_str}")
        return False
    
    def get_or_create_session(self, user_id: int) -> UserSession:
        """Get or create user session"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSession()
        return self.user_sessions[user_id]
    
    # ===== COMMON COMMANDS =====
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command - shows promos for everyone"""
        log_update(update, "START COMMAND")
        
        user = update.effective_user
        user_id = user.id
        username = user.username or ""
        
        logger.info(f"User {user_id} started bot")
        
        # Check admin access
        session = self.get_or_create_session(user_id)
        session.is_admin = await self.check_admin_access(user_id, username)
        
        # Refresh content
        await self.content_manager.refresh_cache()
        
        # Get active promos
        active_promos = self.content_manager.get_active_promos()
        logger.info(f"Found {len(active_promos)} active promos")
        
        # Send welcome message (same for everyone)
        welcome_text = "🎉 Welcome to BC Loyalty!"
        
        if not active_promos:
            welcome_text += "\n\nNo promos available at the moment."
            response = await update.message.reply_text(welcome_text, parse_mode="Markdown")
            log_response(response.to_dict(), "WELCOME MESSAGE (NO PROMOS)")
            logger.warning("No active promos found")
            return
        
        # Show welcome first
        welcome_response = await update.message.reply_text(welcome_text, parse_mode="Markdown")
        log_response(welcome_response.to_dict(), "WELCOME MESSAGE")
        
        # Show first promo (same for everyone)
        await self.show_promo(update, context, user_id, 0)
    
    # ===== PROMO DISPLAY (USER FUNCTIONALITY) =====
    
    async def show_promo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, index: int):
        """Display promo message with navigation"""
        logger.info(f"SHOW_PROMO: user_id={user_id}, index={index}")
        
        active_promos = self.content_manager.get_active_promos()
        
        if not active_promos or index < 0 or index >= len(active_promos):
            await update.effective_message.reply_text("No promos available.")
            return
        
        promo = active_promos[index]
        logger.info(f"PROMO DATA: {promo}")
        
        session = self.get_or_create_session(user_id)
        session.current_index = index
        
        # Create navigation keyboard
        keyboard = []
        
        # Navigation row (always first)
        nav_buttons = []
        nav_buttons.append(InlineKeyboardButton("← Previous", callback_data="prev"))
        
        # Visit link button
        if promo["link"]:
            nav_buttons.append(InlineKeyboardButton("🔗 Visit Link", callback_data=f"visit_{promo['id']}"))
        
        nav_buttons.append(InlineKeyboardButton("Next →", callback_data="next"))
        keyboard.append(nav_buttons)
        
        # Admin panel row (only for admins)
        if session.is_admin:
            admin_buttons = []
            admin_buttons.append(InlineKeyboardButton("📋 List", callback_data="admin_list"))
            admin_buttons.append(InlineKeyboardButton("📝 Edit", callback_data=f"admin_edit_{promo['id']}"))
            admin_buttons.append(InlineKeyboardButton("🔄 Toggle", callback_data=f"admin_toggle_{promo['id']}"))
            admin_buttons.append(InlineKeyboardButton("🗑️ Delete", callback_data=f"admin_delete_{promo['id']}"))
            keyboard.append(admin_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        logger.info(f"KEYBOARD: {reply_markup.to_dict()}")
        
        # Send message
        try:
            if promo["image_file_id"]:
                if update.callback_query:
                    # Edit existing message
                    logger.info("EDITING MESSAGE WITH MEDIA")
                    response = await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(media=promo["image_file_id"], caption=promo["text"]),
                        reply_markup=reply_markup
                    )
                    log_response(response.to_dict() if response else {"result": "edit_success"}, "EDIT MESSAGE MEDIA")
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
                    response = await update.callback_query.edit_message_text(
                        text=promo["text"],
                        reply_markup=reply_markup
                    )
                    log_response(response.to_dict() if response else {"result": "edit_success"}, "EDIT TEXT MESSAGE")
                else:
                    logger.info("SENDING NEW TEXT MESSAGE")
                    response = await update.message.reply_text(
                        text=promo["text"],
                        reply_markup=reply_markup
                    )
                    log_response(response.to_dict(), "SEND TEXT MESSAGE")
        except TelegramError as e:
            logger.error(f"Failed to show promo: {e}")
    
    async def navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle navigation buttons (prev/next) with looping"""
        log_update(update, "NAVIGATION")
        
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        session = self.get_or_create_session(user_id)
        
        current_index = session.current_index
        active_promos = self.content_manager.get_active_promos()
        
        if not active_promos:
            return
        
        total_promos = len(active_promos)
        
        if query.data == "prev":
            # Loop to last promo if at first promo
            new_index = (current_index - 1) % total_promos
            await self.show_promo(update, context, user_id, new_index)
        elif query.data == "next":
            # Loop to first promo if at last promo
            new_index = (current_index + 1) % total_promos
            await self.show_promo(update, context, user_id, new_index)
    
    async def visit_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle visit link button"""
        query = update.callback_query
        await query.answer()
        
        promo_id = int(query.data.split("_")[1])
        active_promos = self.content_manager.get_active_promos()
        
        for promo in active_promos:
            if promo["id"] == promo_id and promo["link"]:
                await query.message.reply_text(f"🔗 Visit: {promo['link']}")
                break
    
    async def back_to_promo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back to promo button"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        session = self.get_or_create_session(user_id)
        
        # Return to current promo view
        await self.show_promo(update, context, user_id, session.current_index)
    
    # ===== ADMIN COMMANDS =====
    
    async def admin_required(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if user is admin, send error if not"""
        user = update.effective_user
        user_id = user.id
        username = user.username or ""
        
        if not await self.check_admin_access(user_id, username):
            await update.message.reply_text(
                "🔐 Access denied. This command requires admin privileges.\n"
                f"Your User ID: `{user_id}`\n"
                f"Your Username: @{username}" if username else f"Your Username: Not set",
                parse_mode="Markdown"
            )
            return False
        return True
    
    async def list_promos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin: List all promos with management buttons"""
        if not await self.admin_required(update, context):
            return
        
        await self.content_manager.refresh_cache()
        all_promos = self.content_manager.get_all_promos()
        
        if not all_promos:
            await update.message.reply_text("📭 No promos found.")
            return
        
        logger.info(f"Found {len(all_promos)} promos to display")
        
        for i, promo in enumerate(all_promos[:10]):  # Limit to 10 to avoid message length issues
            try:
                # Debug logging
                logger.info(f"Processing promo {i}: {type(promo)} - {promo}")
                
                # Ensure promo is a dictionary
                if not isinstance(promo, dict):
                    logger.error(f"Promo {i} is not a dictionary: {type(promo)} - {promo}")
                    continue
                
                # Safely get values with defaults
                promo_id = promo.get("id", "Unknown")
                promo_order = promo.get("order", 0)
                promo_status = promo.get("status", "unknown")
                promo_text = promo.get("text", "No text")
                promo_image_file_id = promo.get("image_file_id", "")
                
                status_emoji = {"active": "✅", "draft": "📄", "inactive": "❌"}.get(promo_status, "❓")
                
                # Safely truncate text
                display_text = str(promo_text)[:100] if promo_text else "No text"
                text = f"{status_emoji} *ID {promo_id}* (Order: {promo_order})\n{display_text}..."
                
                # Add action buttons for each promo
                keyboard = [
                    [
                        InlineKeyboardButton("📝 Edit", callback_data=f"admin_edit_{promo_id}"),
                        InlineKeyboardButton("🔄 Toggle", callback_data=f"admin_toggle_{promo_id}"),
                        InlineKeyboardButton("🗑️ Delete", callback_data=f"admin_delete_{promo_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if promo_image_file_id:
                    await update.message.reply_photo(
                        photo=promo_image_file_id,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    
            except Exception as e:
                logger.error(f"Failed to send promo {i}: {e}")
                # Send error message for this specific promo
                await update.message.reply_text(f"❌ Error displaying promo {i}: {str(e)}")
    
    async def toggle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin: Toggle promo status command"""
        if not await self.admin_required(update, context):
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /toggle {promo_id}")
            return
        
        try:
            promo_id = int(context.args[0])
            await self.toggle_promo_status(update, context, promo_id)
        except ValueError:
            await update.message.reply_text("Invalid promo ID")
    
    async def toggle_promo_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE, promo_id: int):
        """Toggle between active/inactive status"""
        promos = self.content_manager.get_all_promos()
        promo = next((p for p in promos if p["id"] == promo_id), None)
        
        if not promo:
            await update.effective_message.reply_text(f"Promo {promo_id} not found")
            return
        
        new_status = "inactive" if promo["status"] == "active" else "active"
        
        if await self.content_manager.update_promo_status(promo_id, new_status):
            await update.effective_message.reply_text(f"✅ Promo {promo_id} status changed to {new_status}")
        else:
            await update.effective_message.reply_text(f"❌ Failed to update promo {promo_id}")
    
    async def delete_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin: Delete promo command"""
        if not await self.admin_required(update, context):
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /delete {promo_id}")
            return
        
        try:
            promo_id = int(context.args[0])
            await self.delete_promo(update, context, promo_id)
        except ValueError:
            await update.message.reply_text("Invalid promo ID")
    
    async def delete_promo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, promo_id: int):
        """Delete promo"""
        if await self.content_manager.delete_promo(promo_id):
            await update.effective_message.reply_text(f"✅ Promo {promo_id} deleted")
        else:
            await update.effective_message.reply_text(f"❌ Failed to delete promo {promo_id}")
    
    async def edit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin: Edit promo command"""
        if not await self.admin_required(update, context):
            return
        
        if context.args:
            try:
                promo_id = int(context.args[0])
                await update.message.reply_text(f"To edit promo {promo_id}, send a new message with updated content.")
                # Store promo_id for next message
                user_id = update.effective_user.id
                if user_id not in self.pending_messages:
                    self.pending_messages[user_id] = {}
                self.pending_messages[user_id]["edit_id"] = promo_id
            except ValueError:
                await update.message.reply_text("Invalid promo ID")
        else:
            await update.message.reply_text("Usage: /edit {promo_id}")
    
    # ===== ADMIN MESSAGE HANDLING =====
    
    async def admin_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new message from admin (create/edit promo)"""
        log_update(update, "ADMIN MESSAGE HANDLER")
        
        user_id = update.effective_user.id
        
        # Check if user is admin
        user = update.effective_user
        username = user.username or ""
        if not await self.check_admin_access(user_id, username):
            logger.info("Non-admin user sent message, ignoring")
            return  # Ignore messages from non-admins
        
        message = update.message
        
        # Extract message components
        text = message.text or message.caption or ""
        image_file_id = ""
        link = ""
        
        # Get image file_id
        if message.photo:
            image_file_id = message.photo[-1].file_id
        
        # Extract link from entities
        if message.entities:
            for entity in message.entities:
                if entity.type == "url":
                    link = text[entity.offset:entity.offset + entity.length]
                    break
        
        logger.info(f"EXTRACTED MESSAGE DATA:")
        logger.info(f"  Text: {text}")
        logger.info(f"  Image file_id: {image_file_id}")
        logger.info(f"  Link: {link}")
        
        # Check if this is an edit operation
        edit_id = None
        if user_id in self.pending_messages and "edit_id" in self.pending_messages[user_id]:
            edit_id = self.pending_messages[user_id]["edit_id"]
            del self.pending_messages[user_id]["edit_id"]
        
        # Store pending message
        self.pending_messages[user_id] = {
            "text": text,
            "image_file_id": image_file_id,
            "link": link,
            "created_by": str(user_id),
            "edit_id": edit_id
        }
        
        logger.info(f"STORED PENDING MESSAGE: {self.pending_messages[user_id]}")
        
        # Show preview
        await self.show_admin_preview(update, context, user_id)
    
    async def show_admin_preview(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """Show preview of pending message"""
        pending = self.pending_messages.get(user_id)
        if not pending:
            return
        
        edit_id = pending.get("edit_id")
        action = "Edit" if edit_id else "Create"
        
        preview_text = f"📱 *{action} Preview:*"
        if edit_id:
            preview_text += f" (ID: {edit_id})"
        preview_text += f"\n\n{pending['text']}"
        
        if pending['link']:
            preview_text += f"\n\n🔗 Link: {pending['link']}"
        
        keyboard = [
            [
                InlineKeyboardButton("📤 Publish", callback_data="admin_publish"),
                InlineKeyboardButton("📄 Draft", callback_data="admin_draft")
            ],
            [
                InlineKeyboardButton("📝 Edit", callback_data="admin_edit"),
                InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
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
            logger.error(f"Failed to show admin preview: {e}")
    
    async def admin_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin callback queries"""
        log_update(update, "ADMIN CALLBACK HANDLER")
        
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        logger.info(f"ADMIN CALLBACK: user_id={user_id}, data={data}")
        
        # Check admin access for callback queries
        user = update.effective_user
        username = user.username or ""
        if not await self.check_admin_access(user_id, username):
            await query.message.reply_text("🔐 Access denied.")
            return
        
        if data == "admin_publish":
            logger.info("Publishing pending message as active")
            await self.publish_pending_message(update, context, user_id, "active")
        elif data == "admin_draft":
            logger.info("Publishing pending message as draft")
            await self.publish_pending_message(update, context, user_id, "draft")
        elif data == "admin_edit":
            await query.message.reply_text("Send the updated message:")
        elif data == "admin_cancel":
            # Return to promo view instead of showing "cancelled" message
            if user_id in self.pending_messages:
                del self.pending_messages[user_id]
            
            session = self.get_or_create_session(user_id)
            await self.show_promo(update, context, user_id, session.current_index)
        elif data == "admin_list":
            # Show list of all promos in a new message
            await self.list_promos_inline(update, context)
        elif data.startswith("confirm_delete_"):
            promo_id = int(data.split("_")[2])
            await self.confirm_delete_promo(update, context, promo_id)
        elif data.startswith("admin_edit_"):
            promo_id = int(data.split("_")[2])
            await self.edit_promo_inline(update, context, promo_id)
        elif data.startswith("admin_toggle_"):
            promo_id = int(data.split("_")[2])
            await self.toggle_promo_status_inline(update, context, promo_id)
        elif data.startswith("admin_delete_"):
            promo_id = int(data.split("_")[2])
            await self.delete_promo_inline(update, context, promo_id)
        elif data.startswith("edit_text_"):
            promo_id = int(data.split("_")[2])
            await self.edit_text_dialog(update, context, promo_id)
        elif data.startswith("edit_link_"):
            promo_id = int(data.split("_")[2])
            await self.edit_link_dialog(update, context, promo_id)
        elif data.startswith("edit_image_"):
            promo_id = int(data.split("_")[2])
            await self.edit_image_dialog(update, context, promo_id)
        elif data.startswith("edit_all_"):
            promo_id = int(data.split("_")[2])
            await self.edit_all_dialog(update, context, promo_id)
    
    async def list_promos_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin: Show brief list of promos in current message"""
        await self.content_manager.refresh_cache()
        all_promos = self.content_manager.get_all_promos()
        
        if not all_promos:
            await update.callback_query.edit_message_text("📭 No promos found.")
            return
        
        # Create a summary list
        summary_lines = ["📋 **All Promos:**\n"]
        for promo in all_promos[:10]:  # Limit to 10
            status_emoji = {"active": "✅", "draft": "📄", "inactive": "❌"}.get(promo.get("status"), "❓")
            promo_text = str(promo.get("text", "No text"))[:50]
            summary_lines.append(f"{status_emoji} **ID {promo.get('id')}**: {promo_text}...")
        
        summary_text = "\n".join(summary_lines)
        
        # Add back button
        keyboard = [[InlineKeyboardButton("← Back to Promo", callback_data="back_to_promo")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text=summary_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def edit_promo_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, promo_id: int):
        """Admin: Show editing options for specific promo"""
        user_id = update.effective_user.id
        
        # Get the promo data
        all_promos = self.content_manager.get_all_promos()
        promo = next((p for p in all_promos if p["id"] == promo_id), None)
        
        if not promo:
            await update.callback_query.edit_message_text(f"❌ Promo {promo_id} not found")
            return
        
        # Store the promo data for editing
        if user_id not in self.pending_messages:
            self.pending_messages[user_id] = {}
        
        self.pending_messages[user_id] = {
            "edit_id": promo_id,
            "current_promo": promo,
            "edit_mode": "menu"
        }
        
        # Show edit menu
        edit_text = f"📝 **Edit Promo {promo_id}**\n\nWhat do you want to edit?"
        
        keyboard = [
            [
                InlineKeyboardButton("📝 Text", callback_data=f"edit_text_{promo_id}"),
                InlineKeyboardButton("🔗 Link", callback_data=f"edit_link_{promo_id}")
            ],
            [
                InlineKeyboardButton("🖼️ Image", callback_data=f"edit_image_{promo_id}"),
                InlineKeyboardButton("🔄 Replace All", callback_data=f"edit_all_{promo_id}")
            ],
            [
                InlineKeyboardButton("← Back to Promo", callback_data="back_to_promo")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text=edit_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def toggle_promo_status_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, promo_id: int):
        """Admin: Toggle promo status and update current message"""
        promos = self.content_manager.get_all_promos()
        promo = next((p for p in promos if p["id"] == promo_id), None)
        
        if not promo:
            await update.callback_query.edit_message_text(f"❌ Promo {promo_id} not found")
            return
        
        old_status = promo["status"]
        new_status = "inactive" if old_status == "active" else "active"
        
        if await self.content_manager.update_promo_status(promo_id, new_status):
            # Return directly to promo view with success message in caption/text
            user_id = update.effective_user.id
            session = self.get_or_create_session(user_id)
            
            # Update promo data and add success message
            updated_promos = self.content_manager.get_active_promos()
            if updated_promos and session.current_index < len(updated_promos):
                await self.show_promo_with_message(update, context, user_id, session.current_index, 
                                                 f"✅ Promo {promo_id}: {old_status} → {new_status}")
            else:
                # If no promos or current index invalid, go to first promo
                if updated_promos:
                    session.current_index = 0
                    await self.show_promo_with_message(update, context, user_id, 0, 
                                                     f"✅ Promo {promo_id}: {old_status} → {new_status}")
                else:
                    await update.callback_query.edit_message_text("📭 No promos available.")
        else:
            # Show error but still return to promo view
            user_id = update.effective_user.id
            session = self.get_or_create_session(user_id)
            await self.show_promo_with_message(update, context, user_id, session.current_index, 
                                             f"❌ Failed to update promo {promo_id}")
    
    async def show_promo_with_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, index: int, status_message: str):
        """Show promo with an additional status message"""
        active_promos = self.content_manager.get_active_promos()
        
        if not active_promos or index < 0 or index >= len(active_promos):
            await update.callback_query.edit_message_text(f"{status_message}\n\n📭 No promos available.")
            return
        
        promo = active_promos[index]
        session = self.get_or_create_session(user_id)
        session.current_index = index
        
        # Add status message to promo text
        display_text = f"{status_message}\n\n{promo['text']}"
        
        # Create navigation keyboard (same as show_promo)
        keyboard = []
        
        # Navigation row
        nav_buttons = []
        nav_buttons.append(InlineKeyboardButton("← Previous", callback_data="prev"))
        
        if promo["link"]:
            nav_buttons.append(InlineKeyboardButton("🔗 Visit Link", callback_data=f"visit_{promo['id']}"))
        
        nav_buttons.append(InlineKeyboardButton("Next →", callback_data="next"))
        keyboard.append(nav_buttons)
        
        # Admin panel row
        if session.is_admin:
            admin_buttons = []
            admin_buttons.append(InlineKeyboardButton("📋 List", callback_data="admin_list"))
            admin_buttons.append(InlineKeyboardButton("📝 Edit", callback_data=f"admin_edit_{promo['id']}"))
            admin_buttons.append(InlineKeyboardButton("🔄 Toggle", callback_data=f"admin_toggle_{promo['id']}"))
            admin_buttons.append(InlineKeyboardButton("🗑️ Delete", callback_data=f"admin_delete_{promo['id']}"))
            keyboard.append(admin_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
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
            logger.error(f"Failed to show promo with message: {e}")
    
    async def delete_promo_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, promo_id: int):
        """Admin: Delete promo with confirmation"""
        # Show confirmation buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_delete_{promo_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="back_to_promo")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            f"🗑️ **Delete Promo {promo_id}?**\n\nThis action cannot be undone.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        """Publish pending message with given status"""
        pending = self.pending_messages.get(user_id)
        if not pending:
            return
        
        edit_id = pending.get("edit_id")
        
        if edit_id:
            # This is an edit operation - update existing promo
            # Note: We'll need to add update_promo method to ContentManager
            await update.callback_query.message.reply_text("Edit functionality coming soon!")
        else:
            # This is a new promo
            promo_id = await self.content_manager.add_promo(
                text=pending["text"],
                image_file_id=pending["image_file_id"],
                link=pending["link"],
                created_by=pending["created_by"]
            )
            
            if promo_id:
                await self.content_manager.update_promo_status(promo_id, status)
                await update.callback_query.message.reply_text(
                    f"✅ Promo {promo_id} {'published' if status == 'active' else 'saved as draft'}!"
                )
                del self.pending_messages[user_id]
            else:
                await update.callback_query.message.reply_text("❌ Failed to save promo.")


def create_application():
    """Create and configure the bot application"""
    # Validate environment
    required_vars = ["MAIN_BOT_TOKEN", "GOOGLE_SPREADSHEET_ID"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        return None
    
    # Get token
    token = os.getenv("MAIN_BOT_TOKEN")
    
    # Initialize content manager
    content_manager = ContentManager(
        os.getenv("GOOGLE_SHEETS_CREDENTIALS", ""), 
        os.getenv("GOOGLE_SPREADSHEET_ID")
    )
    
    # Create bot instance
    bot = LoyaltyBot(content_manager)
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add error handler
    async def error_handler(update, context):
        logger.error(f"Bot error: {context.error}")
        if update:
            logger.error(f"Update that caused error: {update}")
    
    application.add_error_handler(error_handler)
    
    # Add handlers
    # Common commands
    application.add_handler(CommandHandler("start", bot.start))
    
    # Navigation callbacks (for all users)
    application.add_handler(CallbackQueryHandler(bot.navigation, pattern="^(prev|next)$"))
    application.add_handler(CallbackQueryHandler(bot.visit_link, pattern="^visit_"))
    
    # Back to promo callback (for admins)
    application.add_handler(CallbackQueryHandler(bot.back_to_promo, pattern="^back_to_promo$"))
    
    # Admin commands
    application.add_handler(CommandHandler("list", bot.list_promos))
    application.add_handler(CommandHandler("toggle", bot.toggle_command))
    application.add_handler(CommandHandler("delete", bot.delete_command))
    application.add_handler(CommandHandler("edit", bot.edit_command))
    
    # Admin callbacks
    application.add_handler(CallbackQueryHandler(bot.admin_callback_handler, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(bot.admin_callback_handler, pattern="^confirm_delete_"))
    
    # Admin message handler (for creating/editing promos)
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, bot.admin_message_handler))
    
    logger.info("Bot application created successfully")
    return application


# For development
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    app = create_application()
    if app:
        print("Starting bot in polling mode...")
        app.run_polling()
    else:
        print("Failed to create application")