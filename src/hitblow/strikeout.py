"""
strikeout.py - ストラックアウト投球ロジックモジュール

責務:
  - 1ターン3球というルールを管理する
  - 命中済みの数字をそのターン中は除外する
  - 命中・外れの結果を3スロットの予想リストへ変換する

担当しないこと:
  - GUI描画
  - WebSocketの送受信
  - Hit / Blow計算
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


# ────────────────────────────────────────────────
# データ型
# ────────────────────────────────────────────────

@dataclass
class ThrowState:
    """
    1ターン分の投球状態を保持するデータクラス。

    Attributes:
        slots:
            3球分の結果を格納するリスト（長さは常に3）。
            各要素は「命中した数字（"1"〜"9"）」または「外れ/未投球（None）」。
            スロットのインデックスが投球順序に対応する。
              例: ["1", None, "2"] → 1球目に"1"命中、2球目外れ、3球目に"2"命中
        count:
            実際に投球した球数（0〜3）。
            slotsだけでは「外れ（None）」と「まだ投球していない（None）」を
            区別できないため、このカウンターで管理する。

    注意:
        このクラスは直接変更せず、record_throw() が新しいオブジェクトを返す
        イミュータブルなスタイルで使用する。
    """

    slots: list[str | None] = field(default_factory=lambda: [None, None, None])
    count: int = 0


# 外部インターフェース用の型エイリアス
# ThrowResults は実体として ThrowState を使用する
ThrowResults: TypeAlias = ThrowState


# ────────────────────────────────────────────────
# 公開インターフェース
# ────────────────────────────────────────────────

def create_empty_throw_results() -> ThrowResults:
    """
    3球分の空の投球結果を返す。

    Returns:
        slots=[None, None, None], count=0 の ThrowState。
        コメントで示す「[None, None, None]」は slots の内容を表す。

    Example:
        results = create_empty_throw_results()
        # slots=[None, None, None], count=0
    """
    return ThrowState()


def can_hit_number(
    already_hit_numbers: set[str],
    hit_number: str,
) -> bool:
    """
    そのターンにまだ命中していない数字ならTrueを返す。

    Args:
        already_hit_numbers: このターンで既に命中した数字の集合
        hit_number:          命中したかどうかを確認する数字

    Returns:
        まだ命中していなければ True、既に命中済みなら False

    Example:
        already = {"1", "3"}
        can_hit_number(already, "5")  # → True（まだ命中していない）
        can_hit_number(already, "1")  # → False（既に命中済み）
    """
    return hit_number not in already_hit_numbers


def record_throw(
    throw_results: ThrowResults,
    hit_number: str | None,
) -> ThrowResults:
    """
    1球分の結果を追加した「新しい」投球結果を返す。

    - hit_number が str の場合: 命中として count 番目のスロットに記録する。
    - hit_number が None の場合: 外れとして count 番目のスロットを None のまま残し、
      count だけを +1 する（外れも投球回数を消費する）。

    元の ThrowState は変更せず、新しいオブジェクトを返す（イミュータブルな更新）。

    Args:
        throw_results: 現在の投球状態
        hit_number:    命中した数字（外れは None）

    Returns:
        1球分を追加した新しい ThrowState

    Raises:
        ValueError: 既に3球投げ終わっている場合

    Example:
        results = create_empty_throw_results()  # slots=[None, None, None], count=0
        results = record_throw(results, "1")    # slots=["1",  None, None], count=1
        results = record_throw(results, None)   # slots=["1",  None, None], count=2  ← 外れ
        results = record_throw(results, "2")    # slots=["1",  None, "2" ], count=3
        # ↑ 2球目スロットは外れのため None のまま。見た目は変わらないが count が増えている。
    """
    if throw_results.count >= 3:
        raise ValueError(
            f"既に3球投げ終わっています（count={throw_results.count}）"
        )

    new_slots = list(throw_results.slots)       # コピー（元を変更しない）
    new_slots[throw_results.count] = hit_number # 今回の投球を記録
    return ThrowState(slots=new_slots, count=throw_results.count + 1)


def is_turn_complete(throw_results: ThrowResults) -> bool:
    """
    3球分の投球が完了していれば True を返す。

    Args:
        throw_results: 現在の投球状態

    Returns:
        3球投げ終わっていれば True、そうでなければ False

    Example:
        results = create_empty_throw_results()
        is_turn_complete(results)   # → False (count=0)

        # 3球投げた後
        for _ in range(3):
            results = record_throw(results, None)
        is_turn_complete(results)   # → True (count=3)
    """
    return throw_results.count == 3


def to_guess(throw_results: ThrowResults) -> list[str | None]:
    """
    投球結果を予想用の3要素リストとして返す。

    外れのスロットは None のまま返す（Hit/Blow判定では無視される）。

    Args:
        throw_results: 投球状態（通常は3球完了済みを想定）

    Returns:
        3要素のリスト。例: ["1", None, "2"]
        JSONで送る際は ["1", null, "2"] に変換される。

    Example:
        results = create_empty_throw_results()
        results = record_throw(results, "1")
        results = record_throw(results, None)
        results = record_throw(results, "2")
        to_guess(results)  # → ["1", None, "2"]
    """
    return list(throw_results.slots)


# ────────────────────────────────────────────────
# __main__: 単体動作確認
# ────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 45)
    print("strikeout.py  動作確認")
    print("=" * 45)

    # ── 基本動作 ──
    print("\n【1】 create_empty_throw_results()")
    r = create_empty_throw_results()
    print(f"  slots={r.slots}, count={r.count}")
    assert r.slots == [None, None, None]
    assert r.count == 0

    print("\n【2】 record_throw の連続呼び出し")
    r = record_throw(r, "1")
    print(f"  1球目 命中「1」  : slots={r.slots}, count={r.count}")
    assert r.slots == ["1", None, None] and r.count == 1

    r = record_throw(r, None)
    print(f"  2球目 外れ       : slots={r.slots}, count={r.count}")
    assert r.slots == ["1", None, None] and r.count == 2  # 見た目同じ、countが増えた

    r = record_throw(r, "2")
    print(f"  3球目 命中「2」  : slots={r.slots}, count={r.count}")
    assert r.slots == ["1", None, "2"] and r.count == 3

    print("\n【3】 is_turn_complete()")
    print(f"  ターン完了: {is_turn_complete(r)}")  # → True
    assert is_turn_complete(r) is True

    print("\n【4】 to_guess()")
    g = to_guess(r)
    print(f"  予想リスト: {g}")  # → ["1", None, "2"]
    assert g == ["1", None, "2"]

    print("\n【5】 can_hit_number()")
    already = {"1", "2"}
    print(f"  can_hit_number({{'1','2'}}, '3') = {can_hit_number(already, '3')}")  # True
    print(f"  can_hit_number({{'1','2'}}, '1') = {can_hit_number(already, '1')}")  # False
    assert can_hit_number(already, "3") is True
    assert can_hit_number(already, "1") is False

    print("\n【6】 3球済みで record_throw するとエラー")
    try:
        record_throw(r, "3")
        print("  エラーが発生しなかった（問題あり）")
    except ValueError as e:
        print(f"  ValueError 発生（正常）: {e}")

    print("\n✅ すべてのテスト通過")
