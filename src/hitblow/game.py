"""同一端末で行う2人対戦Hit & Blowのゲーム進行。"""

from __future__ import annotations

import random

from .core import judge
from .game_gui import GameClosed, GameGUI
from .strikeout import create_empty_throw_results, record_throw, to_guess
from .strikeout_gui import (
    WINDOW_HEIGHT as STRIKEOUT_HEIGHT,
    WINDOW_TITLE as STRIKEOUT_TITLE,
    WINDOW_WIDTH as STRIKEOUT_WIDTH,
    StrikeoutClosed,
    get_throw_target,
    reset_turn_marks,
    show_throw_result,
)


def _format_guess(guess: list[str | None]) -> str:
    """部分予想を画面表示用の文字列へ変換する。"""
    return "".join(
        number if number is not None else "X"
        for number in guess
    )


def _play_strikeout_turn(
    gui: GameGUI,
) -> list[str | None]:
    """ストラックアウトを3球行い、部分予想を返す。

    物理演算版では get_throw_target が「物理的な着弾判定」を行い、
    命中したパネル番号（str）または外れ（None）を直接返す。
    そのため従来の「照準番号 + 確率判定（_resolve_local_throw）」は不要になった。

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
            # get_throw_target は物理演算による着弾判定まで済ませ、
            # 命中パネル番号（str）または外れ（None）を返す。
            # ウィンドウが閉じられた場合は StrikeoutClosed を送出する。
            try:
                hit_number = get_throw_target(
                    unavailable_numbers
                )
            except StrikeoutClosed as exc:
                # ストラックアウト側のクローズ通知を
                # ゲーム進行側の GameClosed へ変換する。
                raise GameClosed from exc

            if hit_number is not None:
                unavailable_numbers.add(hit_number)

            throw_results = record_throw(
                throw_results,
                hit_number,
            )

            # 新シグネチャ（引数2つ）: 命中番号と命中済み集合のみを渡す。
            show_throw_result(
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
