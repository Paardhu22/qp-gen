from django.urls import path

from .views import (
    ChatMessageStreamView,
    ConversationDetailView,
    ConversationListCreateView,
)

# No trailing slashes — APPEND_SLASH=False.
urlpatterns = [
    path("conversations", ConversationListCreateView.as_view(), name="conversations"),
    path(
        "conversations/<str:conversation_id>",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path(
        "conversations/<str:conversation_id>/messages",
        ChatMessageStreamView.as_view(),
        name="conversation-messages",
    ),
]
