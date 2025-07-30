import json
import logging
import time
from typing import Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class BotState:
    """Centralized bot state for stateless operation"""
    
    promo_id: int = 0              # Current promo DB ID
    verified_at: int = 0           # 0 = not admin, timestamp = admin verified
    status_message_id: int = 0      # Status/instruction message ID (0 for users)
    promo_message_id: int = 0       # Current promo display message ID (0 for users)

class StateManager:
    """Stateless utility for state encoding/decoding - no global storage"""
    
    @staticmethod
    def create_state(promo_id: int = 0, verified_at: int = 0, 
                    status_message_id: int = 0, promo_message_id: int = 0) -> BotState:
        """Create bot state with given parameters"""
        return BotState(
            promo_id=promo_id,
            verified_at=verified_at,
            status_message_id=status_message_id,
            promo_message_id=promo_message_id
        )
        
    @staticmethod
    def update_state(state: BotState, **updates) -> BotState:
        """
        Create a new state with updated fields
        
        Args:
            state: Original BotState
            **updates: Fields to update (promo_id, verified_at, status_message_id, promo_message_id)
        
        Returns:
            New BotState with updated fields
        """
        # Create new state with original values
        new_state = BotState(
            promo_id=updates.get('promo_id', state.promo_id),
            verified_at=updates.get('verified_at', state.verified_at),
            status_message_id=updates.get('status_message_id', state.status_message_id),
            promo_message_id=updates.get('promo_message_id', state.promo_message_id)
        )
        
        # Validate the new state
        if not StateManager.validate_state(new_state):
            logger.error(f"Invalid state created in update_state: {new_state}")
            return state  # Return original state if validation fails
        
        return new_state
    
    @staticmethod
    def encode_state_for_callback(action: str, state: BotState) -> str:
        """
        Encode action and state into callback data with maximum compression
        Format: action_p:promo_id_v:verified_at_s:status_id_m:promo_id
        """
        # Convert action to camelCase if needed
        action_camel = StateManager._to_camel_case(action)
        
        # Start building parts
        parts = [action_camel]
        
        # Core data (always include if non-zero)
        if state.promo_id > 0:
            parts.extend(["p", StateManager._encode_number(state.promo_id)])
        
        # Admin data (only if admin)
        if state.verified_at > 0:
            parts.extend(["v", StateManager._encode_number(state.verified_at)])

            if state.status_message_id > 0:
                parts.extend(["s", StateManager._encode_number(state.status_message_id)])

            if state.promo_message_id > 0:
                parts.extend(["m", StateManager._encode_number(state.promo_message_id)])

        # Join with underscores
        callback_data = "_".join(parts)
        
        # If too long, use compressed JSON format
        if len(callback_data) > 64:
            return StateManager._encode_json_compressed(action_camel, state)
        
        return callback_data
    
    @staticmethod
    def decode_callback_data(callback_data: str) -> Tuple[str, BotState]:
        """
        Decode callback data back into action and state
        Returns: (action, BotState)
        """
        if callback_data.startswith("state_"):
            return StateManager._decode_json_compressed(callback_data)
        
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
                        state.promo_id = StateManager._decode_number(value)
                    elif key == "v":
                        state.verified_at = StateManager._decode_number(value)
                    elif key == "s":
                        state.status_message_id = StateManager._decode_number(value)
                    elif key == "m":
                        state.promo_message_id = StateManager._decode_number(value)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse callback key {key}={value}: {e}")
                
                i += 2
            else:
                i += 1
        
        return action, state
    
    @staticmethod
    def validate_state(state: BotState) -> bool:
        """Minimal validation to help during development"""
        # Check for negative IDs (likely encoding/decoding errors)
        if state.promo_id < 0 or state.status_message_id < 0 or state.promo_message_id < 0:
            logger.warning(f"Negative IDs in state: {state}")
            return False

        # Check for unreasonable verified_at (future timestamp)
        if state.verified_at > int(time.time()) + 86400:  # Allow 1 day future for clock skew
            logger.warning(f"Future verified_at in state: {state}")
            return False
        
        return True
    
    # Helper methods
    
    @staticmethod
    def _to_camel_case(s: str) -> str:
        """Convert snake_case to camelCase"""
        parts = s.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:]) if len(parts) > 1 else s
    
    @staticmethod
    def _encode_number(num: int) -> str:
        """Encode number in base36 for space efficiency"""
        if num == 0:
            return "0"
        
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        result = ""
        while num:
            result = digits[num % 36] + result
            num //= 36
        return result
    
    @staticmethod
    def _decode_number(encoded: str) -> int:
        """Decode base36 number"""
        try:
            return int(encoded, 36)
        except ValueError:
            logger.warning(f"Failed to decode base36 number: {encoded}")
            return 0
    
    @staticmethod
    def _encode_json_compressed(action: str, state: BotState) -> str:
        """Fallback: encode as compressed JSON (max 58 chars after 'state_')"""
        data = {"a": action}

        if state.promo_id > 0:
            data["p"] = state.promo_id
        if state.verified_at > 0:
            data["v"] = state.verified_at
        if state.status_message_id > 0:
            data["s"] = state.status_message_id
        if state.promo_message_id > 0:
            data["m"] = state.promo_message_id

        json_str = json.dumps(data, separators=(',', ':'))
        return f"state_{json_str}"[:64]
    
    @staticmethod
    def _decode_json_compressed(callback_data: str) -> Tuple[str, BotState]:
        """Decode JSON compressed format"""
        try:
            json_str = callback_data[6:]  # Remove 'state_' prefix
            data = json.loads(json_str)
            
            action = data.get("a", "")
            state = BotState(
                promo_id=data.get("p", 0),
                verified_at=data.get("v", 0),
                status_message_id=data.get("s", 0),
                promo_message_id=data.get("m", 0)
            )
            
            return action, state
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to decode JSON callback: {e}")
            return callback_data, BotState()