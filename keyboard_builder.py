from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from state_manager import BotState, get_state_manager

class KeyboardBuilder:
    """Centralized keyboard builder using state management system"""
    
    @staticmethod
    def user_navigation(state: BotState, current_index: int, total_promos: int):
        """
        Build navigation keyboard for users (and admins in user mode)
        """
        keyboard = []
        
        # Calculate navigation indices
        prev_index = (current_index - 1) % total_promos
        next_index = (current_index + 1) % total_promos
        
        # Create navigation states for prev/next
        state_manager = get_state_manager()
        
        prev_state = BotState(
            promoId=state.promoId,  # Will be updated with actual prev promo ID by handler
            verifiedAt=state.verifiedAt,
            statusMessageId=state.statusMessageId,
            promoMessageId=state.promoMessageId
        )
        
        next_state = BotState(
            promoId=state.promoId,  # Will be updated with actual next promo ID by handler
            verifiedAt=state.verifiedAt,
            statusMessageId=state.statusMessageId,
            promoMessageId=state.promoMessageId
        )
        
        visit_state = state  # Visit uses current state
        
        # Navigation buttons
        nav_buttons = [
            InlineKeyboardButton(
                "← Previous",
                callback_data=state_manager.encode_state_for_callback("prev", prev_state)
            ),
            InlineKeyboardButton(
                "🔗 Visit Link",
                callback_data=state_manager.encode_state_for_callback("visit", visit_state)
            ),
            InlineKeyboardButton(
                "Next →",
                callback_data=state_manager.encode_state_for_callback("next", next_state)
            )
        ]
        keyboard.append(nav_buttons)
        
        # Add admin buttons if user is admin
        if state.is_admin:
            admin_buttons = [
                InlineKeyboardButton(
                    "📋 List",
                    callback_data=state_manager.encode_state_for_callback("adminList", state)
                ),
                InlineKeyboardButton(
                    "📝 Edit",
                    callback_data=state_manager.encode_state_for_callback("adminEdit", state)
                ),
                InlineKeyboardButton(
                    "🔄 Toggle",
                    callback_data=state_manager.encode_state_for_callback("adminToggle", state)
                ),
                InlineKeyboardButton(
                    "🗑️ Delete",
                    callback_data=state_manager.encode_state_for_callback("adminDelete", state)
                )
            ]
            keyboard.append(admin_buttons)
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def admin_promo_actions(state: BotState):
        """Keyboard for admin promo actions (edit, toggle, delete)"""
        state_manager = get_state_manager()
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Edit", 
                    callback_data=state_manager.encode_state_for_callback("adminEdit", state)
                ),
                InlineKeyboardButton(
                    "🔄 Toggle", 
                    callback_data=state_manager.encode_state_for_callback("adminToggle", state)
                ),
                InlineKeyboardButton(
                    "🗑️ Delete", 
                    callback_data=state_manager.encode_state_for_callback("adminDelete", state)
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_back_to_promo(state: BotState):
        """Keyboard with a single back button to promo view"""
        state_manager = get_state_manager()
        
        keyboard = [
            [InlineKeyboardButton(
                "← Back to Promo", 
                callback_data=state_manager.encode_state_for_callback("backToPromo", state)
            )]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_confirmation(action: str, state: BotState):
        """Confirmation keyboard for delete or other actions"""
        state_manager = get_state_manager()
        
        keyboard = [
            [
                InlineKeyboardButton(
                    f"✅ Confirm {action}", 
                    callback_data=state_manager.encode_state_for_callback(f"confirm{action}", state)
                ),
                InlineKeyboardButton(
                    "❌ Cancel", 
                    callback_data=state_manager.encode_state_for_callback("backToPromo", state)
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_preview(user_id: int):
        """Keyboard for admin preview (publish, draft, edit, cancel)"""
        state_manager = get_state_manager()
        
        # Create minimal state for preview actions
        preview_state = BotState()
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "📤 Publish", 
                    callback_data=state_manager.encode_state_for_callback("adminPublish", preview_state)
                ),
                InlineKeyboardButton(
                    "📄 Draft", 
                    callback_data=state_manager.encode_state_for_callback("adminDraft", preview_state)
                ),
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit", 
                    callback_data=state_manager.encode_state_for_callback("adminEditText", preview_state)
                ),
                InlineKeyboardButton(
                    "❌ Cancel", 
                    callback_data=state_manager.encode_state_for_callback("adminCancel", preview_state)
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def admin_edit_menu(state: BotState):
        """Build edit menu keyboard"""
        state_manager = get_state_manager()
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Text",
                    callback_data=state_manager.encode_state_for_callback("editText", state)
                ),
                InlineKeyboardButton(
                    "🔗 Link",
                    callback_data=state_manager.encode_state_for_callback("editLink", state)
                )
            ],
            [
                InlineKeyboardButton(
                    "🖼️ Image",
                    callback_data=state_manager.encode_state_for_callback("editImage", state)
                ),
                InlineKeyboardButton(
                    "🔄 Replace All",
                    callback_data=state_manager.encode_state_for_callback("editAll", state)
                )
            ],
            [
                InlineKeyboardButton(
                    "← Back to Promo",
                    callback_data=state_manager.encode_state_for_callback("backToPromo", state)
                )
            ]
        ]
        return InlineKeyboardMarkup(keyboard)