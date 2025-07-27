import logging
import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from content_manager import ContentManager
from main_bot import MainBot
from admin_bot import AdminBot

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global Flask app for Gunicorn
flask_app = None

def create_app():
    """Create and configure Flask app"""
    global flask_app
    
    # Check environment variables
    main_token = os.getenv("MAIN_BOT_TOKEN")
    admin_token = os.getenv("ADMIN_BOT_TOKEN")
    app_name = os.getenv("HEROKU_APP_NAME", "bc-loyalty-bot")
    
    if not main_token or not admin_token:
        logger.error("Bot tokens not provided")
        return None
    
    # Create Flask app
    flask_app = Flask(__name__)
    
    # Shared content manager
    content_manager = ContentManager(
        os.getenv("GOOGLE_SHEETS_CREDENTIALS"), 
        os.getenv("GOOGLE_SPREADSHEET_ID")
    )
    
    # Create bot instances
    main_bot = MainBot(content_manager)
    admin_bot = AdminBot(content_manager)
    
    # Create bot applications
    main_app = Application.builder().token(main_token).build()
    admin_app = Application.builder().token(admin_token).build()
    
    # Add main bot handlers
    main_app.add_handler(CommandHandler("start", main_bot.start))
    main_app.add_handler(CallbackQueryHandler(main_bot.navigation, pattern="^(prev|next)$"))
    main_app.add_handler(CallbackQueryHandler(main_bot.visit_link, pattern="^visit_"))
    
    # Add admin bot handlers
    admin_app.add_handler(CommandHandler("start", admin_bot.start))
    admin_app.add_handler(CommandHandler("list", admin_bot.list_promos))
    admin_app.add_handler(CommandHandler("toggle", admin_bot.toggle_command))
    admin_app.add_handler(CommandHandler("delete", admin_bot.delete_command))
    admin_app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, admin_bot.message_handler))
    admin_app.add_handler(CallbackQueryHandler(admin_bot.callback_handler))
    
    # Initialize applications and set webhooks
    async def init_apps():
        await main_app.initialize()
        await admin_app.initialize()
        
        # Set webhooks
        app_url = f"https://{app_name}.herokuapp.com"
        await main_app.bot.set_webhook(f"{app_url}/webhook/main")
        await admin_app.bot.set_webhook(f"{app_url}/webhook/admin")
        
        logger.info(f"Webhooks set for {app_url}")
        logger.info(f"Main bot: @{main_app.bot.username}")
        logger.info(f"Admin bot: @{admin_app.bot.username}")
    
    # Run initialization
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_apps())
    
    # Webhook routes
    @flask_app.route("/webhook/main", methods=["POST"])
    def main_webhook():
        """Handle main bot webhook"""
        try:
            data = request.get_json()
            logger.info(f"Main webhook received: {data}")
            update = Update.de_json(data, main_app.bot)
            
            # Run async handler in event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main_app.process_update(update))
            loop.close()
            
            return "OK"
        except Exception as e:
            logger.error(f"Main webhook error: {e}")
            return "ERROR", 500
    
    @flask_app.route("/webhook/admin", methods=["POST"])
    def admin_webhook():
        """Handle admin bot webhook"""
        try:
            data = request.get_json()
            logger.info(f"Admin webhook received: {data}")
            update = Update.de_json(data, admin_app.bot)
            
            # Run async handler in event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(admin_app.process_update(update))
            loop.close()
            
            return "OK"
        except Exception as e:
            logger.error(f"Admin webhook error: {e}")
            return "ERROR", 500
    
    @flask_app.route("/", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return "BC Loyalty Bot is running!"
    
    @flask_app.route("/status", methods=["GET"])
    def status():
        """Status endpoint"""
        return {
            "status": "running",
            "main_bot": f"@{main_app.bot.username}" if hasattr(main_app.bot, 'username') else "unknown",
            "admin_bot": f"@{admin_app.bot.username}" if hasattr(admin_app.bot, 'username') else "unknown",
            "active_promos": len(content_manager.get_active_promos()),
            "total_promos": len(content_manager.get_all_promos())
        }
    
    logger.info("Flask app created successfully")
    return flask_app


def main():
    """Run Flask app with development server"""
    global flask_app
    flask_app = create_app()
    
    if flask_app:
        port = int(os.getenv("PORT", 5000))
        logger.info(f"Starting Flask development server on port {port}...")
        flask_app.run(host="0.0.0.0", port=port, debug=False)


# Create app for Gunicorn
flask_app = create_app()

if __name__ == "__main__":
    main()