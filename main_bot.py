import logging
import asyncio
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class MainBot:
    """Main bot handlers for user-facing promo display"""
    
    def __init__(self, content_manager):
        self.content_manager = content_manager

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main bot start command"""
        user_id = update.effective_user.id
        logger.info(f"User {user_id} started main bot")
        
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
        await self.show_promo(update, context, 0)

    async def show_promo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, index: int):
        """Display promo message with navigation"""
        active_promos = self.content_manager.get_active_promos()
        
        if not active_promos or index < 0 or index >= len(active_promos):
            await update.effective_message.reply_text("No promos available.")
            return
        
        promo = active_promos[index]
        
        # Create navigation keyboard
        keyboard = []
        nav_buttons = []
        
        # Previous button
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("← Previous", callback_data=f"prev_{index}"))
        
        # Visit link button
        if promo["link"]:
            nav_buttons.append(InlineKeyboardButton("🔗 Visit Link", callback_data=f"visit_{promo['id']}"))
        
        # Next button  
        if index < len(active_promos) - 1:
            nav_buttons.append(InlineKeyboardButton("Next →", callback_data=f"next_{index}"))
        
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
        
        active_promos = self.content_manager.get_active_promos()
        
        # Parse current index from callback data
        if query.data.startswith("prev_"):
            current_index = int(query.data.split("_")[1])
            new_index = current_index - 1
            if new_index >= 0:
                await self.show_promo(update, context, new_index)
        elif query.data.startswith("next_"):
            current_index = int(query.data.split("_")[1])
            new_index = current_index + 1
            if new_index < len(active_promos):
                await self.show_promo(update, context, new_index)

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
        """Handle webhook request for main bot - TRUE direct processing"""
        try:
            if not request.is_json:
                return "Bad Request", 400
            
            update_data = request.get_json()
            if not update_data:
                return "Bad Request", 400
            
            # Process directly - no queuing, no threading
            update = Update.de_json(update_data, main_app.bot)
            if update:
                # Create event loop and process immediately
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(main_app.process_update(update))
                finally:
                    loop.close()
            
            return "OK", 200
            
        except Exception as e:
            logger.error(f"Main webhook error: {e}")
            return "OK", 200
    
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