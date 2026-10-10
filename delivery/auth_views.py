"""
auth_views.py — drop into your views.py or import from here.

Provides:
  POST  /auth/login/        — authenticates user, links Telegram chat_id, returns JWT
  POST  /create-user/       — creates user + profile (phone, Telegram chat_id) in one shot
  PATCH /auth/update-phone/ — lets an authenticated user save/update their phone number

The Telegram identity arrives as `init_data` (the signed string from
Telegram.WebApp.initData). It is verified in telegram_auth.py; a plain
`chat_id` in the request body is deliberately ignored because anyone could fake it.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .telegram_auth import (
    get_verified_chat_id,
    get_or_create_profile,
    link_chat_id_to_profile,
)


# ── helper ────────────────────────────────────────────────────────────────────

def _tokens_for_user(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access":  str(refresh.access_token),
    }


def _link_telegram(profile, init_data: str) -> None:
    """
    Verify init_data and, if genuine, link its Telegram id to the profile
    (only when the profile has no chat_id yet — never overwrites).
    Silent no-op outside Telegram or when the signature doesn't check out,
    so login/sign-up never fail because of it.
    """
    chat_id = get_verified_chat_id(init_data)
    if chat_id:
        link_chat_id_to_profile(profile, chat_id)


# ── Login (replaces api/token/ so chat_id is saved in the same request) ──────

class LoginView(APIView):
    """
    POST /auth/login/
    Body: { "username": "...", "password": "...", "init_data": "<Telegram initData>" }

    init_data is optional — omitted when the app is opened outside Telegram.
    Returns the same { access, refresh } shape as SimpleJWT's TokenObtainPairView.
    """
    permission_classes     = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username  = str(request.data.get("username",  "")).strip()
        password  = str(request.data.get("password",  ""))
        init_data = str(request.data.get("init_data", "")).strip()

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Incorrect username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        _link_telegram(get_or_create_profile(user), init_data)

        return Response(_tokens_for_user(user), status=status.HTTP_200_OK)


# ── Sign-up ───────────────────────────────────────────────────────────────────

class CreateUserView(APIView):
    """
    POST /create-user/
    Body: {
        "username":  "alice",
        "password":  "secret",
        "phone":     "0912345678",
        "init_data": "<Telegram initData>"   ← optional, present in the Mini App
    }

    Accounts created here are ALWAYS customers. Delivery staff are promoted
    from Django admin (Profile.is_delivery) — a public endpoint must never
    let the caller choose that, or anyone could sign up as a rider and
    receive every customer's phone number and address.
    """
    permission_classes     = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username  = str(request.data.get("username",  "")).strip()
        password  = str(request.data.get("password",  ""))
        phone     = str(request.data.get("phone",     "")).strip()
        init_data = str(request.data.get("init_data", "")).strip()

        # ── validation ────────────────────────────────────────────────────────
        if len(username) < 2:
            return Response(
                {"username": ["Username must be at least 2 characters."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(password) < 4:
            return Response(
                {"password": ["Password must be at least 4 characters."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(phone) < 9:
            return Response(
                {"phone": ["Enter a valid phone number."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(username=username).exists():
            return Response(
                {"username": ["A user with that username already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── create user + profile in one go ───────────────────────────────────
        user = User.objects.create_user(username=username, password=password)

        profile = get_or_create_profile(user)
        profile.phone       = phone
        profile.is_delivery = False
        profile.save(update_fields=["phone", "is_delivery"])

        _link_telegram(profile, init_data)

        return Response(
            {"ok": True, "username": user.username},
            status=status.HTTP_201_CREATED,
        )


# ── Phone update ──────────────────────────────────────────────────────────────

class UpdatePhoneView(APIView):
    """
    PATCH /auth/update-phone/
    Body: { "phone": "0912345678" }
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        phone = str(request.data.get("phone", "")).strip()
        if not phone:
            return Response(
                {"error": "phone is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile = get_or_create_profile(request.user)
        profile.phone = phone
        profile.save(update_fields=["phone"])
        return Response({"ok": True, "phone": phone})
