"""First-party, short-lived MCP credentials; API credentials are not accepted."""
from datetime import datetime, timedelta, timezone

import jwt
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.exceptions import ToolError

from core.config import settings

ISSUER = 'campusconnect'
AUDIENCE = 'campusconnect:mcp'
SCOPE = 'campus:tools'
FACULTY_SCOPE = 'campus:faculty'


def issue_mcp_token(user_id, role=None):
    now = datetime.now(timezone.utc)
    scope = SCOPE + (' ' + FACULTY_SCOPE if role in ('teacher', 'superadmin') else '')
    return jwt.encode({'sub': user_id, 'iss': ISSUER, 'aud': AUDIENCE, 'scope': scope,
                       'iat': now, 'exp': now + timedelta(minutes=10)},
                      settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


class CampusTokenVerifier(TokenVerifier):
    def __init__(self, app):
        super().__init__(required_scopes=[SCOPE])
        self.app = app

    async def verify_token(self, token):
        try:
            claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
                                issuer=ISSUER, audience=AUDIENCE,
                                options={'require': ['sub', 'iss', 'aud', 'iat', 'exp']})
            if not isinstance(claims.get('scope'), str):
                return None
            scopes = claims['scope'].split()
            if SCOPE not in scopes or set(scopes) - {SCOPE, FACULTY_SCOPE} or not isinstance(claims['sub'], str):
                return None
            if not await self.app.state.accounts.by_id(claims['sub']):
                return None
            return AccessToken(token=token, client_id='campusconnect', subject=claims['sub'],
                               scopes=scopes, expires_at=claims['exp'], claims=claims)
        except (jwt.InvalidTokenError, ValueError, TypeError):
            return None


async def tool_principal(app, *, faculty=False):
    token = get_access_token()
    user = await app.state.accounts.by_id(token.subject) if token and token.subject else None
    if not user:
        raise ToolError('Authentication required')
    if faculty and (FACULTY_SCOPE not in token.scopes or user['role'] not in ('teacher', 'superadmin')):
        raise ToolError('Faculty tool permission required')
    return user
