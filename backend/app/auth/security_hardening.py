"""
Authentication security hardening module.

This module provides enhanced security features for authentication:
- Password strength enforcement
- Account lockout protection  
- Brute force prevention
- Token refresh mechanisms
- Security audit logging
- JWT security enhancements
"""

import re
import time
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import secrets
import string

from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class FailedAttempt:
    """Represents a failed authentication attempt."""
    timestamp: datetime
    ip_address: str
    username: str
    reason: str
    user_agent: Optional[str] = None


@dataclass
class AccountLockout:
    """Represents an account lockout status."""
    username: str
    locked_until: datetime
    failed_attempts: int
    lockout_reason: str


class PasswordStrengthValidator:
    """Validates password strength according to security policies."""
    
    MIN_LENGTH = 12
    MIN_UPPERCASE = 1
    MIN_LOWERCASE = 1
    MIN_DIGITS = 1
    MIN_SPECIAL = 1
    
    # Common weak passwords to reject
    WEAK_PASSWORDS = {
        "password", "123456", "123456789", "qwerty", "abc123",
        "password123", "admin", "administrator", "root", "user",
        "welcome", "login", "pass", "secret", "default"
    }
    
    # Special characters allowed
    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    @classmethod
    def validate_password(cls, password: str) -> Tuple[bool, List[str]]:
        """
        Validate password strength.
        
        Args:
            password: Password to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check minimum length
        if len(password) < cls.MIN_LENGTH:
            errors.append(f"Password must be at least {cls.MIN_LENGTH} characters long")
        
        # Check character composition
        uppercase_count = sum(1 for c in password if c.isupper())
        lowercase_count = sum(1 for c in password if c.islower())
        digit_count = sum(1 for c in password if c.isdigit())
        special_count = sum(1 for c in password if c in cls.SPECIAL_CHARS)
        
        if uppercase_count < cls.MIN_UPPERCASE:
            errors.append(f"Password must contain at least {cls.MIN_UPPERCASE} uppercase letter(s)")
            
        if lowercase_count < cls.MIN_LOWERCASE:
            errors.append(f"Password must contain at least {cls.MIN_LOWERCASE} lowercase letter(s)")
            
        if digit_count < cls.MIN_DIGITS:
            errors.append(f"Password must contain at least {cls.MIN_DIGITS} digit(s)")
            
        if special_count < cls.MIN_SPECIAL:
            errors.append(f"Password must contain at least {cls.MIN_SPECIAL} special character(s): {cls.SPECIAL_CHARS}")
        
        # Check against common weak passwords
        if password.lower() in cls.WEAK_PASSWORDS:
            errors.append("Password is too common and easily guessable")
        
        # Check for keyboard patterns
        if cls._has_keyboard_pattern(password):
            errors.append("Password contains keyboard patterns (e.g., qwerty, 123456)")
        
        # Check for repeated characters
        if cls._has_excessive_repetition(password):
            errors.append("Password contains too many repeated characters")
        
        return len(errors) == 0, errors
    
    @classmethod
    def _has_keyboard_pattern(cls, password: str) -> bool:
        """Check for common keyboard patterns."""
        patterns = [
            "qwerty", "asdf", "zxcv", "123456", "abcdef",
            "qwertyuiop", "asdfghjkl", "zxcvbnm"
        ]
        password_lower = password.lower()
        return any(pattern in password_lower for pattern in patterns)
    
    @classmethod
    def _has_excessive_repetition(cls, password: str) -> bool:
        """Check for excessive character repetition."""
        # No more than 3 consecutive identical characters
        for i in range(len(password) - 2):
            if password[i] == password[i+1] == password[i+2]:
                return True
        return False


class BruteForceProtection:
    """Protects against brute force attacks."""
    
    def __init__(self):
        self.failed_attempts: Dict[str, List[FailedAttempt]] = defaultdict(list)
        self.account_lockouts: Dict[str, AccountLockout] = {}
        self.ip_attempts: Dict[str, List[datetime]] = defaultdict(list)
        
        # Configuration
        self.MAX_FAILED_ATTEMPTS = 5
        self.LOCKOUT_DURATION_MINUTES = 30
        self.ATTEMPT_WINDOW_MINUTES = 15
        self.IP_RATE_LIMIT_PER_HOUR = 20
        
    def record_failed_attempt(self, username: str, ip_address: str, reason: str, user_agent: Optional[str] = None) -> None:
        """Record a failed authentication attempt."""
        attempt = FailedAttempt(
            timestamp=datetime.now(timezone.utc),
            ip_address=ip_address,
            username=username,
            reason=reason,
            user_agent=user_agent
        )
        
        self.failed_attempts[username].append(attempt)
        self.ip_attempts[ip_address].append(attempt.timestamp)
        
        # Log security event
        logger.warning(
            "Failed authentication attempt",
            extra={
                "event": "authentication_failed",
                "username": username,
                "ip_address": ip_address,
                "reason": reason,
                "user_agent": user_agent,
                "timestamp": attempt.timestamp.isoformat(),
                "security_event": True
            }
        )
        
        # Check if account should be locked
        self._check_account_lockout(username)
        
        # Check for suspicious patterns
        self._check_suspicious_activity(username, ip_address)
    
    def is_account_locked(self, username: str) -> bool:
        """Check if account is currently locked."""
        if username in self.account_lockouts:
            lockout = self.account_lockouts[username]
            if datetime.now(timezone.utc) < lockout.locked_until:
                return True
            else:
                # Lockout expired, remove it
                del self.account_lockouts[username]
        return False
    
    def get_lockout_info(self, username: str) -> Optional[AccountLockout]:
        """Get lockout information for an account."""
        if self.is_account_locked(username):
            return self.account_lockouts[username]
        return None
    
    def is_ip_rate_limited(self, ip_address: str) -> bool:
        """Check if IP address is rate limited."""
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        
        # Clean old attempts
        self.ip_attempts[ip_address] = [
            timestamp for timestamp in self.ip_attempts[ip_address]
            if timestamp > hour_ago
        ]
        
        return len(self.ip_attempts[ip_address]) >= self.IP_RATE_LIMIT_PER_HOUR
    
    def get_attempt_delay(self, username: str) -> int:
        """Get progressive delay for failed attempts."""
        recent_attempts = self._get_recent_attempts(username)
        attempt_count = len(recent_attempts)
        
        if attempt_count == 0:
            return 0
        
        # Progressive delay: 1, 2, 4, 8, 16, 32, 60 seconds (capped at 60)
        delay = min(2 ** (attempt_count - 1), 60)
        return delay
    
    def clear_failed_attempts(self, username: str) -> None:
        """Clear failed attempts for successful authentication."""
        if username in self.failed_attempts:
            del self.failed_attempts[username]
        
        logger.info(
            "Cleared failed attempts after successful authentication",
            extra={
                "event": "failed_attempts_cleared",
                "username": username,
                "security_event": True
            }
        )
    
    def _check_account_lockout(self, username: str) -> None:
        """Check if account should be locked due to failed attempts."""
        recent_attempts = self._get_recent_attempts(username)
        
        if len(recent_attempts) >= self.MAX_FAILED_ATTEMPTS:
            lockout_until = datetime.now(timezone.utc) + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
            
            lockout = AccountLockout(
                username=username,
                locked_until=lockout_until,
                failed_attempts=len(recent_attempts),
                lockout_reason=f"Too many failed attempts ({len(recent_attempts)})"
            )
            
            self.account_lockouts[username] = lockout
            
            logger.error(
                "Account locked due to excessive failed attempts",
                extra={
                    "event": "account_locked",
                    "username": username,
                    "failed_attempts": len(recent_attempts),
                    "locked_until": lockout_until.isoformat(),
                    "lockout_duration_minutes": self.LOCKOUT_DURATION_MINUTES,
                    "security_event": True,
                    "alert_priority": "high"
                }
            )
    
    def _get_recent_attempts(self, username: str) -> List[FailedAttempt]:
        """Get recent failed attempts within the time window."""
        if username not in self.failed_attempts:
            return []
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.ATTEMPT_WINDOW_MINUTES)
        
        return [
            attempt for attempt in self.failed_attempts[username]
            if attempt.timestamp > cutoff_time
        ]
    
    def _check_suspicious_activity(self, username: str, ip_address: str) -> None:
        """Check for suspicious activity patterns."""
        recent_attempts = self._get_recent_attempts(username)
        
        # Check for rapid-fire attempts (more than 3 in 1 minute)
        one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
        rapid_attempts = [
            attempt for attempt in recent_attempts
            if attempt.timestamp > one_minute_ago
        ]
        
        if len(rapid_attempts) >= 3:
            logger.warning(
                "Suspicious rapid-fire authentication attempts detected",
                extra={
                    "event": "suspicious_activity_rapid_attempts",
                    "username": username,
                    "ip_address": ip_address,
                    "attempts_count": len(rapid_attempts),
                    "time_window": "1_minute",
                    "security_event": True,
                    "alert_priority": "medium"
                }
            )
        
        # Check for distributed attacks (same username from multiple IPs)
        unique_ips = set(attempt.ip_address for attempt in recent_attempts)
        if len(unique_ips) >= 3:
            logger.warning(
                "Distributed authentication attack detected",
                extra={
                    "event": "suspicious_activity_distributed_attack",
                    "username": username,
                    "unique_ips": len(unique_ips),
                    "ip_addresses": list(unique_ips),
                    "security_event": True,
                    "alert_priority": "high"
                }
            )


class JWTSecurityEnhancer:
    """Enhances JWT token security."""
    
    @staticmethod
    def validate_secret_strength(secret: str) -> Tuple[bool, List[str]]:
        """Validate JWT secret strength."""
        errors = []
        
        # Minimum length requirement
        if len(secret) < 32:
            errors.append("JWT secret must be at least 32 characters long")
        
        # Check for default/weak secrets
        weak_secrets = {
            "default_secret_key_change_in_production",
            "secret",
            "jwt_secret",
            "my_secret_key",
            "change_me"
        }
        
        if secret.lower() in weak_secrets:
            errors.append("JWT secret is a common default value and must be changed")
        
        # Check entropy (should have good character distribution)
        if len(set(secret)) < len(secret) / 4:
            errors.append("JWT secret has insufficient entropy (too many repeated characters)")
        
        # Should contain mix of character types
        has_letters = any(c.isalpha() for c in secret)
        has_digits = any(c.isdigit() for c in secret)
        has_special = any(not c.isalnum() for c in secret)
        
        if not (has_letters and has_digits):
            errors.append("JWT secret should contain both letters and numbers")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def generate_secure_secret(length: int = 64) -> str:
        """Generate a cryptographically secure JWT secret."""
        # Use URL-safe characters for easier configuration
        alphabet = string.ascii_letters + string.digits + "-_"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def validate_token_claims(claims: dict) -> Tuple[bool, List[str]]:
        """Validate JWT token claims for security."""
        errors = []
        required_claims = ["sub", "exp", "iat", "scopes"]
        
        for claim in required_claims:
            if claim not in claims:
                errors.append(f"Missing required claim: {claim}")
        
        # Validate expiration
        if "exp" in claims:
            exp_time = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
            now = datetime.now(timezone.utc)
            
            if exp_time <= now:
                errors.append("Token is expired")
            
            # Check for excessive lifetime (more than 1 hour for access tokens)
            max_lifetime = timedelta(hours=1)
            if "iat" in claims:
                issued_time = datetime.fromtimestamp(claims["iat"], tz=timezone.utc)
                lifetime = exp_time - issued_time
                
                if lifetime > max_lifetime:
                    errors.append(f"Token lifetime ({lifetime}) exceeds maximum allowed ({max_lifetime})")
        
        return len(errors) == 0, errors


class TokenRefreshManager:
    """Manages secure token refresh mechanisms."""
    
    def __init__(self):
        self.refresh_token_families: Dict[str, List[Dict]] = {}
        self.revoked_families: set = set()
        
    def create_token_family(self, user_id: str, client_info: Dict) -> str:
        """Create a new refresh token family."""
        family_id = secrets.token_urlsafe(32)
        
        # Hash client info for binding
        client_fingerprint = self._create_client_fingerprint(client_info)
        
        self.refresh_token_families[family_id] = [{
            "token_id": secrets.token_urlsafe(32),
            "created_at": datetime.now(timezone.utc),
            "user_id": user_id,
            "client_fingerprint": client_fingerprint,
            "used": False
        }]
        
        return family_id
    
    def rotate_refresh_token(self, family_id: str, old_token_id: str, client_info: Dict) -> Optional[str]:
        """Rotate refresh token and detect potential theft."""
        if family_id in self.revoked_families:
            logger.error(
                "Attempted to use refresh token from revoked family",
                extra={
                    "event": "refresh_token_theft_detected",
                    "family_id": family_id,
                    "security_event": True,
                    "alert_priority": "critical"
                }
            )
            return None
        
        if family_id not in self.refresh_token_families:
            return None
        
        family = self.refresh_token_families[family_id]
        
        # Find the token being used
        current_token = None
        for token in family:
            if token["token_id"] == old_token_id:
                current_token = token
                break
        
        if not current_token:
            return None
        
        # Check if token was already used (potential theft)
        if current_token["used"]:
            logger.error(
                "Refresh token reuse detected - revoking entire family",
                extra={
                    "event": "refresh_token_reuse_detected",
                    "family_id": family_id,
                    "token_id": old_token_id,
                    "security_event": True,
                    "alert_priority": "critical"
                }
            )
            self.revoke_token_family(family_id)
            return None
        
        # Validate client fingerprint
        client_fingerprint = self._create_client_fingerprint(client_info)
        if current_token["client_fingerprint"] != client_fingerprint:
            logger.warning(
                "Client fingerprint mismatch for refresh token",
                extra={
                    "event": "refresh_token_fingerprint_mismatch",
                    "family_id": family_id,
                    "security_event": True,
                    "alert_priority": "high"
                }
            )
            # Optionally revoke or require additional verification
        
        # Mark old token as used
        current_token["used"] = True
        
        # Create new token
        new_token_id = secrets.token_urlsafe(32)
        family.append({
            "token_id": new_token_id,
            "created_at": datetime.now(timezone.utc),
            "user_id": current_token["user_id"],
            "client_fingerprint": client_fingerprint,
            "used": False
        })
        
        # Clean old tokens (keep last 5)
        if len(family) > 5:
            family[:] = family[-5:]
        
        return new_token_id
    
    def revoke_token_family(self, family_id: str) -> None:
        """Revoke an entire token family."""
        self.revoked_families.add(family_id)
        if family_id in self.refresh_token_families:
            del self.refresh_token_families[family_id]
        
        logger.info(
            "Refresh token family revoked",
            extra={
                "event": "refresh_token_family_revoked",
                "family_id": family_id,
                "security_event": True
            }
        )
    
    def _create_client_fingerprint(self, client_info: Dict) -> str:
        """Create a fingerprint for client binding."""
        # Hash relevant client characteristics
        fingerprint_data = f"{client_info.get('ip_address', '')}" \
                           f"{client_info.get('user_agent', '')}" \
                           f"{client_info.get('accept_language', '')}"
        
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()


# Global instances for the application
brute_force_protection = BruteForceProtection()
token_refresh_manager = TokenRefreshManager()