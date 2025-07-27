import logging
import os
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
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
webhook_manager = None

def create_app():
    """Create and configure Flask app"""
    global flask_app, main_app, admin_app, content_manager, webhook_manager
    
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
    
    # Create bot applications
    main_app = Application.builder().token(main_token).build()
    admin_app = Application.builder().token(admin_token).build()
    
    # Create webhook manager
    webhook_manager = WebhookManager(main_app, admin_app)
    
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
    
    # Initialize applications and check webhooks at startup
    async def init_apps():
        try:
            logger.info("Initializing bot applications...")
            await main_app.initialize()
            logger.info("Main app initialized")
            await admin_app.initialize()
            logger.info("Admin app initialized")
            
            # Check and configure webhooks at startup
            logger.info("Checking webhook configuration at startup...")
            webhook_success = await webhook_manager.check_and_initialize_webhooks()
            if webhook_success:
                logger.info("Webhook configuration completed successfully")
            else:
                logger.warning("Webhook configuration failed, but continuing startup")
            
            logger.info("Bot applications ready")
        except Exception as e:
            logger.error(f"Failed to initialize apps: {e}")
            raise
    
    # Run initialization
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(init_apps())
        loop.close()
        logger.info("Bot initialization completed successfully")
    except Exception as e:
        logger.error(f"Critical error during initialization: {e}")
        return None
    
    # Routes - delegate to WebhookManager
    @flask_app.route("/webhook/main", methods=["POST"])
    def main_webhook():
        return webhook_manager.handle_main_webhook()
    
    @flask_app.route("/webhook/admin", methods=["POST"])
    def admin_webhook():
        return webhook_manager.handle_admin_webhook()
    
    @flask_app.route("/webhook-health", methods=["GET"])
    def webhook_health():
        return webhook_manager.handle_webhook_health()

    @flask_app.route("/init-webhooks", methods=["POST"])
    def manual_init_webhooks():
        return webhook_manager.handle_manual_init()
    
    @flask_app.route("/", methods=["GET"])
    def health_check():
        return "BC Loyalty Bot is running!"
    
    @flask_app.route("/status", methods=["GET"])
    def status():
        try:
            webhook_status = webhook_manager.get_status()
            return {
                "status": "running",
                "main_bot": f"@{main_app.bot.username}" if main_app and hasattr(main_app.bot, "username") else "unknown",
                "admin_bot": f"@{admin_app.bot.username}" if admin_app and hasattr(admin_app.bot, "username") else "unknown",
                "active_promos": len(content_manager.get_active_promos()) if content_manager else 0,
                "total_promos": len(content_manager.get_all_promos()) if content_manager else 0,
                **webhook_status
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