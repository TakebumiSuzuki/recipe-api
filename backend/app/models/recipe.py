from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.models.base import Base
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.user import User


class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(5000))
    servings: Mapped[int]
    cook_time_min: Mapped[int]
    difficulty: Mapped[Difficulty] = mapped_column(
        SAEnum(
            Difficulty,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            create_constraint=True,
            length=10,
            name="recipes_difficulty_enum",
        )
    )
    source: Mapped[dict | None] = mapped_column(JSONB())

    is_published: Mapped[bool] = mapped_column(server_default=text("false"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="recipes")

    __table_args__ = (
        UniqueConstraint("user_id", "title"),
        CheckConstraint("cook_time_min >= 1", name="cook_time_more_than_1"),
        Index(name="ix_recipes_source_gin", postgresql_using="gin"),
    )


"""
recipes（レシピ）
意図	内容
id	主キー
user_id	users.id への外部キー（1対多の「多」側）
title	文字列、最大100文字
description	説明文。長文可、未入力可
servings	何人分か。小さい整数
cook_time_min	調理時間（分）。小さい整数
difficulty	easy / normal / hard のいずれか（Enum）
is_published	公開済みか。真偽値、初期値は「非公開」
published_on	公開日。日付のみ（時刻を持たない）、未公開なら空
source	出典情報。JSONB、未入力可
created_at / updated_at	タイムゾーン付き日時
制約として次の2つを入れる。

同じ投稿者が同じタイトルのレシピを2つ作れないようにする（user_id と title の複合ユニーク制約）
cook_time_min は 1 以上（CheckConstraint）
source を JSONB にした理由：出典はレシピによって形が違う。 「URL だけ」のこともあれば「書籍名＋著者＋ページ番号」「番組名＋放送日」のこともある。 こういう「項目が事前に決まらないデータ」を1カラムにそのまま入れられるのが JSONB。 ただし何でも JSONB に入れると検索も制約もできなくなるため、使いどころの見極めが必要になる。 （この設計が妥当かどうかは、実装時に改めて議論する）

steps（手順）
意図	内容
id	主キー
recipe_id	recipes.id への外部キー
step_no	何番目の手順か。小さい整数
instruction	手順の本文。長文可
制約：同じレシピの中で step_no は重複しない（recipe_id と step_no の複合ユニーク制約）。

リレーショナルDBのテーブルには行の順序という概念がない。 「1. 玉ねぎを切る → 2. 炒める」の順序を保つには、step_no のような列を自分で持ち、 取り出すときに明示的に並び替える必要がある。
"""
