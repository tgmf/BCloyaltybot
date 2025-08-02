from venv import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from state_manager import BotState, StateManager

class KeyboardBuilder:
    """Centralized keyboard builder using stateless state management system"""
    
    @staticmethod
    def build_keyboard(action: str, state: BotState, promo_link: str = "") -> InlineKeyboardMarkup:
        """Build appropriate keyboard based on action and state"""
        if action == "adminDelete":
            return KeyboardBuilder.admin_confirmation("Delete", state)
        elif action == "adminEdit":
            return KeyboardBuilder.admin_edit_menu(state)
        elif action == "adminPreview":
            return KeyboardBuilder.admin_preview(state)
        else:
            # Default: navigation keyboard (user + admin if verified)
            return KeyboardBuilder.user_navigation(state, promo_link)
    
    @staticmethod
    def user_navigation(state: BotState, promo_link: str = "") -> InlineKeyboardMarkup:
        """
        Build navigation keyboard for users (and admins in user mode)
        """
        keyboard = []

        # Navigation buttons - use current state, handlers will update promo_id
        nav_buttons = [
            InlineKeyboardButton(
                "《",
                callback_data=StateManager.encode_state_for_callback("prev", state)
            )
        ]
        if promo_link:
            nav_buttons.append(
                InlineKeyboardButton(
                    "🔗  Перейти",
                    url=promo_link
                )
            )
        nav_buttons.append(
            InlineKeyboardButton(
                "》",
                callback_data=StateManager.encode_state_for_callback("next", state)
            )
        )
        keyboard.append(nav_buttons)
        
        # Add admin buttons if user is admin
        if state.verified_at > 0:
            admin_buttons = [
                InlineKeyboardButton(
                    "📋 Список",
                    callback_data=StateManager.encode_state_for_callback("adminList", state)
                ),
                InlineKeyboardButton(
                    "📝 Изменить",
                    callback_data=StateManager.encode_state_for_callback("adminEdit", state)
                ),
                InlineKeyboardButton(
                    "🔄 Вкл/Выкл",
                    callback_data=StateManager.encode_state_for_callback("adminToggle", state)
                ),
                InlineKeyboardButton(
                    "🗑️ Удалить",
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
                    "📝 Изменить", 
                    callback_data=StateManager.encode_state_for_callback("adminEdit", state)
                ),
                InlineKeyboardButton(
                    "🔄 Вкл/Выкл", 
                    callback_data=StateManager.encode_state_for_callback("adminToggle", state)
                ),
                InlineKeyboardButton(
                    "🗑️ Удалить", 
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
                "← Назад",
                callback_data=StateManager.encode_state_for_callback("backToPromo", state)
            )]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_confirmation(action: str, state: BotState):
        """Confirmation keyboard for delete or other actions"""
        action_ru = "удаление" if action == "Delete" else action
        keyboard = [
            [
                InlineKeyboardButton(
                    f"✅ Подтвердить {action_ru}", 
                    callback_data=StateManager.encode_state_for_callback(f"confirm{action}", state)
                ),
                InlineKeyboardButton(
                    "❌ Отмена", 
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
                    "📤 Опубликовать", 
                    callback_data=StateManager.encode_state_for_callback("adminPublish", preview_state)
                ),
                InlineKeyboardButton(
                    "📄 Сохранить", 
                    callback_data=StateManager.encode_state_for_callback("adminDraft", preview_state)
                ),
            ],
            [
                InlineKeyboardButton(
                    "📝 Изменить", 
                    callback_data=StateManager.encode_state_for_callback("adminEditText", preview_state)
                ),
                InlineKeyboardButton(
                    "❌ Отмена", 
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
                    "📝 Текст",
                    callback_data=StateManager.encode_state_for_callback("editText", state)
                ),
                InlineKeyboardButton(
                    "🔗 Ссылку",
                    callback_data=StateManager.encode_state_for_callback("editLink", state)
                )
            ],
            [
                InlineKeyboardButton(
                    "🖼️ Изображение",
                    callback_data=StateManager.encode_state_for_callback("editImage", state)
                ),
                InlineKeyboardButton(
                    "🔄 Заменить все",
                    callback_data=StateManager.encode_state_for_callback("editAll", state)
                )
            ],
            [
                InlineKeyboardButton(
                    "← Назад",
                    callback_data=StateManager.encode_state_for_callback("backToPromo", state)
                )
            ]
        ]
        return InlineKeyboardMarkup(keyboard)