import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils import encode_callback_state

# Centralized keyboard builder for stateless Telegram bot

class KeyboardBuilder:
    @staticmethod
    def back_button():
        """Build simple back button keyboard (legacy/compatibility)"""
        keyboard = [[InlineKeyboardButton("← Back to Promo", callback_data="back_to_promo")]]
        return InlineKeyboardMarkup(keyboard)
    @staticmethod
    def admin_edit(promo_id: int, current_index: int):
        """Build edit menu keyboard with state"""
        current_time = int(time.time())
        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Text",
                    callback_data=encode_callback_state("editText", promoId=promo_id, idx=current_index, ts=current_time)
                ),
                InlineKeyboardButton(
                    "🔗 Link",
                    callback_data=encode_callback_state("editLink", promoId=promo_id, idx=current_index, ts=current_time)
                )
            ],
            [
                InlineKeyboardButton(
                    "🖼️ Image",
                    callback_data=encode_callback_state("editImage", promoId=promo_id, idx=current_index, ts=current_time)
                ),
                InlineKeyboardButton(
                    "🔄 Replace All",
                    callback_data=encode_callback_state("editAll", promoId=promo_id, idx=current_index, ts=current_time)
                )
            ],
            [
                InlineKeyboardButton(
                    "← Back to Promo",
                    callback_data=encode_callback_state("backToPromo", idx=current_index, ts=current_time)
                )
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def confirmation(action: str, promo_id: int, current_index: int):
        """Build confirmation keyboard with state"""
        current_time = int(time.time())
        keyboard = [
            [
                InlineKeyboardButton(
                    f"✅ Yes, {action}",
                    callback_data=encode_callback_state(f"confirm{action.title()}", promoId=promo_id, idx=current_index, ts=current_time)
                ),
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data=encode_callback_state("backToPromo", idx=current_index, ts=current_time)
                )
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    @staticmethod
    def user_navigation(promo_id: int, current_index: int, total_promos: int, is_admin: bool = False, verified_at: int = 0, user_id: int = 0, status_message_id: int = 0, is_list: bool = False):
        """Build navigation keyboard for regular users (no admin controls)"""
        
        keyboard = []
        prev_index = (current_index - 1) % total_promos
        next_index = (current_index + 1) % total_promos
        current_time = int(time.time())
        nav_buttons = [
            InlineKeyboardButton(
                "← Previous",
                callback_data=encode_callback_state("prev", idx=prev_index, ts=current_time)
            ),
            InlineKeyboardButton(
                "🔗 Visit Link",
                callback_data=encode_callback_state("visit", promoId=promo_id, idx=current_index, ts=current_time)
            ),
            InlineKeyboardButton(
                "Next →",
                callback_data=encode_callback_state("next", idx=next_index, ts=current_time)
            )
        ]
        keyboard.append(nav_buttons)
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_navigation(promo_id: int, current_index: int, total_promos: int, verified_at: int = 0, user_id: int = 0, status_message_id: int = 0, is_list: bool = False):
        """Build navigation keyboard for admins (includes admin controls)"""
        keyboard = []
        prev_index = (current_index - 1) % total_promos
        next_index = (current_index + 1) % total_promos
        current_time = int(time.time())
        nav_buttons = [
            InlineKeyboardButton(
                "← Previous",
                callback_data=encode_callback_state("prev", idx=prev_index, ts=current_time)
            ),
            InlineKeyboardButton(
                "🔗 Visit Link",
                callback_data=encode_callback_state("visit", promoId=promo_id, idx=current_index, ts=current_time)
            ),
            InlineKeyboardButton(
                "Next →",
                callback_data=encode_callback_state("next", idx=next_index, ts=current_time)
            )
        ]
        keyboard.append(nav_buttons)
        admin_buttons = [
            InlineKeyboardButton(
                "📋 List",
                callback_data=encode_callback_state("adminList", idx=current_index, ts=current_time)
            ),
            InlineKeyboardButton(
                "📝 Edit",
                callback_data=encode_callback_state("adminEdit", promoId=promo_id, idx=current_index, ts=current_time)
            ),
            InlineKeyboardButton(
                "🔄 Toggle",
                callback_data=encode_callback_state("adminToggle", promoId=promo_id, idx=current_index, ts=current_time)
            ),
            InlineKeyboardButton(
                "🗑️ Delete",
                callback_data=encode_callback_state("adminDelete", promoId=promo_id, idx=current_index, ts=current_time)
            )
        ]
        keyboard.append(admin_buttons)
        return InlineKeyboardMarkup(keyboard)
    @staticmethod
    def admin_promo_actions(promo_id, idx):
        """Keyboard for admin promo actions (edit, toggle, delete)"""
        keyboard = [
            [
                InlineKeyboardButton("📝 Edit", callback_data=encode_callback_state("adminEdit", promoId=promo_id, idx=idx)),
                InlineKeyboardButton("🔄 Toggle", callback_data=encode_callback_state("adminToggle", promoId=promo_id, idx=idx)),
                InlineKeyboardButton("🗑️ Delete", callback_data=encode_callback_state("adminDelete", promoId=promo_id, idx=idx)),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_back_to_promo(idx):
        """Keyboard with a single back button to promo view"""
        keyboard = [
            [InlineKeyboardButton("← Back to Promo", callback_data=encode_callback_state("backToPromo", idx=idx))]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_confirmation(action, promo_id, idx):
        """Confirmation keyboard for delete or other actions"""
        keyboard = [
            [
                InlineKeyboardButton(f"✅ Confirm {action}", callback_data=encode_callback_state(f"confirm{action}", promoId=promo_id, idx=idx)),
                InlineKeyboardButton("❌ Cancel", callback_data=encode_callback_state("backToPromo", idx=idx)),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_preview(user_id):
        """Keyboard for admin preview (publish, draft, edit, cancel)"""
        keyboard = [
            [
                InlineKeyboardButton("📤 Publish", callback_data=encode_callback_state("admin_publish", userId=user_id)),
                InlineKeyboardButton("📄 Draft", callback_data=encode_callback_state("admin_draft", userId=user_id)),
            ],
            [
                InlineKeyboardButton("📝 Edit", callback_data=encode_callback_state("admin_edit_text", userId=user_id)),
                InlineKeyboardButton("❌ Cancel", callback_data=encode_callback_state("admin_cancel", userId=user_id)),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    # Add more keyboard builders as needed for navigation, user actions, etc.
