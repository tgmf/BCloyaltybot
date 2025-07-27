import logging
import asyncio
import threading
from datetime import datetime
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class UserSession:
    """Track user session for main bot navigation"""
    def __init__(self):
        self.current_index = 0
        self.last_activity = datetime.now()

class MainBot:
    """Main bot handlers for user-facing promo display"""
    
    def __init__(self, content_manager):
        self.content_manager = content_manager
        self.user_sessions: Dict[int, UserSession] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    def handle_webhook_request(self, request, main_app):
        """Handle webhook request for main bot"""
        try:
            # Basic request validation
            if not request.is_json:
                logger.warning("Main webhook: Request is not JSON")
                return "Bad Request", 400
            
            update_data = request.get_json()
            if not update_data:
                logger.warning("Main webhook: Empty request body")
                return "Bad Request", 400
            
            # Process update through main application in background
            self._process_update_async(update_data, main_app)
            
            return "OK", 200
            
        except Exception as e:
            logger.error(f"Main webhook error: {e}")
            return "OK", 200  # Always return 200 to prevent Telegram retries
    
    def _process_update_async(self, update_data, main_app):
        """Process update in background thread"""
        def process():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                update = Update.de_json(update_data, main_app.bot)
                if update:
                    loop.run_until_complete(main_app.process_update(update))
                
                loop.close()
            except Exception as e:
                logger.error(f"Error processing main bot update: {e}")
        
        thread = threading.Thread(target=process, daemon=True)
        thread.start()