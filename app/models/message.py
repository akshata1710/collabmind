from datetime import datetime
from sqlalchemy import Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)

    # This is the threading magic:
    # reply_to_id = None  → top-level message
    # reply_to_id = 5    → this is a reply to message with id=5
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, index=True
    )

    author: Mapped["User"] = relationship("User", back_populates="messages")
    channel: Mapped["Channel"] = relationship("Channel", back_populates="messages")
    replies: Mapped[list["Message"]] = relationship(
        "Message", back_populates="parent", foreign_keys=[reply_to_id]
    )
    parent: Mapped["Message | None"] = relationship(
        "Message", back_populates="replies", remote_side="Message.id"
    )