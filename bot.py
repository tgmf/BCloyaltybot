import logging
import os
import asyncio
from typing import Dict, Optional
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from telegram.error import TelegramError

from content_manager import ContentManager

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        
        # Check authorization by user_id or username
        for phone, auth_data in self.content_manager.auth_cache.items():
            if auth_data.get("user_id") == user_id_str or auth_data.get("username") == username:
                return True
        
        return False
    
    def get_or_create_session(self, user_id: int) -> UserSession:
        """Get or create user session"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSession()
        return self.user_sessions[user_id]
    
    # ===== COMMON COMMANDS =====
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command - shows promos for everyone"""
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
        
        # Send welcome message
        welcome_text = "🎉 Welcome to BC Loyalty!"
        if session.is_admin:
            welcome_text += "\n\n🎛️ *Admin Panel Active*\nYou can use admin commands like /list, /edit, /toggle, /delete"
        
        if not active_promos:
            welcome_text += "\n\nNo promos available at the moment."
            await update.message.reply_text(welcome_text, parse_mode="Markdown")
            logger.warning("No active promos found")
            return
        
        # Show welcome + first promo
        await update.message.reply_text(welcome_text, parse_mode="Markdown")
        await self.show_promo(update, context, user_id, 0)
    
    # ===== PROMO DISPLAY (USER FUNCTIONALITY) =====
    
    async def show_promo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, index: int):
        """Display promo message with navigation"""
        active_promos = self.content_manager.get_active_promos()
        
        if not active_promos or index < 0 or index >= len(active_promos):
            await update.effective_message.reply_text("No promos available.")
            return
        
        promo = active_promos[index]
        session = self.get_or_create_session(user_id)
        session.current_index = index
        
        # Create navigation keyboard
        keyboard = []
        nav_buttons = []
        
        # Previous button
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("← Previous", callback_data="prev"))
        
        # Visit link button
        if promo["link"]:
            nav_buttons.append(InlineKeyboardButton("🔗 Visit Link", callback_data=f"visit_{promo['id']}"))
        
        # Next button  
        if index < len(active_promos) - 1:
            nav_buttons.append(InlineKeyboardButton("Next →", callback_data="next"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send message
        try:
            if promo["image_file_id"]:
                if update.callback_query:
                    # Edit existing message
                    await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(media=promo["image_file_id"], caption=promo["text"]),
                        reply_markup=reply_markup
                    )
                else:
                    # Send new message
                    await update.message.reply_photo(
                        photo=promo["image_file_id"],
                        caption=promo["text"],
                        reply_markup=reply_markup
                    )
            else:
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        text=promo["text"],
                        reply_markup=reply_markup
                    )
                else:
                    await update.message.reply_text(
                        text=promo["text"],
                        reply_markup=reply_markup
                    )
        except TelegramError as e:
            logger.error(f"Failed to show promo: {e}")
    
    async def navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle navigation buttons (prev/next)"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        session = self.get_or_create_session(user_id)
        
        current_index = session.current_index
        active_promos = self.content_manager.get_active_promos()
        
        if query.data == "prev" and current_index > 0:
            await self.show_promo(update, context, user_id, current_index - 1)
        elif query.data == "next" and current_index < len(active_promos) - 1:
            await self.show_promo(update, context, user_id, current_index + 1)
    
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
        
        for promo in all_promos[:10]:  # Limit to 10 to avoid message length issues
            status_emoji = {"active": "✅", "draft": "📄", "inactive": "❌"}.get(promo["status"], "❓")
            
            text = f"{status_emoji} *ID {promo['id']}* (Order: {promo['order']})\n{promo['text'][:100]}..."
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Toggle", callback_data=f"admin_toggle_{promo['id']}"),
                    InlineKeyboardButton("🗑️ Delete", callback_data=f"admin_delete_{promo['id']}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                if promo["image_file_id"]:
                    await update.message.reply_photo(
                        photo=promo["image_file_id"],
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
            except TelegramError as e:
                logger.error(f"Failed to send promo {promo['id']}: {e}")
    
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
        user_id = update.effective_user.id
        
        # Check if user is admin
        user = update.effective_user
        username = user.username or ""
        if not await self.check_admin_access(user_id, username):
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
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        # Check admin access for callback queries
        user = update.effective_user
        username = user.username or ""
        if not await self.check_admin_access(user_id, username):
            await query.message.reply_text("🔐 Access denied.")
            return
        
        if data == "admin_publish":
            await self.publish_pending_message(update, context, user_id, "active")
        elif data == "admin_draft":
            await self.publish_pending_message(update, context, user_id, "draft")
        elif data == "admin_edit":
            await query.message.reply_text("Send the updated message:")
        elif data == "admin_cancel":
            if user_id in self.pending_messages:
                del self.pending_messages[user_id]
            await query.message.reply_text("❌ Operation cancelled.")
        elif data.startswith("admin_toggle_"):
            promo_id = int(data.split("_")[2])
            await self.toggle_promo_status(update, context, promo_id)
        elif data.startswith("admin_delete_"):
            promo_id = int(data.split("_")[2])
            await self.delete_promo(update, context, promo_id)
    
    async def publish_pending_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, status: str):
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
    
    # Admin commands
    application.add_handler(CommandHandler("list", bot.list_promos))
    application.add_handler(CommandHandler("toggle", bot.toggle_command))
    application.add_handler(CommandHandler("delete", bot.delete_command))
    application.add_handler(CommandHandler("edit", bot.edit_command))
    
    # Admin callbacks
    application.add_handler(CallbackQueryHandler(bot.admin_callback_handler, pattern="^admin_"))
    
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