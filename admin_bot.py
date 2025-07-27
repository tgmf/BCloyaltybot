import logging
import asyncio
import threading
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class AdminBot:
    """Admin bot handlers for content management"""
    
    def __init__(self, content_manager):
        self.content_manager = content_manager
        self.pending_messages: Dict[int, Dict] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await self.show_preview(update, context, user_id)

    async def show_preview(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
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

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def list_promos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def toggle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def delete_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    def handle_webhook_request(self, request, admin_app):
        """Handle webhook request for admin bot"""
        try:
            # Basic request validation
            if not request.is_json:
                logger.warning("Admin webhook: Request is not JSON")
                return "Bad Request", 400
            
            update_data = request.get_json()
            if not update_data:
                logger.warning("Admin webhook: Empty request body")
                return "Bad Request", 400
            
            # Process update through admin application in background
            self._process_update_async(update_data, admin_app)
            
            return "OK", 200
            
        except Exception as e:
            logger.error(f"Admin webhook error: {e}")
            return "OK", 200  # Always return 200 to prevent Telegram retries
    
    def _process_update_async(self, update_data, admin_app):
        """Process update in background thread"""
        def process():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                update = Update.de_json(update_data, admin_app.bot)
                if update:
                    loop.run_until_complete(admin_app.process_update(update))
                
                loop.close()
            except Exception as e:
                logger.error(f"Error processing admin bot update: {e}")
        
        thread = threading.Thread(target=process, daemon=True)
        thread.start()