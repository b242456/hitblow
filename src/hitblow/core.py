"""ゲームの中心ロジック（純粋関数＝テストしやすい）。

ここは責務「判定と出題」。画面・入力には触らない（それは game.py）。
"""

from __future__ import annotations

import random
from collections.abc import Sequence


GuessDigit = str | None


def judge(
    secret: str,
    guess: Sequence[GuessDigit],
) -> tuple[int, int]:
    """secretとguessを比べて、Hit数とBlow数を返す。

    guessに含まれるNoneまたは表示用の"X"は、
    Hit / Blow判定の対象外とする。

    Args:
        secret:
            正解の数字。例: "123"
        guess:
            予想。例: ["1", None, "2"] または "1X2"

    Returns:
        (hit, blow)のタプル。
    """
    # 同じ位置に同じ数字があるものをHitとして数える。
    # Noneと"X"は判定対象外にする。
    hits = sum(
        guess_digit not in (None, "X")
        and secret_digit == guess_digit
        for secret_digit, guess_digit in zip(secret, guess)
    )

    # Noneと"X"を除いた、実際に命中した数字だけを取り出す。
    valid_guess = [
        digit
        for digit in guess
        if digit not in (None, "X")
    ]

    # 正解と予想の両方に含まれる数字の個数を数える。
    common = sum(
        min(
            secret.count(digit),
            valid_guess.count(digit),
        )
        for digit in set(valid_guess)
    )

    # 共通する数字からHitを引いたものがBlowになる。
    return hits, common - hits


def make_secret(digits: int = 3) -> str:
    """1から9を使って、重複なしのdigits桁の答えを作る。"""
    if not 1 <= digits <= 9:
        raise ValueError(
            "digitsは1から9の範囲で指定してください。"
        )

    return "".join(
        random.sample("123456789", digits)
    )