import logging
import os
import asyncio
from flask import Flask, request, jsonify
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from content_manager import ContentManager
from main_bot import MainBot
from admin_bot import AdminBot
from webhook_manager import WebhookManager

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
content_manager = None
main_bot = None
admin_bot = None
webhook_manager = None

def validate_environment():
    """Validate required environment variables"""
    required_vars = ["MAIN_BOT_TOKEN", "ADMIN_BOT_TOKEN", "GOOGLE_SPREADSHEET_ID", "HEROKU_APP_NAME"]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

def create_app():
    """Create and configure Flask app"""
    global flask_app, main_app, admin_app, content_manager, main_bot, admin_bot, webhook_manager
    
    try:
        validate_environment()
        
        logger.info("Creating Flask application...")
        flask_app = Flask(__name__)
        
        # Initialize content manager
        content_manager = ContentManager(
            os.getenv("GOOGLE_SHEETS_CREDENTIALS", ""), 
            os.getenv("GOOGLE_SPREADSHEET_ID")
        )
        
        # Create bot handlers
        main_bot = MainBot(content_manager)
        admin_bot = AdminBot(content_manager)
        
        # Create bot applications
        main_app = Application.builder().token(os.getenv("MAIN_BOT_TOKEN")).build()
        admin_app = Application.builder().token(os.getenv("ADMIN_BOT_TOKEN")).build()
        
        # Register bot handlers
        register_bot_handlers()
        
        # Initialize bot applications
        run_async_task(init_bot_apps())
        
        # Setup webhooks
        webhook_manager = WebhookManager()
        run_async_task(setup_webhooks())
        
        # Register Flask routes
        register_flask_routes()
        
        logger.info("Flask app created successfully")
        return flask_app
        
    except Exception as e:
        logger.error(f"Failed to create Flask app: {e}")
        return None

async def init_bot_apps():
    """Initialize bot applications"""
    await main_app.initialize()
    await admin_app.initialize()
    logger.info("Bot applications initialized")

async def setup_webhooks():
    """Setup webhooks on startup"""
    success = await webhook_manager.setup_webhooks(main_app.bot, admin_app.bot)
    if success:
        logger.info("Webhooks setup completed")
    else:
        logger.warning("Webhook setup failed")

def register_bot_handlers():
    """Register bot handlers"""
    # Main bot handlers
    main_app.add_handler(CommandHandler("start", main_bot.start))
    main_app.add_handler(CallbackQueryHandler(main_bot.navigation, pattern="^(prev|next)$"))
    main_app.add_handler(CallbackQueryHandler(main_bot.visit_link, pattern="^visit_"))
    
    # Admin bot handlers
    admin_app.add_handler(CommandHandler("start", admin_bot.start))
    admin_app.add_handler(CommandHandler("list", admin_bot.list_promos))
    admin_app.add_handler(CommandHandler("toggle", admin_bot.toggle_command))
    admin_app.add_handler(CommandHandler("delete", admin_bot.delete_command))
    admin_app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, admin_bot.message_handler))
    admin_app.add_handler(CallbackQueryHandler(admin_bot.callback_handler))

def register_flask_routes():
    """Register Flask routes"""
    
    @flask_app.route("/webhook/main", methods=["POST"])
    def main_webhook():
        """Main bot webhook endpoint"""
        return main_bot.handle_webhook_request(request, main_app)
    
    @flask_app.route("/webhook/admin", methods=["POST"])
    def admin_webhook():
        """Admin bot webhook endpoint"""
        return admin_bot.handle_webhook_request(request, admin_app)
    
    @flask_app.route("/", methods=["GET"])
    def health_check():
        """Basic health check"""
        return jsonify({"status": "running", "service": "BC Loyalty Bot"})

def run_async_task(coro):
    """Run async task in sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(coro)
        return result
    finally:
        loop.close()

def main():
    """Run Flask app"""
    global flask_app
    
    flask_app = create_app()
    
    if flask_app:
        port = int(os.getenv("PORT", 5000))
        logger.info(f"Starting Flask server on port {port}")
        flask_app.run(host="0.0.0.0", port=port, debug=False)
    else:
        logger.error("Failed to create Flask app")
        exit(1)

# Create app for production
flask_app = create_app()

if not flask_app:
    logger.error("Failed to create Flask app for production")
    exit(1)

if __name__ == "__main__":
    main()