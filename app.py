import logging
import os
import asyncio
import time
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import RetryAfter, TelegramError

from content_manager import ContentManager
from main_bot import MainBot
from admin_bot import AdminBot

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variables
flask_app = None
main_app = None
admin_app = None
webhooks_initialized = False

async def initialize_webhooks():
    """Initialize webhooks with proper delays"""
    global webhooks_initialized
    
    if webhooks_initialized:
        return True
        
    try:
        app_name = os.getenv("HEROKU_APP_NAME", "bc-loyalty-bot")
        app_url = f"https://{app_name}.herokuapp.com"
        
        logger.info("Starting webhook initialization...")
        
        # Initialize main bot webhook
        main_webhook_url = f"{app_url}/webhook/main"
        await main_app.bot.set_webhook(main_webhook_url)
        logger.info(f"Main bot webhook set: {main_webhook_url}")
        
        # Wait between webhook calls to avoid rate limiting
        await asyncio.sleep(3)
        
        # Initialize admin bot webhook
        admin_webhook_url = f"{app_url}/webhook/admin"
        await admin_app.bot.set_webhook(admin_webhook_url)
        logger.info(f"Admin bot webhook set: {admin_webhook_url}")
        
        webhooks_initialized = True
        logger.info("All webhooks initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize webhooks: {e}")
        return False

def create_app():
    """Create and configure Flask app"""
    global flask_app, main_app, admin_app
    
    # Check environment variables
    main_token = os.getenv("MAIN_BOT_TOKEN")
    admin_token = os.getenv("ADMIN_BOT_TOKEN")
    
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
    
    # Create bot applications (but don't set webhooks yet)
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
    
    # Initialize applications (without webhooks)
    async def init_apps():
        try:
            logger.info("Initializing bot applications...")
            await main_app.initialize()
            logger.info("Main app initialized")
            await admin_app.initialize()
            logger.info("Admin app initialized")
            logger.info("Bot applications ready (webhooks will be set on first request)")
        except Exception as e:
            logger.error(f"Failed to initialize apps: {e}")
            raise
    
    # Run basic initialization
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(init_apps())
        loop.close()
        logger.info("Bot initialization completed successfully")
    except Exception as e:
        logger.error(f"Critical error during initialization: {e}")
    
    # Routes
    @flask_app.route("/webhook/main", methods=["POST"])
    def main_webhook():
        """Handle main bot webhook"""
        try:
            # Lazy webhook initialization on first request
            if not webhooks_initialized:
                logger.info("Initializing webhooks on first request...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(initialize_webhooks())
                loop.close()
            
            data = request.get_json()
            if not data:
                return "OK"
                
            update = Update.de_json(data, main_app.bot)
            
            # Process update
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(main_app.process_update(update))
            finally:
                loop.close()
            
            return "OK"
        except Exception as e:
            logger.error(f"Main webhook error: {e}")
            return "ERROR", 500
    
    @flask_app.route("/webhook/admin", methods=["POST"])
    def admin_webhook():
        """Handle admin bot webhook"""
        try:
            # Lazy webhook initialization on first request
            if not webhooks_initialized:
                logger.info("Initializing webhooks on first request...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(initialize_webhooks())
                loop.close()
            
            data = request.get_json()
            if not data:
                return "OK"
                
            update = Update.de_json(data, admin_app.bot)
            
            # Process update
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(admin_app.process_update(update))
            finally:
                loop.close()
            
            return "OK"
        except Exception as e:
            logger.error(f"Admin webhook error: {e}")
            return "ERROR", 500
    
    @flask_app.route("/init-webhooks", methods=["POST"])
    def manual_init_webhooks():
        """Manual webhook initialization endpoint"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(initialize_webhooks())
            loop.close()
            
            if success:
                return jsonify({"status": "success", "message": "Webhooks initialized"})
            else:
                return jsonify({"status": "error", "message": "Failed to initialize webhooks"}), 500
        except Exception as e:
            logger.error(f"Manual webhook init error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    @flask_app.route("/", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return "BC Loyalty Bot is running!"
    
    @flask_app.route("/status", methods=["GET"])
    def status():
        """Status endpoint"""
        try:
            return {
                "status": "running",
                "webhooks_initialized": webhooks_initialized,
                "main_bot": f"@{main_app.bot.username}" if hasattr(main_app.bot, "username") else "unknown",
                "admin_bot": f"@{admin_app.bot.username}" if hasattr(admin_app.bot, "username") else "unknown",
                "active_promos": len(content_manager.get_active_promos()),
                "total_promos": len(content_manager.get_all_promos())
            }
        except Exception as e:
            logger.error(f"Status endpoint error: {e}")
            return {"status": "error", "message": str(e)}, 500
    
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