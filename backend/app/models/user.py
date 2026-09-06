from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    bio: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    recipes: Mapped[list["Recipe"]] = relationship(
        back_populates="user", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) >= 2", name="name_length_gte"),
        CheckConstraint("length(trim(bio)) <= 1000", name="bio_length_lte"),
        CheckConstraint("email ~ '^.+@.+$'", name="email_validation_loose"),
        CheckConstraint("email = lower(email)"),
        # Index(None, "email"), unique制約を入れているので不要
    )


"""
users（投稿者）
意図	内容
id	主キー
name	表示名。文字列、最大50文字
email	文字列、最大255文字。重複禁止
bio	自己紹介。長文可（Text）、未入力可
created_at	作成日時。タイムゾーン付き、DB 側で自動的に現在時刻が入る
タイムゾーン付き日時：PostgreSQL の timestamptz 型のこと。 「2026-08-24 10:00」だけでなく「どこの時刻か」まで保存する。 日本国内向けサービスでも、サーバとDBのタイムゾーンがずれると事故になるため、付きを使うのが定石。
"""
