from datetime import datetime
from pydantic import BaseModel, EmailStr


# ── User ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Auth ──────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Channel ───────────────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    name: str
    description: str | None = None


class ChannelOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Message ───────────────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    content: str
    channel_id: int
    reply_to_id: int | None = None


class MessageOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    author_id: int
    channel_id: int
    reply_to_id: int | None
    author: UserOut

    model_config = {"from_attributes": True}


class ThreadOut(BaseModel):
    root: MessageOut
    replies: list[MessageOut]