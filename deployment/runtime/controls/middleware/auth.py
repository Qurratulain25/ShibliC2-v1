# auth.py
import jwt
from fastapi import HTTPException, Depends, Request
import logging
from config import JWT_SECRET

logger = logging.getLogger(__name__)

# Method to verify JWT token
def verify_jwt_token(token: str):
    """Verify JWT token and return decoded payload"""
    try:
        # Use default algorithm (HS256) to match Node.js service
        decoded = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return decoded
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        raise HTTPException(status_code=401, detail={"error": "token_expired"})
    except jwt.InvalidTokenError:
        logger.warning("Invalid JWT token")
        raise HTTPException(status_code=401, detail={"error": "token_invalid"})
    except Exception as e:
        logger.error(f"JWT verification error: {e}")
        raise HTTPException(status_code=401, detail={"error": "token_verification_failed"})

# Method to get current user
async def get_current_user(request: Request):
    """Dependency to get current authenticated user from Authorization header"""
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        logger.error("Not authenticated: missing Authorization header")
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    # Extract token from "Bearer <token>" format
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.error("Invalid Authorization header format")
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    
    token = parts[1]
    decoded_token = verify_jwt_token(token)
    
    if not decoded_token:
        logger.error("Authentication failed: invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return decoded_token

# Method to require role    
def allowed_roles_and_required_permission(allowed_roles: list[str], required_permission: str):
    """Dependency factory to allow multiple roles access"""
    def role_and_permission_checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get('roleName')

        if not user_role:
            logger.error("No role found in token")
            raise HTTPException(status_code=403, detail="No role found in token")

        if user_role not in allowed_roles:
            logger.error(f"Access denied. User role: {user_role} not in allowed roles: {allowed_roles}")
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Allowed roles: {allowed_roles}, User role: {user_role}"
            )

        if required_permission not in current_user.get('permissions'):
            logger.error(f"Access denied. User role: {user_role} does not have the required permission: {required_permission}")
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. User role: {user_role} does not have the required permission: {required_permission}"
            )

        return current_user

    return role_and_permission_checker
