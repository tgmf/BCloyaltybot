import logging
import os
from telegram.ext import Application

from bot import create_application

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def validate_environment():
    """Validate required environment variables"""
    required_vars = {
        "MAIN_BOT_TOKEN": "Main bot token from @BotFather",
        "GOOGLE_SPREADSHEET_ID": "Google Sheets spreadsheet ID"
    }
    
    missing_vars = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing_vars.append(f"  {var}: {description}")
    
    # Check for webhook URL in production
    port = os.getenv("PORT")
    if port and not os.getenv("HEROKU_APP_NAME"):
        missing_vars.append("  HEROKU_APP_NAME: Required for webhook URL in production")
    
    if missing_vars:
        error_msg = "Missing required environment variables:\n" + "\n".join(missing_vars)
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # Optional but recommended
    if not os.getenv("GOOGLE_SHEETS_CREDENTIALS"):
        logger.warning("GOOGLE_SHEETS_CREDENTIALS not set - Google Sheets integration will not work")

def main():
    """Main application entry point"""
    try:
        # Validate environment
        validate_environment()
        
        logger.info("Starting BC Loyalty Bot (Unified)...")
        
        # Create bot application
        application = create_application()
        
        if not application:
            logger.error("Failed to create bot application")
            return
        
        # Determine if we're running locally or on Heroku
        port = os.getenv("PORT")
        
        if port:
            # Production mode - run webhook on Heroku
            logger.info("Running in webhook mode (production)")
            
            # Construct webhook URL for Heroku
            app_name = os.getenv("HEROKU_APP_NAME")
            webhook_url = f"https://{app_name}.herokuapp.com/"
            
            logger.info(f"Setting webhook URL: {webhook_url}")
            
            # Start webhook - PTB handles the event loop internally
            application.run_webhook(
                listen="0.0.0.0",
                port=int(port),
                webhook_url=webhook_url,
                allowed_updates=["message", "callback_query"]
            )
        else:
            # Development mode - run polling
            logger.info("Running in polling mode (development)")
            application.run_polling(
                allowed_updates=["message", "callback_query"]
            )
    
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise

if __name__ == "__main__":
    main()