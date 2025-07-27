import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)
from telegram.error import TelegramError

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ContentManager:
    """Manages promo content via Google Sheets"""
    
    def __init__(self, credentials_json: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.promos_cache = []
        self.auth_cache = {}
        self.last_update = 0
        self.cache_timeout = 300  # 5 minutes
        
        # Initialize Google Sheets client
        try:
            if credentials_json:
                creds_dict = json.loads(credentials_json)
                scope = [
                    "https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                self.client = gspread.authorize(creds)
                self.sheet = self.client.open_by_key(spreadsheet_id)
                logger.info("Google Sheets client initialized successfully")
            else:
                logger.warning("No Google Sheets credentials provided")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            self.client = None

    async def refresh_cache(self, force: bool = False):
        """Refresh content cache from Google Sheets"""
        if not self.client:
            return False
            
        now = datetime.now().timestamp()
        if not force and (now - self.last_update) < self.cache_timeout:
            return True
            
        try:
            # Get promo messages
            promos_sheet = self.sheet.worksheet("promo_messages")
            promos_data = promos_sheet.get_all_records()
            
            self.promos_cache = []
            for row in promos_data:
                if row.get("id"):  # Skip empty rows
                    self.promos_cache.append({
                        "id": int(row["id"]),
                        "text": row.get("text", ""),
                        "image_file_id": row.get("image_file_id", ""),
                        "link": row.get("link", ""),
                        "order": int(row.get("order", 0)),
                        "status": row.get("status", "draft"),
                        "created_by": row.get("created_by", ""),
                        "created_at": row.get("created_at", "")
                    })
            
            # Sort by order
            self.promos_cache.sort(key=lambda x: x["order"])
            
            # Get authorized users
            try:
                auth_sheet = self.sheet.worksheet("authorized_users")
                auth_data = auth_sheet.get_all_records()
                
                self.auth_cache = {}
                for row in auth_data:
                    if row.get("phone_number"):
                        self.auth_cache[row["phone_number"]] = {
                            "user_id": row.get("user_id", ""),
                            "username": row.get("username", ""),
                            "added_at": row.get("added_at", "")
                        }
            except Exception as e:
                logger.warning(f"Auth sheet not found or error: {e}")
            
            self.last_update = now
            logger.info(f"Cache refreshed: {len(self.promos_cache)} promos, {len(self.auth_cache)} auth users")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh cache: {e}")
            return False

    def get_active_promos(self) -> List[Dict]:
        """Get all active promo messages"""
        return [p for p in self.promos_cache if p["status"] == "active"]
    
    def get_all_promos(self) -> List[Dict]:
        """Get all promo messages"""
        return self.promos_cache.copy()
    
    def is_authorized(self, phone_number: str) -> bool:
        """Check if phone number is authorized"""
        return phone_number in self.auth_cache
    
    async def add_promo(self, text: str, image_file_id: str, link: str, created_by: str, order: Optional[int] = None) -> int:
        """Add new promo message"""
        if not self.client:
            return 0
            
        try:
            promos_sheet = self.sheet.worksheet("promo_messages")
            
            # Get next ID
            existing_data = promos_sheet.get_all_records()
            next_id = max([int(row.get("id", 0)) for row in existing_data], default=0) + 1
            
            # Get next order if not specified
            if order is None:
                order = max([int(row.get("order", 0)) for row in existing_data], default=0) + 10
            
            # Add new row
            new_row = [
                next_id, text, image_file_id, link, order, 
                "draft", created_by, datetime.now().isoformat()
            ]
            promos_sheet.append_row(new_row)
            
            # Refresh cache
            await self.refresh_cache(force=True)
            
            logger.info(f"Added promo {next_id} by {created_by}")
            return next_id
            
        except Exception as e:
            logger.error(f"Failed to add promo: {e}")
            return 0

    async def update_promo_status(self, promo_id: int, status: str) -> bool:
        """Update promo status (active/draft/inactive)"""
        if not self.client:
            return False
            
        try:
            promos_sheet = self.sheet.worksheet("promo_messages")
            records = promos_sheet.get_all_records()
            
            for i, row in enumerate(records, start=2):  # Start from row 2 (skip header)
                if int(row.get("id", 0)) == promo_id:
                    promos_sheet.update(f"F{i}", status)  # Column F is status
                    await self.refresh_cache(force=True)
                    logger.info(f"Updated promo {promo_id} status to {status}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to update promo status: {e}")
            return False

    async def delete_promo(self, promo_id: int) -> bool:
        """Delete promo message"""
        if not self.client:
            return False
            
        try:
            promos_sheet = self.sheet.worksheet("promo_messages")
            records = promos_sheet.get_all_records()
            
            for i, row in enumerate(records, start=2):  # Start from row 2 (skip header)
                if int(row.get("id", 0)) == promo_id:
                    promos_sheet.delete_rows(i)
                    await self.refresh_cache(force=True)
                    logger.info(f"Deleted promo {promo_id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete promo: {e}")
            return False


class UserSession:
    """Track user session for main bot navigation"""
    def __init__(self):
        self.current_index = 0
        self.last_activity = datetime.now()


class BotApplication:
    """Main application handling both bots"""
    
    def __init__(self):
        # Environment variables
        self.main_bot_token = os.getenv("MAIN_BOT_TOKEN")
        self.admin_bot_token = os.getenv("ADMIN_BOT_TOKEN")
        self.google_creds = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        self.spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
        
        # Content manager
        self.content_manager = ContentManager(self.google_creds, self.spreadsheet_id)
        
        # User sessions for main bot
        self.user_sessions: Dict[int, UserSession] = {}
        
        # Pending messages for admin bot
        self.pending_messages: Dict[int, Dict] = {}

    async def setup_applications(self):
        """Setup both bot applications"""
        # Main bot application
        self.main_app = Application.builder().token(self.main_bot_token).build()
        
        # Main bot handlers
        self.main_app.add_handler(CommandHandler("start", self.main_start))
        self.main_app.add_handler(CallbackQueryHandler(self.main_navigation, pattern="^(prev|next)$"))
        self.main_app.add_handler(CallbackQueryHandler(self.main_visit_link, pattern="^visit_"))
        
        # Admin bot application  
        self.admin_app = Application.builder().token(self.admin_bot_token).build()
        
        # Admin bot handlers
        self.admin_app.add_handler(CommandHandler("start", self.admin_start))
        self.admin_app.add_handler(CommandHandler("list", self.admin_list))
        self.admin_app.add_handler(CommandHandler("toggle", self.admin_toggle))
        self.admin_app.add_handler(CommandHandler("delete", self.admin_delete))
        self.admin_app.add_handler(MessageHandler(
            filters.TEXT | filters.PHOTO, self.admin_message_handler
        ))
        self.admin_app.add_handler(CallbackQueryHandler(self.admin_callback_handler))
        
        # Initial cache refresh
        await self.content_manager.refresh_cache(force=True)
        
        return self.main_app, self.admin_app

    # ===== MAIN BOT HANDLERS =====
    
    async def main_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main bot start command"""
        user_id = update.effective_user.id
        logger.info(f"User {user_id} started main bot")
        
        # Initialize user session
        self.user_sessions[user_id] = UserSession()
        
        # Refresh content
        await self.content_manager.refresh_cache()
        
        # Get active promos
        active_promos = self.content_manager.get_active_promos()
        logger.info(f"Found {len(active_promos)} active promos")
        
        if not active_promos:
            await update.message.reply_text("🎉 Welcome! No promos available at the moment.")
            logger.warning("No active promos found")
            return
        
        # Show first promo
        logger.info(f"Showing first promo to user {user_id}")
        await self.show_promo(update, context, user_id, 0)

    async def show_promo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, index: int):
        """Display promo message with navigation"""
        active_promos = self.content_manager.get_active_promos()
        
        if not active_promos or index < 0 or index >= len(active_promos):
            await update.effective_message.reply_text("No promos available.")
            return
        
        promo = active_promos[index]
        self.user_sessions[user_id].current_index = index
        
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

    async def main_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle navigation buttons"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSession()
        
        current_index = self.user_sessions[user_id].current_index
        active_promos = self.content_manager.get_active_promos()
        
        if query.data == "prev" and current_index > 0:
            await self.show_promo(update, context, user_id, current_index - 1)
        elif query.data == "next" and current_index < len(active_promos) - 1:
            await self.show_promo(update, context, user_id, current_index + 1)

    async def main_visit_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle visit link button"""
        query = update.callback_query
        await query.answer()
        
        promo_id = int(query.data.split("_")[1])
        active_promos = self.content_manager.get_active_promos()
        
        for promo in active_promos:
            if promo["id"] == promo_id and promo["link"]:
                await query.message.reply_text(f"🔗 Visit: {promo['link']}")
                break

    # ===== ADMIN BOT HANDLERS =====
    
    async def admin_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin bot start command"""
        user = update.effective_user
        user_id = str(user.id)
        username = user.username or ""
        
        # Refresh auth cache
        await self.content_manager.refresh_cache()
        
        # Check authorization by user_id or username
        is_authorized = False
        for phone, auth_data in self.content_manager.auth_cache.items():
            if auth_data.get("user_id") == user_id or auth_data.get("username") == username:
                is_authorized = True
                break
        
        if not is_authorized:
            await update.message.reply_text(
                "🔐 Access denied. Contact administrator to get authorized.\n"
                f"Your User ID: `{user_id}`\n"
                f"Your Username: @{username}" if username else f"Your Username: Not set",
                parse_mode="Markdown"
            )
            return
        
        welcome_text = (
            "🎛️ *Admin Panel*\n\n"
            "Send a message (text + image + link) to create new promo\n\n"
            "Commands:\n"
            "• /list - View all promos\n"
            "• /toggle {id} - Toggle promo status\n"
            "• /delete {id} - Delete promo"
        )
        
        await update.message.reply_text(welcome_text, parse_mode="Markdown")

    async def admin_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new message from admin"""
        user_id = update.effective_user.id
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
        
        # Store pending message
        self.pending_messages[user_id] = {
            "text": text,
            "image_file_id": image_file_id,
            "link": link,
            "created_by": str(user_id)
        }
        
        # Show preview
        await self.show_admin_preview(update, context, user_id)

    async def show_admin_preview(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """Show preview of pending message"""
        pending = self.pending_messages.get(user_id)
        if not pending:
            return
        
        preview_text = f"📱 *Preview:*\n\n{pending['text']}"
        if pending['link']:
            preview_text += f"\n\n🔗 Link: {pending['link']}"
        
        keyboard = [
            [
                InlineKeyboardButton("📤 Publish", callback_data="publish"),
                InlineKeyboardButton("📝 Edit", callback_data="edit"),
                InlineKeyboardButton("📄 Draft", callback_data="draft")
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
            logger.error(f"Failed to show preview: {e}")

    async def admin_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin callback queries"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data == "publish":
            await self.publish_pending_message(update, context, user_id, "active")
        elif data == "draft":
            await self.publish_pending_message(update, context, user_id, "draft")
        elif data == "edit":
            await query.message.reply_text("Send the updated message:")
        elif data.startswith("toggle_"):
            promo_id = int(data.split("_")[1])
            await self.toggle_promo_status(update, context, promo_id)
        elif data.startswith("delete_"):
            promo_id = int(data.split("_")[1])
            await self.delete_promo(update, context, promo_id)

    async def publish_pending_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, status: str):
        """Publish pending message with given status"""
        pending = self.pending_messages.get(user_id)
        if not pending:
            return
        
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

    async def admin_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all promos with management buttons"""
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
                    InlineKeyboardButton("🔄 Toggle", callback_data=f"toggle_{promo['id']}"),
                    InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{promo['id']}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
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

    async def admin_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle promo status command"""
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

    async def admin_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete promo command"""
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


async def main():
    """Run both bots"""
    app = BotApplication()
    
    if not app.main_bot_token or not app.admin_bot_token:
        logger.error("Bot tokens not provided")
        return
    
    # Setup applications
    main_app, admin_app = await app.setup_applications()
    
    # Run both bots
    logger.info("Starting both bots...")
    
    try:
        # Run both applications concurrently
        await asyncio.gather(
            main_app.run_polling(drop_pending_updates=True),
            admin_app.run_polling(drop_pending_updates=True)
        )
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Error running bots: {e}")
    finally:
        logger.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())