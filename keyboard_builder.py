from venv import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from state_manager import BotState, StateManager
from content_manager import ContentManager

class KeyboardBuilder:
    """Centralized keyboard builder using stateless state management system"""
    
    @staticmethod
    def build_keyboard(action: str, state: BotState, promo_link: str = "", content_manager: ContentManager = None) -> InlineKeyboardMarkup:
        """Build appropriate keyboard based on action and state"""
        if action == "adminDelete":
            return KeyboardBuilder.admin_confirmation("Delete", state)
        elif action == "adminEdit":
            return KeyboardBuilder.admin_edit_menu(state)
        elif action == "adminPreview":
            return KeyboardBuilder.admin_preview(state)
        elif action == "editText" or action == "editLink" or action == "editImage" or action == "editAll":
            return KeyboardBuilder.admin_back_to_promo(state)
        else:
            # Default: navigation keyboard (user + admin if verified)
            return KeyboardBuilder.user_navigation(state, promo_link, content_manager)

    @staticmethod
    def user_navigation(state: BotState, promo_link: str = "", content_manager: ContentManager = None) -> InlineKeyboardMarkup:
        """
        Build navigation keyboard for users (and admins in user mode)
        """
        keyboard = []

        # Determine which promos to check for navigation
        if state.verified_at > 0 and state.show_all_mode:
            # Admin in "show all" mode
            target_promos = content_manager.get_all_promos() if content_manager else []
        else:
            # Regular user or admin in "active only" mode
            target_promos = content_manager.get_active_promos() if content_manager else []

        # Only show navigation buttons if more than 1 promo
        if len(target_promos) > 1:
            nav_buttons = [
                InlineKeyboardButton(
                    "《",
                    callback_data=StateManager.encode_state_for_callback("prev", state)
                )
            ]
            
            # Add link button in the middle if we have a link
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
        else:
            # Only one or no promos - just show link button if available
            if promo_link:
                keyboard.append([
                    InlineKeyboardButton(
                        "🔗  Перейти",
                        url=promo_link
                    )
                ])
        
       # Add admin buttons if user is admin
        if state.verified_at > 0:
            # Determine toggle button text based on current mode
            if state.show_all_mode:
                toggle_view_text = "👁️ Все"  # Currently showing all
            else:
                toggle_view_text = "👁️ Активные"  # Currently showing active only

            current_promo = next((p for p in target_promos if p["id"] == state.promo_id), None)
            if current_promo and current_promo.get("status") == "active":
                toggle_status_text = "🔴 Выкл."
            else:
                toggle_status_text = "🟢 Вкл."

            admin_buttons = [
                InlineKeyboardButton(
                    toggle_view_text,
                    callback_data=StateManager.encode_state_for_callback("adminView", state)
                ),
                InlineKeyboardButton(
                    "✏️ Правка",
                    callback_data=StateManager.encode_state_for_callback("adminEdit", state)
                ),
                InlineKeyboardButton(
                    toggle_status_text,
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
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "🟢 Опубликовать", 
                    callback_data=StateManager.encode_state_for_callback("adminPublish", state)
                ),
                InlineKeyboardButton(
                    "✏️ Правка", 
                    callback_data=StateManager.encode_state_for_callback("adminEdit", state)
                ),
            ],
            [
                InlineKeyboardButton(
                    "← Назад",
                    callback_data=StateManager.encode_state_for_callback("backToPromo", state)
                ),
                InlineKeyboardButton(
                    "🗑️ Удалить", 
                    callback_data=StateManager.encode_state_for_callback("adminDelete", state)
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