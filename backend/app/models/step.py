from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models import Recipe


class Step(Base):
    __tablename__ = "steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    step_no: Mapped[int] = mapped_column(SmallInteger)
    instruction: Mapped[str] = mapped_column(Text())

    recipe: Mapped["Recipe"] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("recipe_id", "step_no"),
        CheckConstraint("step_no >= 1", name="step_no_gte"),
        CheckConstraint("length(instruction) <= 1000", name="instruction_length_lte"),
        CheckConstraint("length(trim(instruction)) >= 1", name="instruction_not_blank"),
    )


"""steps（手順）
id	主キー
recipe_id	recipes.id への外部キー
step_no	何番目の手順か。小さい整数
instruction	手順の本文。長文可
制約：同じレシピの中で step_no は重複しない（recipe_id と step_no の複合ユニーク制約）。

リレーショナルDBのテーブルには行の順序という概念がない。 「1. 玉ねぎを切る → 2. 炒める」の順序を保つには、step_no のような列を自分で持ち、 取り出すときに明示的に並び替える必要がある。
"""
