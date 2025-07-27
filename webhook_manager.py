import logging
import asyncio
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

class WebhookManager:
    """Manages Telegram bot webhooks intelligently"""
    
    def __init__(self, main_app, admin_app):
        self.main_app = main_app
        self.admin_app = admin_app
        self.webhooks_initialized = False
        self._app_url = None
    
    def get_app_url(self) -> str:
        """Get the app URL from HEROKU_APP_NAME environment variable"""
        if self._app_url:
            return self._app_url
        
        # Get app name from environment variable
        app_name = os.getenv("HEROKU_APP_NAME")
        if not app_name:
            raise RuntimeError(
                "HEROKU_APP_NAME environment variable is required. "
                "Please set it to your Heroku app name:\n"
                "  heroku config:set HEROKU_APP_NAME=your-app-name -a your-app-name\n\n"
                "To find your app name, check: https://dashboard.heroku.com/apps"
            )
        
        self._app_url = f"https://{app_name}.herokuapp.com"
        logger.info(f"Using app URL: {self._app_url}")
        return self._app_url
    
    async def check_and_initialize_webhooks(self) -> bool:
        """Check current webhook status and initialize only if needed"""
        if self.webhooks_initialized:
            return True
            
        try:
            app_url = self.get_app_url()
            
            logger.info("Checking current webhook status...")
            
            # Check main bot webhook
            main_webhook_info = await self.main_app.bot.get_webhook_info()
            main_webhook_url = f"{app_url}/webhook/main"
            main_needs_update = main_webhook_info.url != main_webhook_url
            
            # Check admin bot webhook  
            admin_webhook_info = await self.admin_app.bot.get_webhook_info()
            admin_webhook_url = f"{app_url}/webhook/admin"
            admin_needs_update = admin_webhook_info.url != admin_webhook_url
            
            logger.info(f"Main webhook: current='{main_webhook_info.url}', expected='{main_webhook_url}', needs_update={main_needs_update}")
            logger.info(f"Admin webhook: current='{admin_webhook_info.url}', expected='{admin_webhook_url}', needs_update={admin_needs_update}")
            
            # Handle main bot webhook
            if main_needs_update:
                if main_webhook_info.url:
                    logger.info(f"Deleting old main bot webhook: {main_webhook_info.url}")
                    await self.main_app.bot.delete_webhook()
                    await asyncio.sleep(1)  # Brief pause after deletion
                
                logger.info("Setting new main bot webhook...")
                await self.main_app.bot.set_webhook(main_webhook_url)
                logger.info(f"Main bot webhook updated to: {main_webhook_url}")
                
                # Wait between webhook calls to avoid rate limiting
                if admin_needs_update:
                    await asyncio.sleep(2)
            
            # Handle admin bot webhook
            if admin_needs_update:
                if admin_webhook_info.url:
                    logger.info(f"Deleting old admin bot webhook: {admin_webhook_info.url}")
                    await self.admin_app.bot.delete_webhook()
                    await asyncio.sleep(1)  # Brief pause after deletion
                
                logger.info("Setting new admin bot webhook...")
                await self.admin_app.bot.set_webhook(admin_webhook_url)
                logger.info(f"Admin bot webhook updated to: {admin_webhook_url}")
            
            if not main_needs_update and not admin_needs_update:
                logger.info("All webhooks are already correctly configured")
            
            self.webhooks_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to check/initialize webhooks: {e}")
            return False
    
    async def force_reinitialize(self) -> bool:
        """Force webhook reinitialization (for manual endpoint)"""
        self.webhooks_initialized = False
        self._app_url = None  # Force URL re-detection
        return await self.check_and_initialize_webhooks()
    
    async def cleanup_webhooks(self) -> bool:
        """Remove all webhooks (useful for cleanup or switching to polling)"""
        try:
            logger.info("Cleaning up all webhooks...")
            
            # Delete main bot webhook
            main_info = await self.main_app.bot.get_webhook_info()
            if main_info.url:
                logger.info(f"Deleting main bot webhook: {main_info.url}")
                await self.main_app.bot.delete_webhook()
                await asyncio.sleep(1)
            
            # Delete admin bot webhook
            admin_info = await self.admin_app.bot.get_webhook_info()
            if admin_info.url:
                logger.info(f"Deleting admin bot webhook: {admin_info.url}")
                await self.admin_app.bot.delete_webhook()
                await asyncio.sleep(1)
            
            logger.info("All webhooks cleaned up successfully")
            self.webhooks_initialized = False
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup webhooks: {e}")
            return False
    
    def get_status(self) -> dict:
        """Get webhook manager status"""
        return {
            "webhooks_initialized": self.webhooks_initialized,
            "app_url": self._app_url
        }