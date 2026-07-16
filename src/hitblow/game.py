"""同一端末で行う2人対戦Hit & Blowのゲーム進行。"""

from __future__ import annotations

import random
from typing import Final

from .core import judge
from .game_gui import GameClosed, GameGUI
from .strikeout import create_empty_throw_results, record_throw, to_guess
from .strikeout_gui import (
    WINDOW_HEIGHT as STRIKEOUT_HEIGHT,
    WINDOW_TITLE as STRIKEOUT_TITLE,
    WINDOW_WIDTH as STRIKEOUT_WIDTH,
    get_throw_target,
    reset_turn_marks,
    show_throw_result,
)

LOCAL_HIT_PROBABILITY: Final[float] = 0.65


def _format_guess(guess: list[str | None]) -> str:
    """部分予想を画面表示用の文字列へ変換する。"""
    return "".join(
        number if number is not None else "X"
        for number in guess
    )


def _resolve_local_throw(target_number: str) -> str | None:
    """通信実装前のローカル版として、投球の命中・外れを確定する。

    既存のstrikeout_gui.pyの単体動作確認と同じく、
    65%の確率で照準番号へ命中し、35%の確率で外れとする。

    Args:
        target_number:
            プレイヤーが狙った数字。

    Returns:
        命中した場合はtarget_number。
        外れた場合はNone。
    """
    if random.random() < LOCAL_HIT_PROBABILITY:
        return target_number

    return None


def _play_strikeout_turn(
    gui: GameGUI,
) -> list[str | None]:
    """ストラックアウトを3球行い、部分予想を返す。

    Args:
        gui:
            メインGUIを管理するGameGUI。

    Returns:
        3球分の部分予想。
        例: ["1", None, "2"]

    Raises:
        GameClosed:
            ストラックアウト画面が閉じられた場合。
    """
    throw_results = create_empty_throw_results()
    unavailable_numbers: set[str] = set()

    reset_turn_marks()

    gui.open_strikeout_window(
        width=STRIKEOUT_WIDTH,
        height=STRIKEOUT_HEIGHT,
        title=STRIKEOUT_TITLE,
    )

    try:
        for _ in range(3):
            target_number = get_throw_target(
                unavailable_numbers
            )

            if target_number is None:
                raise GameClosed

            hit_number = _resolve_local_throw(
                target_number
            )

            if hit_number is not None:
                unavailable_numbers.add(hit_number)

            throw_results = record_throw(
                throw_results,
                hit_number,
            )

            show_throw_result(
                target_number,
                hit_number,
                unavailable_numbers,
            )

        return to_guess(throw_results)

    finally:
        gui.restore_main_window()


def play(digits: int = 3) -> None:
    """同一端末で2人対戦のHit & Blowを開始する。

    公開関数名と引数は既存コードから変更しない。

    Args:
        digits:
            秘密数字の桁数。
            現在のストラックアウトは3球固定なので3のみ対応する。

    Raises:
        ValueError:
            digitsが3以外の場合。
    """
    if digits != 3:
        raise ValueError(
            "現在の対戦GUIは3桁のゲームだけに対応しています。"
        )

    gui = GameGUI(digits=digits)

    try:
        keep_playing = True

        while keep_playing:
            player_names = (
                "プレイヤー1",
                "プレイヤー2",
            )

            history: list[str] = []

            gui.show_intro()

            secret_1 = gui.ask_secret(
                player_names[0]
            )

            gui.show_handoff(
                title=f"{player_names[1]}に交代",
                message=(
                    f"{player_names[0]}の秘密数字を隠しました。\n"
                    f"{player_names[1]}だけが画面を見てください。"
                ),
            )

            secret_2 = gui.ask_secret(
                player_names[1]
            )

            secret_numbers = (
                secret_1,
                secret_2,
            )

            current_player = random.randrange(2)
            turn_number = 1

            gui.show_game_started(
                player_names[current_player]
            )

            while True:
                opponent = 1 - current_player
                player_name = player_names[current_player]

                gui.wait_for_turn_start(
                    player_name=player_name,
                    opponent_name=player_names[opponent],
                    turn_number=turn_number,
                    history=history,
                )

                guess = _play_strikeout_turn(gui)

                hit, blow = judge(
                    secret_numbers[opponent],
                    guess,
                )

                guess_text = _format_guess(guess)

                history.append(
                    f"{turn_number}ターン目  "
                    f"{player_name}: "
                    f"{guess_text}  /  "
                    f"{hit} Hit  {blow} Blow"
                )

                if hit == digits:
                    keep_playing = gui.show_game_over(
                        winner_name=player_name,
                        player_names=player_names,
                        secret_numbers=secret_numbers,
                        history=history,
                    )
                    break

                gui.show_turn_result(
                    player_name=player_name,
                    guess_text=guess_text,
                    hit=hit,
                    blow=blow,
                    history=history,
                )

                current_player = opponent
                turn_number += 1

    except GameClosed:
        return

    finally:
        gui.close()