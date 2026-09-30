from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from gateway_service.application.errors import AuthenticationError
from gateway_service.application.ports.token_service import (
    DecodedAccess,
    DecodedRefresh,
    IssuedRefresh,
)
from gateway_service.config import GatewaySettings
from gateway_service.domain.user import Role, User


class PyJwtTokenService:
    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def decode_refresh(self, token: str) -> DecodedRefresh:
        try:
            decoded_token = jwt.decode(
                jwt=token,
                key=self._settings.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "jti", "exp", "type"]},
            )
            if decoded_token["type"] != "refresh":
                raise AuthenticationError

            return DecodedRefresh(
                user_id=UUID(decoded_token["sub"]),
                jti=UUID(decoded_token["jti"]),
            )
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise AuthenticationError from exc

    def decode_access(self, token: str) -> DecodedAccess:
        try:
            decoded_token = jwt.decode(
                jwt=token,
                key=self._settings.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "role", "exp", "type"]},
            )
            if decoded_token["type"] != "access":
                raise AuthenticationError

            return DecodedAccess(
                user_id=UUID(decoded_token["sub"]),
                role=Role(decoded_token["role"]),
            )
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise AuthenticationError from exc

    def issue_refresh(self, user: User) -> IssuedRefresh:
        jti = uuid4()
        expires_at = datetime.now(tz=UTC) + timedelta(
            seconds=self._settings.refresh_token_ttl_seconds
        )
        payload = {
            "sub": str(user.id),
            "jti": str(jti),
            "exp": expires_at,
            "type": "refresh",
        }
        token = jwt.encode(
            payload=payload, key=self._settings.jwt_secret, algorithm="HS256"
        )
        return IssuedRefresh(token=token, jti=jti, expires_at=expires_at)

    def issue_access(self, user: User) -> str:
        expires_at = datetime.now(tz=UTC) + timedelta(
            seconds=self._settings.access_token_ttl_seconds
        )
        payload = {
            "sub": str(user.id),
            "role": user.role.value,
            "exp": expires_at,
            "type": "access",
        }
        return jwt.encode(
            payload=payload,
            key=self._settings.jwt_secret,
            algorithm="HS256",
        )
