import json
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class BotState:
    """Centralized bot state for stateless operation"""
    
    promoId: int = 0              # Current promo DB ID
    verifiedAt: int = 0           # 0 = not admin, timestamp = admin verified  
    statusMessageId: int = 0      # Status/instruction message ID (0 for users)
    promoMessageId: int = 0       # Current promo display message ID (0 for users)

class StateManager:
        
    async def create_state(self, user_id: int, promo_id: int = 0, verified_at: int = 0, 
                          status_message_id: int = 0, promo_message_id: int = 0) -> BotState:
        """Create bot state with given parameters"""
        return BotState(
            promoId=promo_id,
            verifiedAt=verified_at,
            statusMessageId=status_message_id,
            promoMessageId=promo_message_id
        )
    
    def encode_state_for_callback(self, action: str, state: BotState) -> str:
        """
        Encode action and state into callback data with maximum compression
        Format: action_p:promo_id_v:verified_at_s:status_id_m:promo_id
        """
        # Convert action to camelCase if needed
        action_camel = self._to_camel_case(action)
        
        # Start building parts
        parts = [action_camel]
        
        # Core data (always include if non-zero)
        if state.promoId > 0:
            parts.extend(["p", self._encode_number(state.promoId)])
        
        # Admin data (only if admin)
        if state.verifiedAt > 0:
            parts.extend(["v", self._encode_number(state.verifiedAt)])
            
            if state.statusMessageId > 0:
                parts.extend(["s", self._encode_number(state.statusMessageId)])
            
            if state.promoMessageId > 0:
                parts.extend(["m", self._encode_number(state.promoMessageId)])
        
        # Join with underscores
        callback_data = "_".join(parts)
        
        # If too long, use compressed JSON format
        if len(callback_data) > 64:
            return self._encode_json_compressed(action_camel, state)
        
        return callback_data
    
    def decode_callback_data(self, callback_data: str) -> Tuple[str, BotState]:
        """
        Decode callback data back into action and state
        Returns: (action, BotState)
        """
        if callback_data.startswith("state_"):
            return self._decode_json_compressed(callback_data)
        
        # Parse underscore-separated format
        parts = callback_data.split("_")
        if len(parts) < 1:
            return callback_data, BotState()
        
        action = parts[0]
        state = BotState()
        
        # Parse key-value pairs
        i = 1
        while i < len(parts):
            if i + 1 < len(parts):
                key = parts[i]
                value = parts[i + 1]
                
                try:
                    if key == "p":
                        state.promoId = self._decode_number(value)
                    elif key == "v":
                        state.verifiedAt = self._decode_number(value)
                    elif key == "s":
                        state.statusMessageId = self._decode_number(value)
                    elif key == "m":
                        state.promoMessageId = self._decode_number(value)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse callback key {key}={value}: {e}")
                
                i += 2
            else:
                i += 1
        
        return action, state
    
    def validate_state(self, state: BotState) -> bool:
        """Validate state has minimum required fields"""
        # For now, just check that it's a valid BotState object
        return isinstance(state, BotState)
    
    # Helper methods
    
    def _to_camel_case(self, s: str) -> str:
        """Convert snake_case to camelCase"""
        parts = s.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:]) if len(parts) > 1 else s
    
    def _encode_number(self, num: int) -> str:
        """Encode number in base36 for space efficiency"""
        if num == 0:
            return "0"
        
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        result = ""
        while num:
            result = digits[num % 36] + result
            num //= 36
        return result
    
    def _decode_number(self, encoded: str) -> int:
        """Decode base36 number"""
        try:
            return int(encoded, 36)
        except ValueError:
            logger.warning(f"Failed to decode base36 number: {encoded}")
            return 0
    
    def _encode_json_compressed(self, action: str, state: BotState) -> str:
        """Fallback: encode as compressed JSON (max 58 chars after 'state_')"""
        data = {"a": action}
        
        if state.promoId > 0:
            data["p"] = state.promoId
        if state.verifiedAt > 0:
            data["v"] = state.verifiedAt
        if state.statusMessageId > 0:
            data["s"] = state.statusMessageId
        if state.promoMessageId > 0:
            data["m"] = state.promoMessageId
        
        json_str = json.dumps(data, separators=(',', ':'))
        return f"state_{json_str}"[:64]
    
    def _decode_json_compressed(self, callback_data: str) -> Tuple[str, BotState]:
        """Decode JSON compressed format"""
        try:
            json_str = callback_data[6:]  # Remove 'state_' prefix
            data = json.loads(json_str)
            
            action = data.get("a", "")
            state = BotState(
                promoId=data.get("p", 0),
                verifiedAt=data.get("v", 0),
                statusMessageId=data.get("s", 0),
                promoMessageId=data.get("m", 0)
            )
            
            return action, state
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to decode JSON callback: {e}")
            return callback_data, BotState()

# Global instance (to be initialized in bot.py)
state_manager: Optional[StateManager] = None

def init_state_manager():
    """Initialize global state manager instance"""
    global state_manager
    state_manager = StateManager()
    return state_manager

def get_state_manager() -> StateManager:
    """Get global state manager instance"""
    if state_manager is None:
        raise RuntimeError("State manager not initialized. Call init_state_manager() first.")
    return state_manager