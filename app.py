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
main_bot = None
admin_bot = None
webhook_manager = None

def validate_environment():
    """Validate required environment variables"""
    required_vars = {
        "MAIN_BOT_TOKEN": "Main bot token from @BotFather",
        "ADMIN_BOT_TOKEN": "Admin bot token from @BotFather",
        "GOOGLE_SPREADSHEET_ID": "Google Sheets spreadsheet ID",
        "HEROKU_APP_NAME": "Heroku app name for webhook URLs"
    }
    
    missing_vars = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing_vars.append(f"  {var}: {description}")
    
    if missing_vars:
        error_msg = "Missing required environment variables:\n" + "\n".join(missing_vars)
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # Optional but recommended
    if not os.getenv("GOOGLE_SHEETS_CREDENTIALS"):
        logger.warning("GOOGLE_SHEETS_CREDENTIALS not set - Google Sheets integration will not work")

def create_app():
    """Create and configure Flask app with proper delegation"""
    global flask_app, main_app, admin_app, content_manager, main_bot, admin_bot, webhook_manager
    
    try:
        # Validate environment first
        validate_environment()
        
        # Get tokens
        main_token = os.getenv("MAIN_BOT_TOKEN")
        admin_token = os.getenv("ADMIN_BOT_TOKEN")
        
        logger.info("Creating Flask application...")
        
        # Create Flask app
        flask_app = Flask(__name__)
        
        # Initialize content manager
        logger.info("Initializing content manager...")
        content_manager = ContentManager(
            os.getenv("GOOGLE_SHEETS_CREDENTIALS", ""), 
            os.getenv("GOOGLE_SPREADSHEET_ID")
        )
        
        # Create bot handler instances
        logger.info("Creating bot handlers...")
        main_bot = MainBot(content_manager)
        admin_bot = AdminBot(content_manager)
        
        # Create bot applications
        logger.info("Creating bot applications...")
        main_app = Application.builder().token(main_token).build()
        admin_app = Application.builder().token(admin_token).build()
        
        # Create webhook manager
        logger.info("Creating webhook manager...")
        webhook_manager = WebhookManager(main_app, admin_app)
        
        # Register bot handlers
        register_bot_handlers()
        
        # Initialize applications asynchronously
        logger.info("Initializing bot applications...")
        async def init_apps():
            try:
                await main_app.initialize()
                logger.info("Main app initialized")
                await admin_app.initialize()
                logger.info("Admin app initialized")
                
                # Initialize webhooks
                logger.info("Setting up webhooks...")
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
        
        # Register Flask routes
        register_flask_routes()
        
        logger.info("Flask app created successfully")
        return flask_app
        
    except Exception as e:
        logger.error(f"Failed to create Flask app: {e}")
        return None

def register_bot_handlers():
    """Register all bot handlers with their respective applications"""
    logger.info("Registering bot handlers...")
    
    # Add error handlers first
    async def error_handler(update, context):
        """Handle errors in bot processing"""
        logger.error(f"Bot error: {context.error}")
        if update:
            logger.error(f"Update that caused error: {update}")
        # Don't re-raise the error to prevent crashes
    
    main_app.add_error_handler(error_handler)
    admin_app.add_error_handler(error_handler)
    
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
    
    logger.info("Bot handlers registered successfully")

