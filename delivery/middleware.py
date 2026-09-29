import logging
from urllib.parse import parse_qs

from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)


class JWTAuthMiddleware(BaseMiddleware):
    """
    Reads ?token=<access token> from the WebSocket URL and puts the user's
    Profile in scope["user"] (same as before). Anything that goes wrong leaves
    scope["user"] as AnonymousUser, and the consumer refuses those connections.
    """

    async def __call__(self, scope, receive, send):
        # Import models lazily, after Django is ready
        from delivery.models import Profile

        scope["user"] = AnonymousUser()

        # parse_qs stops the token at "&", unlike split("token=")
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]

        if token:
            user_id = None
            try:
                access_token = await database_sync_to_async(AccessToken)(token)
                user_id = access_token.get("user_id")

                # one query instead of two, and the user is loaded with it
                scope["user"] = await database_sync_to_async(
                    Profile.objects.select_related("user").get
                )(user_id=user_id)

            except Profile.DoesNotExist:
                logger.warning("WebSocket auth: user_id=%s has no Profile", user_id)
            except Exception as e:
                # never log the token itself
                logger.warning("WebSocket auth failed: %s", e)

        return await super().__call__(scope, receive, send)
