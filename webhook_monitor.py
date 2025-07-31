import asyncio
import logging
import os
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class WebhookMonitor:
    """Monitor and maintain webhook health"""
    
    def __init__(self, application):
        self.application = application
        self.check_interval = 600  # 10 minutes in seconds
        self.is_running = False
        
    async def start_monitoring(self):
        """Start periodic webhook monitoring"""
        if self.is_running:
            return
        
        # Only run monitoring in production (when PORT is set)
        if not os.getenv("PORT"):
            logger.info("Development mode detected - skipping webhook monitoring")
            return
            
        self.is_running = True
        logger.info("Starting webhook health monitoring (10-minute intervals)")
        
        # Start the monitoring task
        asyncio.create_task(self._monitor_loop())
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_webhook_health()
                
            except Exception as e:
                logger.error(f"Webhook monitor error: {e}")
                # Continue monitoring even if check fails
    
    async def _check_webhook_health(self):
        """Check webhook status and fix if needed"""
        try:
            bot = self.application.bot
            webhook_info = await bot.get_webhook_info()
            
            expected_url = self._get_expected_webhook_url()
            current_url = webhook_info.url
            
            logger.info(f"Webhook check - Current: '{current_url}', Expected: '{expected_url}'")
            
            # Check if webhook URL is missing or incorrect
            if not current_url or current_url != expected_url:
                logger.warning(f"Webhook URL mismatch! Fixing...")
                await self._fix_webhook(expected_url)
                return
            
            # Check for pending updates (might indicate delivery issues)
            pending_count = webhook_info.pending_update_count
            if pending_count > 10:  # Arbitrary threshold
                logger.warning(f"High pending update count: {pending_count}")
            
            # Check for recent errors
            if webhook_info.last_error_date:
                logger.warning(f"Last webhook error: {webhook_info.last_error_message}")
            
            logger.info("Webhook health check passed ✅")
            
        except TelegramError as e:
            logger.error(f"Failed to check webhook health: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in webhook health check: {e}")
    
    def _get_expected_webhook_url(self) -> str:
        """Get the expected webhook URL"""
        app_name = os.getenv("HEROKU_APP_NAME")
        if not app_name:
            logger.error("HEROKU_APP_NAME not set!")
            return ""
        return f"https://{app_name}.herokuapp.com/"
    
    async def _fix_webhook(self, webhook_url: str):
        """Fix webhook by setting correct URL"""
        try:
            bot = self.application.bot
            
            # Set the webhook
            await bot.set_webhook(
                url=webhook_url,
                allowed_updates=["message", "callback_query"]
            )
            
            logger.info(f"Webhook fixed! Set to: {webhook_url}")
            
            # Verify it was set correctly
            await asyncio.sleep(2)  # Give Telegram a moment
            webhook_info = await bot.get_webhook_info()
            
            if webhook_info.url == webhook_url:
                logger.info("Webhook verification successful ✅")
            else:
                logger.error(f"Webhook verification failed! Expected: {webhook_url}, Got: {webhook_info.url}")
                
        except TelegramError as e:
            logger.error(f"Failed to fix webhook: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fixing webhook: {e}")
    
    def stop_monitoring(self):
        """Stop webhook monitoring"""
        self.is_running = False
        logger.info("Webhook monitoring stopped")

# Global monitor instance
webhook_monitor = None

def start_webhook_monitoring(application):
    """Start webhook monitoring for the application"""
    global webhook_monitor
    
    if webhook_monitor is None:
        webhook_monitor = WebhookMonitor(application)
    
    # Start monitoring (non-blocking)
    asyncio.create_task(webhook_monitor.start_monitoring())

def stop_webhook_monitoring():
    """Stop webhook monitoring"""
    global webhook_monitor
    
    if webhook_monitor:
        webhook_monitor.stop_monitoring()