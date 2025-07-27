import logging
import os
import asyncio

logger = logging.getLogger(__name__)

class WebhookManager:
    """Simple webhook setup manager - only sets webhooks if different"""
    
    def __init__(self):
        self.app_url = None
    
    def get_app_url(self):
        """Get app URL from HEROKU_APP_NAME"""
        if self.app_url:
            return self.app_url
            
        app_name = os.getenv("HEROKU_APP_NAME")
        if not app_name:
            raise RuntimeError("HEROKU_APP_NAME environment variable required")
        
        self.app_url = f"https://{app_name}.herokuapp.com"
        return self.app_url
    
    async def setup_webhooks(self, main_bot, admin_bot):
        """Setup webhooks for both bots if they're different from expected"""
        try:
            app_url = self.get_app_url()
            
            # Expected webhook URLs
            main_webhook_url = f"{app_url}/webhook/main"
            admin_webhook_url = f"{app_url}/webhook/admin"
            
            # Get current webhook info
            main_info = await main_bot.get_webhook_info()
            admin_info = await admin_bot.get_webhook_info()
            
            # Set main bot webhook if different
            if main_info.url != main_webhook_url:
                logger.info(f"Setting main bot webhook: {main_webhook_url}")
                await main_bot.set_webhook(main_webhook_url)
                await asyncio.sleep(1)  # Brief pause between webhook calls
            else:
                logger.info("Main bot webhook already correct")
            
            # Set admin bot webhook if different
            if admin_info.url != admin_webhook_url:
                logger.info(f"Setting admin bot webhook: {admin_webhook_url}")
                await admin_bot.set_webhook(admin_webhook_url)
            else:
                logger.info("Admin bot webhook already correct")
                
            logger.info("Webhook setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup webhooks: {e}")
            return False