def register_flask_routes():
    """Register all Flask routes with delegation to appropriate handlers"""
    
    # ===== WEBHOOK ROUTES - Delegate to WebhookManager =====
    @flask_app.route("/webhook/main", methods=["POST"])
    def main_webhook():
        """Main bot webhook endpoint - delegates to WebhookManager"""
        return webhook_manager.handle_main_webhook(request)
    
    @flask_app.route("/webhook/admin", methods=["POST"])
    def admin_webhook():
        """Admin bot webhook endpoint - delegates to WebhookManager"""
        return webhook_manager.handle_admin_webhook(request)
    
    @flask_app.route("/webhook-health", methods=["GET"])
    def webhook_health():
        """Webhook health check - delegates to WebhookManager"""
        return webhook_manager.handle_webhook_health()

    @flask_app.route("/init-webhooks", methods=["POST"])
    def manual_init_webhooks():
        """Manual webhook initialization - delegates to WebhookManager"""
        return webhook_manager.handle_manual_init()
    
    # ===== GENERAL ROUTES - Handle directly =====
    @flask_app.route("/", methods=["GET"])
    def health_check():
        """Basic health check endpoint"""
        return jsonify({
            "status": "running",
            "service": "BC Loyalty Bot",
            "message": "Service is operational"
        })
    
    @flask_app.route("/status", methods=["GET"])
    def status():
        """Comprehensive status endpoint"""
        try:
            # Get webhook status from WebhookManager
            webhook_status = webhook_manager.get_status()
            
            # Get bot information
            main_bot_info = "unknown"
            admin_bot_info = "unknown"
            
            try:
                if main_app and hasattr(main_app.bot, "username"):
                    main_bot_info = f"@{main_app.bot.username}"
            except Exception as e:
                logger.warning(f"Could not get main bot info: {e}")
            
            try:
                if admin_app and hasattr(admin_app.bot, "username"):
                    admin_bot_info = f"@{admin_app.bot.username}"
            except Exception as e:
                logger.warning(f"Could not get admin bot info: {e}")
            
            # Get content statistics
            active_promos = 0
            total_promos = 0
            auth_users = 0
            
            try:
                if content_manager:
                    active_promos = len(content_manager.get_active_promos())
                    total_promos = len(content_manager.get_all_promos())
                    auth_users = len(content_manager.auth_cache)
            except Exception as e:
                logger.warning(f"Could not get content stats: {e}")
            
            return jsonify({
                "status": "running",
                "timestamp": "2024-01-01T00:00:00Z",  # You might want to add actual timestamp
                "bots": {
                    "main_bot": main_bot_info,
                    "admin_bot": admin_bot_info
                },
                "content": {
                    "active_promos": active_promos,
                    "total_promos": total_promos,
                    "authorized_users": auth_users
                },
                "webhooks": webhook_status,
                "environment": {
                    "heroku_app": os.getenv("HEROKU_APP_NAME", "not_set"),
                    "google_sheets_configured": bool(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
                }
            })
            
        except Exception as e:
            logger.error(f"Status endpoint error: {e}")
            return jsonify({
                "status": "error", 
                "message": str(e)
            }), 500
    
    @flask_app.route("/content/refresh", methods=["POST"])
    def refresh_content():
        """Force content cache refresh - delegates to ContentManager"""
        try:
            # Run async refresh in sync context
            async def do_refresh():
                return await content_manager.refresh_cache(force=True)
            
            # Execute async function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(do_refresh())
            loop.close()
            
            if success:
                return jsonify({
                    "status": "success",
                    "message": "Content cache refreshed",
                    "active_promos": len(content_manager.get_active_promos()),
                    "total_promos": len(content_manager.get_all_promos())
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "Failed to refresh content cache"
                }), 500
                
        except Exception as e:
            logger.error(f"Content refresh error: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500
    
    # ===== ERROR HANDLERS =====
    @flask_app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors"""
        return jsonify({
            "status": "error",
            "message": "Endpoint not found",
            "available_endpoints": [
                "/",
                "/status", 
                "/webhook/main",
                "/webhook/admin",
                "/webhook-health",
                "/init-webhooks",
                "/content/refresh"
            ]
        }), 404
    
    @flask_app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        logger.error(f"Internal server error: {error}")
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500
    
    logger.info("Flask routes registered successfully")

def main():
    """Run Flask app with development server"""
    global flask_app
    
    logger.info("Starting BC Loyalty Bot...")
    
    flask_app = create_app()
    
    if flask_app:
        port = int(os.getenv("PORT", 5000))
        logger.info(f"Starting Flask development server on port {port}...")
        logger.info(f"Available endpoints:")
        logger.info(f"  Health: http://localhost:{port}/")
        logger.info(f"  Status: http://localhost:{port}/status")
        logger.info(f"  Webhook Health: http://localhost:{port}/webhook-health")
        
        flask_app.run(host="0.0.0.0", port=port, debug=False)
    else:
        logger.error("Failed to create Flask app. Check your environment variables.")
        exit(1)

# Create app for Gunicorn (production)
logger.info("Creating Flask app for production...")
flask_app = create_app()

if not flask_app:
    logger.error("Failed to create Flask app for production")
    exit(1)

if __name__ == "__main__":
    main()