import logging
import os
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from telegram import Update

from content_manager import ContentManager
from user_handlers import start_command, navigation_handler
from admin_handlers import (
    admin_message_handler, admin_callback_handler, back_to_promo_handler, login_command, logout_command
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def create_application():
    """Create and configure the bot application"""
    try:
        # Get token
        dev_token = os.getenv("DEV_BOT_TOKEN")
        if dev_token:
            token = dev_token
            logger.info("Using DEV_BOT_TOKEN for development environment")
        else:
            token = os.getenv("MAIN_BOT_TOKEN")

        # Initialize content manager
        content_manager = ContentManager(
            os.getenv("GOOGLE_SHEETS_CREDENTIALS", ""), 
            os.getenv("GOOGLE_SPREADSHEET_ID")
        )
        
        # Create application
        application = Application.builder().token(token).build()
        
        # Register handlers
        register_all_handlers(application, content_manager)
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        logger.info("Bot application created successfully (stateless mode)")
        return application
        
    except Exception as e:
        logger.error(f"Failed to create application: {e}")
        return None

def register_all_handlers(application: Application, content_manager: ContentManager):
    """Register all command and callback handlers"""
    
    # ===== COMMON COMMANDS =====
    
    # Start command (available to all users)
    application.add_handler(
        CommandHandler("start", lambda update, context: start_command(update, context, content_manager))
    )
    
    # ===== USER NAVIGATION CALLBACKS =====
    
    # Navigation buttons (prev/next) - stateless with embedded state
    application.add_handler(
        CallbackQueryHandler(
            lambda update, context: navigation_handler(update, context, content_manager),
            pattern="^(prev|next)"
        )
    )
    
    # ===== ADMIN COMMANDS =====
    
    # Login command for admin access
    application.add_handler(
        CommandHandler("login", lambda update, context: login_command(update, context, content_manager))
    )
    
    # Logout command for admins
    application.add_handler(
        CommandHandler("logout", lambda update, context: logout_command(update, context, content_manager))
    )
    
    # ===== ADMIN CALLBACK HANDLERS =====
    
    # Back to promo button (admin only, camelCase)
    application.add_handler(
        CallbackQueryHandler(
            lambda update, context: back_to_promo_handler(update, context, content_manager),
            pattern="^backToPromo"
        )
    )

    # Admin callback handlers (all admin* camelCase actions)
    application.add_handler(
        CallbackQueryHandler(
            lambda update, context: admin_callback_handler(update, context, content_manager),
            pattern="^admin[A-Z]"
        )
    )

    # Confirmation callbacks (confirm* camelCase)
    application.add_handler(
        CallbackQueryHandler(
            lambda update, context: admin_callback_handler(update, context, content_manager),
            pattern="^confirm[A-Z]"
        )
    )

    # Edit dialog callbacks (edit* camelCase)
    application.add_handler(
        CallbackQueryHandler(
            lambda update, context: admin_callback_handler(update, context, content_manager),
            pattern="^edit[A-Z]"
        )
    )
    
    # State-encoded callbacks (state_* pattern for JSON-encoded stateless data)
    application.add_handler(
        CallbackQueryHandler(
            lambda update, context: handle_stateless_callback(update, context, content_manager),
            pattern="^state_"
        )
    )
    
    # ===== MESSAGE HANDLERS =====
    
    # Admin message handler for creating/editing promos
    # This should be last to catch all text/photo messages from admins
    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO,
            lambda update, context: admin_message_handler(update, context, content_manager)
        )
    )
    
    logger.info("All handlers registered successfully (stateless mode)")

async def handle_stateless_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, content_manager):
    """Handle stateless callbacks with JSON-encoded state"""
    # Import here to avoid circular imports
    from state_manager import StateManager
    
    query = update.callback_query
    await query.answer()
    
    # Decode the action and route to appropriate handler
    action, state = StateManager.decode_callback_data(query.data)
    
    logger.info(f"STATELESS CALLBACK: action={action}, state={state}")
    
    # Route based on action (camelCase)
    if action.startswith("admin") or action.startswith("confirm") or action.startswith("edit"):
        await admin_callback_handler(update, context, content_manager)
    elif action in ["prev", "next"]:
        await navigation_handler(update, context, content_manager)
    elif action == "backToPromo":
        await back_to_promo_handler(update, context, content_manager)
    else:
        logger.warning(f"Unknown stateless callback action: {action}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Bot error: {context.error}")
    
    if update:
        logger.error(f"Update that caused error: {update}")
        
        # Try to send error message to user
        try:
            if update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Возникла ошибка при обработке вашего запроса.\n\nПожалуйста, попробуйте еще раз: /start"
                )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")