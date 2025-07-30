from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from state_manager import BotState, StateManager

class KeyboardBuilder:
    """Centralized keyboard builder using stateless state management system"""
    
    @staticmethod
    def user_navigation(state: BotState, promo_link: str = "") -> InlineKeyboardMarkup:
        """
        Build navigation keyboard for users (and admins in user mode)
        """
        keyboard = []

        # Create visit link button - URL if link exists, disabled if not
        if promo_link:
            visit_button = InlineKeyboardButton(
                "🔗&nbsp;&nbsp;Перейти",
                url=promo_link
            )
        else:
            visit_button = InlineKeyboardButton(
                "🔗&nbsp;&nbsp;Скоро",
                callback_data="disabled"
            )
    
        # Navigation buttons - use current state, handlers will update promoId
        nav_buttons = [
            InlineKeyboardButton(
                "《",
                callback_data=StateManager.encode_state_for_callback("prev", state)
            ),
            visit_button,
            InlineKeyboardButton(
                "》",
                callback_data=StateManager.encode_state_for_callback("next", state)
            )
        ]
        keyboard.append(nav_buttons)
        
        # Add admin buttons if user is admin
        if state.verifiedAt > 0:
            admin_buttons = [
                InlineKeyboardButton(
                    "📋 List",
                    callback_data=StateManager.encode_state_for_callback("adminList", state)
                ),
                InlineKeyboardButton(
                    "📝 Edit",
                    callback_data=StateManager.encode_state_for_callback("adminEdit", state)
                ),
                InlineKeyboardButton(
                    "🔄 Toggle",
                    callback_data=StateManager.encode_state_for_callback("adminToggle", state)
                ),
                InlineKeyboardButton(
                    "🗑️ Delete",
                    callback_data=StateManager.encode_state_for_callback("adminDelete", state)
                )
            ]
            keyboard.append(admin_buttons)
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def admin_promo_actions(state: BotState):
        """Keyboard for admin promo actions (edit, toggle, delete)"""
        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Edit", 
                    callback_data=StateManager.encode_state_for_callback("adminEdit", state)
                ),
                InlineKeyboardButton(
                    "🔄 Toggle", 
                    callback_data=StateManager.encode_state_for_callback("adminToggle", state)
                ),
                InlineKeyboardButton(
                    "🗑️ Delete", 
                    callback_data=StateManager.encode_state_for_callback("adminDelete", state)
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_back_to_promo(state: BotState):
        """Keyboard with a single back button to promo view"""
        keyboard = [
            [InlineKeyboardButton(
                "← Back to Promo", 
                callback_data=StateManager.encode_state_for_callback("backToPromo", state)
            )]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_confirmation(action: str, state: BotState):
        """Confirmation keyboard for delete or other actions"""
        keyboard = [
            [
                InlineKeyboardButton(
                    f"✅ Confirm {action}", 
                    callback_data=StateManager.encode_state_for_callback(f"confirm{action}", state)
                ),
                InlineKeyboardButton(
                    "❌ Cancel", 
                    callback_data=StateManager.encode_state_for_callback("backToPromo", state)
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_preview(state: BotState = None):
        """Keyboard for admin preview (publish, draft, edit, cancel)"""
        # Create minimal state for preview actions if none provided
        if state is None:
            preview_state = StateManager.create_state()
        else:
            preview_state = state
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "📤 Publish", 
                    callback_data=StateManager.encode_state_for_callback("adminPublish", preview_state)
                ),
                InlineKeyboardButton(
                    "📄 Draft", 
                    callback_data=StateManager.encode_state_for_callback("adminDraft", preview_state)
                ),
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit", 
                    callback_data=StateManager.encode_state_for_callback("adminEditText", preview_state)
                ),
                InlineKeyboardButton(
                    "❌ Cancel", 
                    callback_data=StateManager.encode_state_for_callback("adminCancel", preview_state)
                ),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def admin_edit_menu(state: BotState):
        """Build edit menu keyboard"""
        keyboard = [
            [
                InlineKeyboardButton(
                    "📝 Text",
                    callback_data=StateManager.encode_state_for_callback("editText", state)
                ),
                InlineKeyboardButton(
                    "🔗 Link",
                    callback_data=StateManager.encode_state_for_callback("editLink", state)
                )
            ],
            [
                InlineKeyboardButton(
                    "🖼️ Image",
                    callback_data=StateManager.encode_state_for_callback("editImage", state)
                ),
                InlineKeyboardButton(
                    "🔄 Replace All",
                    callback_data=StateManager.encode_state_for_callback("editAll", state)
                )
            ],
            [
                InlineKeyboardButton(
                    "← Back to Promo",
                    callback_data=StateManager.encode_state_for_callback("backToPromo", state)
                )
            ]
        ]
        return InlineKeyboardMarkup(keyboard)