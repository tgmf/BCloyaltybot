import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

class ContentManager:
    """Manages promo content via Google Sheets"""
    
    def __init__(self, credentials_json: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.sheet = None
        self.promos_cache = []
        self.auth_cache = {}
        self.last_update = 0
        self.cache_timeout = 300  # 5 minutes
        
        # Initialize Google Sheets client
        try:
            if credentials_json:
                creds_dict = json.loads(credentials_json)
                scope = [
                    "https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                self.client = gspread.authorize(creds)
                self.sheet = self.client.open_by_key(spreadsheet_id)
                logger.info("Google Sheets client initialized successfully")
            else:
                logger.warning("No Google Sheets credentials provided")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            self.client = None
            self.sheet = None

    async def refresh_cache(self, force: bool = False):
        """Refresh content cache from Google Sheets"""
        if not self.client or not self.sheet:
            logger.warning("Google Sheets client not available")
            return False
            
        now = datetime.now().timestamp()
        if not force and (now - self.last_update) < self.cache_timeout:
            return True
            
        try:
            # Get promo messages
            promos_sheet = self.sheet.worksheet("promo_messages")
            promos_data = promos_sheet.get_all_records()
            
            self.promos_cache = []
            for row in promos_data:
                if row.get("id"):  # Skip empty rows
                    self.promos_cache.append({
                        "id": int(row["id"]),
                        "text": row.get("text", ""),
                        "image_file_id": row.get("image_file_id", ""),
                        "link": row.get("link", ""),
                        "order": int(row.get("order", 0)),
                        "status": row.get("status", "draft"),
                        "created_by": row.get("created_by", ""),
                        "created_at": row.get("created_at", "")
                    })
            
            # Sort by order
            self.promos_cache.sort(key=lambda x: x["order"])
            
            # Get authorized users
            try:
                auth_sheet = self.sheet.worksheet("authorized_users")
                auth_data = auth_sheet.get_all_records()
                
                self.auth_cache = {}
                for row in auth_data:
                    if row.get("phone_number"):
                        self.auth_cache[row["phone_number"]] = {
                            "user_id": row.get("user_id", ""),
                            "username": row.get("username", ""),
                            "added_at": row.get("added_at", "")
                        }
            except Exception as e:
                logger.warning(f"Auth sheet not found or error: {e}")
            
            self.last_update = now
            logger.info(f"Cache refreshed: {len(self.promos_cache)} promos, {len(self.auth_cache)} auth users")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh cache: {e}")
            return False

    def get_active_promos(self) -> List[Dict]:
        """Get all active promo messages"""
        return [p for p in self.promos_cache if p["status"] == "active"]
    
    def get_all_promos(self) -> List[Dict]:
        """Get all promo messages"""
        return self.promos_cache.copy()
    
    def is_authorized(self, phone_number: str) -> bool:
        """Check if phone number is authorized"""
        return phone_number in self.auth_cache
    
    async def get_promo_by_id(self, promo_id: int) -> Optional[Dict]:
        """Get specific promo by ID"""
        for promo in self.promos_cache:
            if promo["id"] == promo_id:
                return promo.copy()
        return None
    
    async def add_promo(self, text: str, image_file_id: str, link: str, created_by: str, order: Optional[int] = None) -> int:
        """Add new promo message"""
        if not self.client or not self.sheet:
            logger.error("Google Sheets client not available")
            return 0
            
        try:
            promos_sheet = self.sheet.worksheet("promo_messages")
            
            # Get next ID
            existing_data = promos_sheet.get_all_records()
            next_id = max([int(row.get("id", 0)) for row in existing_data], default=0) + 1
            
            # Get next order if not specified
            if order is None:
                order = max([int(row.get("order", 0)) for row in existing_data], default=0) + 10
            
            # Add new row
            new_row = [
                next_id, text, image_file_id, link, order, 
                "draft", created_by, datetime.now().isoformat()
            ]
            promos_sheet.append_row(new_row)
            
            # Refresh cache
            await self.refresh_cache(force=True)
            
            logger.info(f"Added promo {next_id} by {created_by}")
            return next_id
            
        except Exception as e:
            logger.error(f"Failed to add promo: {e}")
            return 0

    async def update_promo_status(self, promo_id: int, status: str) -> bool:
        """Update promo status (active/draft/inactive)"""
        if not self.client or not self.sheet:
            logger.error("Google Sheets client not available")
            return False
            
        try:
            promos_sheet = self.sheet.worksheet("promo_messages")
            records = promos_sheet.get_all_records()
            
            for i, row in enumerate(records, start=2):  # Start from row 2 (skip header)
                if int(row.get("id", 0)) == promo_id:
                    promos_sheet.update(f"F{i}", status)  # Column F is status
                    await self.refresh_cache(force=True)
                    logger.info(f"Updated promo {promo_id} status to {status}")
                    return True
            
            logger.warning(f"Promo {promo_id} not found for status update")
            return False
            
        except Exception as e:
            logger.error(f"Failed to update promo status: {e}")
            return False

    async def update_promo(self, promo_id: int, **kwargs) -> bool:
        """Update promo fields"""
        if not self.client or not self.sheet:
            logger.error("Google Sheets client not available")
            return False
            
        try:
            promos_sheet = self.sheet.worksheet("promo_messages")
            records = promos_sheet.get_all_records()
            
            for i, row in enumerate(records, start=2):  # Start from row 2 (skip header)
                if int(row.get("id", 0)) == promo_id:
                    # Update specific fields
                    updates = []
                    
                    if "text" in kwargs:
                        updates.append((f"B{i}", kwargs["text"]))  # Column B is text
                    if "image_file_id" in kwargs:
                        updates.append((f"C{i}", kwargs["image_file_id"]))  # Column C is image_file_id
                    if "link" in kwargs:
                        updates.append((f"D{i}", kwargs["link"]))  # Column D is link
                    if "order" in kwargs:
                        updates.append((f"E{i}", kwargs["order"]))  # Column E is order
                    if "status" in kwargs:
                        updates.append((f"F{i}", kwargs["status"]))  # Column F is status
                    
                    # Batch update
                    if updates:
                        for cell, value in updates:
                            promos_sheet.update(cell, value)
                        
                        await self.refresh_cache(force=True)
                        logger.info(f"Updated promo {promo_id} fields: {list(kwargs.keys())}")
                        return True
            
            logger.warning(f"Promo {promo_id} not found for update")
            return False
            
        except Exception as e:
            logger.error(f"Failed to update promo: {e}")
            return False

    async def delete_promo(self, promo_id: int) -> bool:
        """Delete promo message"""
        if not self.client or not self.sheet:
            logger.error("Google Sheets client not available")
            return False
            
        try:
            promos_sheet = self.sheet.worksheet("promo_messages")
            records = promos_sheet.get_all_records()
            
            for i, row in enumerate(records, start=2):  # Start from row 2 (skip header)
                if int(row.get("id", 0)) == promo_id:
                    promos_sheet.delete_rows(i)
                    await self.refresh_cache(force=True)
                    logger.info(f"Deleted promo {promo_id}")
                    return True
            
            logger.warning(f"Promo {promo_id} not found for deletion")
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete promo: {e}")
            return False

    async def reorder_promos(self, promo_id: int, new_order: int) -> bool:
        """Reorder promo by changing its order value"""
        return await self.update_promo(promo_id, order=new_order)

    def get_auth_users(self) -> Dict[str, Dict]:
        """Get all authorized users"""
        return self.auth_cache.copy()

    async def add_auth_user(self, phone_number: str, user_id: str, username: str) -> bool:
        """Add authorized user"""
        if not self.client or not self.sheet:
            logger.error("Google Sheets client not available")
            return False
            
        try:
            auth_sheet = self.sheet.worksheet("authorized_users")
            
            # Add new row
            new_row = [phone_number, user_id, username, datetime.now().isoformat()]
            auth_sheet.append_row(new_row)
            
            # Refresh cache
            await self.refresh_cache(force=True)
            
            logger.info(f"Added authorized user: {phone_number} ({user_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add authorized user: {e}")
            return False

    async def remove_auth_user(self, phone_number: str) -> bool:
        """Remove authorized user"""
        if not self.client or not self.sheet:
            logger.error("Google Sheets client not available")
            return False
            
        try:
            auth_sheet = self.sheet.worksheet("authorized_users")
            records = auth_sheet.get_all_records()
            
            for i, row in enumerate(records, start=2):  # Start from row 2 (skip header)
                if row.get("phone_number") == phone_number:
                    auth_sheet.delete_rows(i)
                    await self.refresh_cache(force=True)
                    logger.info(f"Removed authorized user: {phone_number}")
                    return True
            
            logger.warning(f"Authorized user {phone_number} not found for removal")
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove authorized user: {e}")
            return False

    # ===== UTILITY METHODS =====

    def get_promo_count_by_status(self) -> Dict[str, int]:
        """Get count of promos by status"""
        counts = {"active": 0, "draft": 0, "inactive": 0}
        
        for promo in self.promos_cache:
            status = promo.get("status", "draft")
            if status in counts:
                counts[status] += 1
        
        return counts

    def get_next_order_value(self) -> int:
        """Get next available order value"""
        if not self.promos_cache:
            return 10
        
        max_order = max([promo.get("order", 0) for promo in self.promos_cache])
        return max_order + 10

    def validate_promo_order(self, order: int) -> bool:
        """Validate if order value is available"""
        existing_orders = [promo.get("order") for promo in self.promos_cache]
        return order not in existing_orders

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        await self.refresh_cache()
        
        status_counts = self.get_promo_count_by_status()
        
        return {
            "total_promos": len(self.promos_cache),
            "status_breakdown": status_counts,
            "total_auth_users": len(self.auth_cache),
            "last_cache_update": datetime.fromtimestamp(self.last_update).isoformat() if self.last_update else None,
            "sheets_connected": self.client is not None
        }