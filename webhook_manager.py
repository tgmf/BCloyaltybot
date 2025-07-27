import logging
import asyncio
import os
import json
from typing import Optional
from flask import jsonify
from telegram import Update
from telegram.error import TelegramError

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

    # ===== FLASK ROUTE HANDLERS =====
    
    def handle_main_webhook(self, request):
        """Handle main bot webhook request from Flask route"""
        try:
            # Validate and parse request
            update_data = self._validate_and_parse_request(request)
            
            # Log incoming update (for debugging)
            logger.debug(f"Main bot update received: {json.dumps(update_data, indent=2)}")
            
            # Create async task for processing
            self._run_async_task(self._process_main_update(update_data))
            
            # Return immediate response to Telegram
            return "OK", 200
            
        except ValueError as e:
            logger.warning(f"Main webhook validation error: {e}")
            return "Bad Request", 400
        except Exception as e:
            logger.error(f"Main webhook error: {e}")
            return "OK", 200  # Return 200 to prevent Telegram retries

    def handle_admin_webhook(self, request):
        """Handle admin bot webhook request from Flask route"""
        try:
            # Validate and parse request
            update_data = self._validate_and_parse_request(request)
            
            # Log incoming update (for debugging)
            logger.debug(f"Admin bot update received: {json.dumps(update_data, indent=2)}")
            
            # Create async task for processing
            self._run_async_task(self._process_admin_update(update_data))
            
            # Return immediate response to Telegram
            return "OK", 200
            
        except ValueError as e:
            logger.warning(f"Admin webhook validation error: {e}")
            return "Bad Request", 400
        except Exception as e:
            logger.error(f"Admin webhook error: {e}")
            return "OK", 200  # Return 200 to prevent Telegram retries

    def handle_webhook_health(self):
        """Handle webhook health check request from Flask route"""
        try:
            app_url = self._app_url or "not_configured"
            
            return jsonify({
                "status": "healthy",
                "webhooks_active": self.webhooks_initialized,
                "app_url": app_url,
                "endpoints": {
                    "main_webhook": f"{app_url}/webhook/main" if app_url != "not_configured" else None,
                    "admin_webhook": f"{app_url}/webhook/admin" if app_url != "not_configured" else None
                },
                "message": "Webhook system is operational"
            })
            
        except Exception as e:
            logger.error(f"Webhook health check error: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500

    def handle_manual_init(self):
        """Handle manual webhook initialization request from Flask route"""
        try:
            # Run async webhook reinitialization
            success = self._run_async_task_sync(self.force_reinitialize())
            
            if success:
                app_url = self.get_app_url()
                return jsonify({
                    "status": "success",
                    "message": "Webhooks reinitialized successfully",
                    "webhooks": {
                        "main_webhook": f"{app_url}/webhook/main",
                        "admin_webhook": f"{app_url}/webhook/admin"
                    }
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "Failed to reinitialize webhooks"
                }), 500
                
        except Exception as e:
            logger.error(f"Manual webhook init error: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500

    # ===== PRIVATE HELPER METHODS =====

    def _validate_and_parse_request(self, request):
        """Validate and parse webhook request"""
        if not request.is_json:
            raise ValueError("Request must be JSON")
            
        if request.content_length and request.content_length > 10 * 1024 * 1024:  # 10MB limit
            raise ValueError("Request too large")
            
        update_data = request.get_json()
        if not update_data:
            raise ValueError("Empty request body")
            
        # Basic validation - ensure it looks like a Telegram update
        if not isinstance(update_data, dict):
            raise ValueError("Request body must be a JSON object")
            
        # Check for at least one expected field
        expected_fields = ["update_id", "message", "callback_query", "inline_query"]
        if not any(field in update_data for field in expected_fields):
            raise ValueError("Request does not look like a Telegram update")
            
        return update_data

    async def _process_main_update(self, update_data):
        """Process main bot update asynchronously"""
        try:
            # Create Telegram Update object
            update = Update.de_json(update_data, self.main_app.bot)
            if not update:
                logger.warning("Failed to create Update object from main bot data")
                return
            
            # Process update through main application
            logger.debug(f"Processing main bot update {update.update_id}")
            await self.main_app.process_update(update)
            logger.debug(f"Main bot update {update.update_id} processed successfully")
            
        except TelegramError as e:
            logger.error(f"Telegram error processing main update: {e}")
        except Exception as e:
            logger.error(f"Error processing main bot update: {e}")

    async def _process_admin_update(self, update_data):
        """Process admin bot update asynchronously"""
        try:
            # Create Telegram Update object
            update = Update.de_json(update_data, self.admin_app.bot)
            if not update:
                logger.warning("Failed to create Update object from admin bot data")
                return
            
            # Process update through admin application
            logger.debug(f"Processing admin bot update {update.update_id}")
            await self.admin_app.process_update(update)
            logger.debug(f"Admin bot update {update.update_id} processed successfully")
            
        except TelegramError as e:
            logger.error(f"Telegram error processing admin update: {e}")
        except Exception as e:
            logger.error(f"Error processing admin bot update: {e}")

    def _run_async_task(self, coro):
        """Run async coroutine from sync context (fire-and-forget)"""
        try:
            # Use asyncio.run_coroutine_threadsafe for better thread safety
            import threading
            import concurrent.futures
            
            def run_with_new_loop():
                """Run coroutine in a completely new event loop"""
                try:
                    # Create a fresh event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        new_loop.run_until_complete(coro)
                    finally:
                        # Properly cleanup the loop
                        new_loop.close()
                except Exception as e:
                    logger.error(f"Error in async task thread: {e}")
            
            # Run in a daemon thread to avoid blocking
            thread = threading.Thread(target=run_with_new_loop, daemon=True)
            thread.start()
            logger.debug("Created async task in new thread with isolated event loop")
                
        except Exception as e:
            logger.error(f"Failed to run async task: {e}")

    def _run_async_task_sync(self, coro):
        """Run async coroutine from sync context and wait for result"""
        try:
            import concurrent.futures
            import threading
            
            def run_and_return():
                """Run coroutine and return result"""
                try:
                    # Create isolated event loop
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()
                except Exception as e:
                    logger.error(f"Error in sync async task: {e}")
                    return False
            
            # Use ThreadPoolExecutor for better resource management
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_and_return)
                return future.result(timeout=30)  # 30 second timeout
                
        except Exception as e:
            logger.error(f"Failed to run async task synchronously: {e}")
            return False