"""同一端末2人対戦用のHit & BlowメインGUI。"""

from __future__ import annotations

from typing import Final

try:
    import pygame
except ImportError as exc:
    raise ImportError(
        "pygame がインストールされていません。\n"
        "次のコマンドでインストールしてください:\n"
        "  uv pip install pygame"
    ) from exc


MAIN_WIDTH: Final[int] = 960
MAIN_HEIGHT: Final[int] = 720
MAIN_TITLE: Final[str] = "Hit & Blow - 2人対戦"
FPS: Final[int] = 60

C_BG = (20, 26, 48)
C_PANEL = (34, 42, 70)
C_BORDER = (76, 88, 132)

C_TEXT = (228, 233, 252)
C_SUBTEXT = (158, 168, 205)
C_ACCENT = (255, 208, 68)
C_OK = (76, 210, 124)

C_BUTTON = (74, 96, 168)
C_BUTTON_HOVER = (94, 120, 202)
C_BUTTON_DISABLED = (65, 70, 92)

C_SECRET_SELECTED = (255, 208, 68)
C_SECRET_NORMAL = (195, 202, 225)
C_SECRET_TEXT = (18, 22, 40)


class GameClosed(Exception):
    """プレイヤーがウィンドウを閉じたことをゲーム進行へ通知する。"""


class GameGUI:
    """Hit & Blowのメイン画面と入力を管理する。"""

    def __init__(
        self,
        digits: int = 3,
    ) -> None:
        self.digits = digits

        pygame.init()

        self.clock = pygame.time.Clock()
        self.screen: pygame.Surface
        self.fonts: dict[str, pygame.font.Font] = {}

        self.restore_main_window()
        self._init_fonts()

    def _init_fonts(self) -> None:
        """日本語を表示しやすいフォントを優先して読み込む。"""
        preferred = [
            "Yu Gothic UI",
            "Yu Gothic",
            "Meiryo",
            "MS Gothic",
            "Noto Sans CJK JP",
        ]

        font_path = pygame.font.match_font(
            ",".join(preferred)
        )

        def make_font(
            size: int,
            bold: bool = False,
        ) -> pygame.font.Font:
            if font_path:
                font = pygame.font.Font(
                    font_path,
                    size,
                )
            else:
                font = pygame.font.Font(
                    None,
                    size,
                )

            font.set_bold(bold)
            return font

        self.fonts = {
            "title": make_font(44, True),
            "heading": make_font(30, True),
            "body": make_font(23),
            "small": make_font(18),
            "button": make_font(22, True),
            "digit": make_font(42, True),
            "result": make_font(36, True),
        }

    def restore_main_window(self) -> None:
        """メイン画面の大きさとタイトルを復元する。"""
        self.screen = pygame.display.set_mode(
            (MAIN_WIDTH, MAIN_HEIGHT)
        )

        pygame.display.set_caption(
            MAIN_TITLE
        )

        pygame.event.clear()

    def open_strikeout_window(
        self,
        width: int,
        height: int,
        title: str,
    ) -> None:
        """ストラックアウト用の表示モードへ切り替える。"""
        pygame.display.set_mode(
            (width, height)
        )

        pygame.display.set_caption(
            title
        )

        pygame.event.clear()

    def close(self) -> None:
        """Pygameを終了する。"""
        pygame.quit()

    def _handle_common_event(
        self,
        event: pygame.event.Event,
    ) -> None:
        """終了操作を共通処理する。"""
        if event.type == pygame.QUIT:
            raise GameClosed

        if (
            event.type == pygame.KEYDOWN
            and event.key == pygame.K_ESCAPE
        ):
            raise GameClosed

    def _draw_text(
        self,
        text: str,
        font_name: str,
        color: tuple[int, int, int],
        center: tuple[int, int],
    ) -> pygame.Rect:
        """指定位置を中心に1行の文字を描画する。"""
        surface = self.fonts[font_name].render(
            text,
            True,
            color,
        )

        rect = surface.get_rect(
            center=center
        )

        self.screen.blit(
            surface,
            rect,
        )

        return rect

    def _draw_multiline(
        self,
        text: str,
        font_name: str,
        color: tuple[int, int, int],
        center_x: int,
        start_y: int,
        line_gap: int = 8,
    ) -> int:
        """改行を含む文章を複数行で描画する。"""
        y = start_y
        font = self.fonts[font_name]

        for line in text.splitlines():
            surface = font.render(
                line,
                True,
                color,
            )

            rect = surface.get_rect(
                center=(center_x, y)
            )

            self.screen.blit(
                surface,
                rect,
            )

            y += surface.get_height() + line_gap

        return y

    def _draw_button(
        self,
        rect: pygame.Rect,
        label: str,
        enabled: bool = True,
    ) -> None:
        """ボタンを描画する。"""
        mouse_over = (
            enabled
            and rect.collidepoint(
                pygame.mouse.get_pos()
            )
        )

        if not enabled:
            color = C_BUTTON_DISABLED
        elif mouse_over:
            color = C_BUTTON_HOVER
        else:
            color = C_BUTTON

        pygame.draw.rect(
            self.screen,
            color,
            rect,
            border_radius=12,
        )

        pygame.draw.rect(
            self.screen,
            C_BORDER,
            rect,
            2,
            border_radius=12,
        )

        text_color = (
            C_TEXT
            if enabled
            else C_SUBTEXT
        )

        text = self.fonts["button"].render(
            label,
            True,
            text_color,
        )

        self.screen.blit(
            text,
            text.get_rect(
                center=rect.center
            ),
        )

    def _draw_frame_title(
        self,
        subtitle: str = "",
    ) -> None:
        """共通の背景とタイトルを描画する。"""
        self.screen.fill(C_BG)

        self._draw_text(
            "HIT & BLOW",
            "title",
            C_ACCENT,
            (MAIN_WIDTH // 2, 62),
        )

        if subtitle:
            self._draw_text(
                subtitle,
                "body",
                C_SUBTEXT,
                (MAIN_WIDTH // 2, 108),
            )

    def _wait_for_single_button(
        self,
        title: str,
        message: str,
        button_label: str,
    ) -> None:
        """説明と1つのボタンを表示し、操作されるまで待つ。"""
        button = pygame.Rect(
            MAIN_WIDTH // 2 - 150,
            560,
            300,
            64,
        )

        while True:
            for event in pygame.event.get():
                self._handle_common_event(event)

                if (
                    event.type == pygame.KEYDOWN
                    and event.key in (
                        pygame.K_RETURN,
                        pygame.K_SPACE,
                    )
                ):
                    return

                if (
                    event.type
                    == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                    and button.collidepoint(event.pos)
                ):
                    return

            self._draw_frame_title()

            self._draw_text(
                title,
                "heading",
                C_TEXT,
                (MAIN_WIDTH // 2, 210),
            )

            self._draw_multiline(
                message,
                "body",
                C_SUBTEXT,
                MAIN_WIDTH // 2,
                285,
                line_gap=12,
            )

            self._draw_button(
                button,
                button_label,
            )

            pygame.display.flip()
            self.clock.tick(FPS)

    def show_intro(self) -> None:
        """ゲーム開始時の説明を表示する。"""
        self._wait_for_single_button(
            title="同じ端末で2人対戦",
            message=(
                "各プレイヤーが、1〜9から重複しない"
                "3桁の秘密数字を設定します。\n"
                "自分のターンでは、"
                "ストラックアウトを3球行います。\n"
                "3 Hitを先に取ったプレイヤーの勝利です。"
            ),
            button_label="秘密数字の設定へ",
        )

    def show_handoff(
        self,
        title: str,
        message: str,
        button_label: str = "準備できた",
    ) -> None:
        """端末を次のプレイヤーへ渡す画面を表示する。"""
        self._wait_for_single_button(
            title,
            message,
            button_label,
        )

    def ask_secret(
        self,
        player_name: str,
    ) -> str:
        """ボタンから重複しない3桁の秘密数字を受け取る。"""
        selected: list[str] = []

        cell_size = 86
        gap = 14

        grid_width = (
            cell_size * 3
            + gap * 2
        )

        grid_x = (
            MAIN_WIDTH - grid_width
        ) // 2

        grid_y = 250

        digit_rects: dict[
            str,
            pygame.Rect,
        ] = {}

        for index in range(9):
            row = index // 3
            col = index % 3
            digit = str(index + 1)

            digit_rects[digit] = pygame.Rect(
                grid_x
                + col * (cell_size + gap),
                grid_y
                + row * (cell_size + gap),
                cell_size,
                cell_size,
            )

        clear_button = pygame.Rect(
            MAIN_WIDTH // 2 - 250,
            600,
            210,
            58,
        )

        confirm_button = pygame.Rect(
            MAIN_WIDTH // 2 + 40,
            600,
            210,
            58,
        )

        while True:
            for event in pygame.event.get():
                self._handle_common_event(event)

                if event.type == pygame.KEYDOWN:
                    if (
                        event.key == pygame.K_BACKSPACE
                        and selected
                    ):
                        selected.pop()

                    elif (
                        event.key == pygame.K_RETURN
                        and len(selected) == self.digits
                    ):
                        return "".join(selected)

                    elif event.unicode in "123456789":
                        digit = event.unicode

                        if digit in selected:
                            selected.remove(digit)

                        elif len(selected) < self.digits:
                            selected.append(digit)

                if (
                    event.type
                    == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                ):
                    for digit, rect in digit_rects.items():
                        if rect.collidepoint(event.pos):
                            if digit in selected:
                                selected.remove(digit)

                            elif len(selected) < self.digits:
                                selected.append(digit)

                            break

                    if clear_button.collidepoint(
                        event.pos
                    ):
                        selected.clear()

                    if (
                        confirm_button.collidepoint(
                            event.pos
                        )
                        and len(selected)
                        == self.digits
                    ):
                        return "".join(selected)

            self._draw_frame_title(
                f"{player_name}の秘密数字を設定"
            )

            if selected:
                selected_text = " ".join(selected)
            else:
                selected_text = "― ― ―"

            self._draw_text(
                selected_text,
                "result",
                C_ACCENT,
                (MAIN_WIDTH // 2, 170),
            )

            self._draw_text(
                "1〜9から、順番を考えて"
                "3つ選択してください",
                "small",
                C_SUBTEXT,
                (MAIN_WIDTH // 2, 215),
            )

            for digit, rect in digit_rects.items():
                is_selected = digit in selected

                if is_selected:
                    color = C_SECRET_SELECTED
                else:
                    color = C_SECRET_NORMAL

                pygame.draw.rect(
                    self.screen,
                    color,
                    rect,
                    border_radius=12,
                )

                pygame.draw.rect(
                    self.screen,
                    C_BORDER,
                    rect,
                    2,
                    border_radius=12,
                )

                digit_surface = (
                    self.fonts["digit"].render(
                        digit,
                        True,
                        C_SECRET_TEXT,
                    )
                )

                self.screen.blit(
                    digit_surface,
                    digit_surface.get_rect(
                        center=rect.center
                    ),
                )

            self._draw_button(
                clear_button,
                "選択を消す",
            )

            self._draw_button(
                confirm_button,
                "この数字に決定",
                enabled=(
                    len(selected)
                    == self.digits
                ),
            )

            pygame.display.flip()
            self.clock.tick(FPS)

    def show_game_started(
        self,
        first_player_name: str,
    ) -> None:
        """ランダムに決まった先攻を表示する。"""
        self._wait_for_single_button(
            title="ゲーム開始",
            message=(
                f"先攻は "
                f"{first_player_name} です。"
            ),
            button_label="対戦を始める",
        )

    def _draw_history(
        self,
        history: list[str],
    ) -> None:
        """直近の対戦履歴を表示する。"""
        panel = pygame.Rect(
            100,
            350,
            760,
            230,
        )

        pygame.draw.rect(
            self.screen,
            C_PANEL,
            panel,
            border_radius=14,
        )

        pygame.draw.rect(
            self.screen,
            C_BORDER,
            panel,
            2,
            border_radius=14,
        )

        self._draw_text(
            "対戦履歴",
            "body",
            C_TEXT,
            (
                panel.centerx,
                panel.top + 30,
            ),
        )

        if not history:
            self._draw_text(
                "まだ結果はありません",
                "small",
                C_SUBTEXT,
                panel.center,
            )
            return

        recent = history[-6:]
        y = panel.top + 65

        for line in recent:
            surface = self.fonts["small"].render(
                line,
                True,
                C_SUBTEXT,
            )

            self.screen.blit(
                surface,
                (
                    panel.left + 24,
                    y,
                ),
            )

            y += 27

    def wait_for_turn_start(
        self,
        player_name: str,
        opponent_name: str,
        turn_number: int,
        history: list[str],
    ) -> None:
        """現在のプレイヤーが準備できるまで待つ。"""
        button = pygame.Rect(
            MAIN_WIDTH // 2 - 165,
            610,
            330,
            62,
        )

        while True:
            for event in pygame.event.get():
                self._handle_common_event(event)

                if (
                    event.type == pygame.KEYDOWN
                    and event.key in (
                        pygame.K_RETURN,
                        pygame.K_SPACE,
                    )
                ):
                    return

                if (
                    event.type
                    == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                    and button.collidepoint(event.pos)
                ):
                    return

            self._draw_frame_title(
                f"{turn_number}ターン目"
            )

            self._draw_text(
                f"{player_name}のターン",
                "heading",
                C_ACCENT,
                (MAIN_WIDTH // 2, 178),
            )

            self._draw_multiline(
                (
                    f"{opponent_name}の秘密数字を狙います。\n"
                    "準備できたらストラックアウトを"
                    "開始してください。"
                ),
                "body",
                C_SUBTEXT,
                MAIN_WIDTH // 2,
                230,
            )

            self._draw_history(history)

            self._draw_button(
                button,
                "ストラックアウト開始",
            )

            pygame.display.flip()
            self.clock.tick(FPS)

    def show_turn_result(
        self,
        player_name: str,
        guess_text: str,
        hit: int,
        blow: int,
        history: list[str],
    ) -> None:
        """ストラックアウト終了後の結果を表示する。"""
        button = pygame.Rect(
            MAIN_WIDTH // 2 - 145,
            620,
            290,
            56,
        )

        while True:
            for event in pygame.event.get():
                self._handle_common_event(event)

                if (
                    event.type == pygame.KEYDOWN
                    and event.key in (
                        pygame.K_RETURN,
                        pygame.K_SPACE,
                    )
                ):
                    return

                if (
                    event.type
                    == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                    and button.collidepoint(event.pos)
                ):
                    return

            self._draw_frame_title(
                f"{player_name}の結果"
            )

            self._draw_text(
                f"予想  {guess_text}",
                "result",
                C_TEXT,
                (MAIN_WIDTH // 2, 175),
            )

            self._draw_text(
                f"{hit} Hit   {blow} Blow",
                "result",
                C_ACCENT,
                (MAIN_WIDTH // 2, 235),
            )

            self._draw_history(history)

            self._draw_button(
                button,
                "次のプレイヤーへ",
            )

            pygame.display.flip()
            self.clock.tick(FPS)

    def show_game_over(
        self,
        winner_name: str,
        player_names: tuple[str, str],
        secret_numbers: tuple[str, str],
        history: list[str],
    ) -> bool:
        """勝者を表示し、再戦する場合はTrueを返す。"""
        replay_button = pygame.Rect(
            MAIN_WIDTH // 2 - 270,
            625,
            230,
            58,
        )

        quit_button = pygame.Rect(
            MAIN_WIDTH // 2 + 40,
            625,
            230,
            58,
        )

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return False

                    if event.key in (
                        pygame.K_RETURN,
                        pygame.K_SPACE,
                    ):
                        return True

                if (
                    event.type
                    == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                ):
                    if replay_button.collidepoint(
                        event.pos
                    ):
                        return True

                    if quit_button.collidepoint(
                        event.pos
                    ):
                        return False

            self._draw_frame_title(
                "ゲーム終了"
            )

            self._draw_text(
                f"{winner_name}の勝利！",
                "heading",
                C_OK,
                (MAIN_WIDTH // 2, 170),
            )

            self._draw_multiline(
                (
                    f"{player_names[0]}の秘密数字: "
                    f"{secret_numbers[0]}\n"
                    f"{player_names[1]}の秘密数字: "
                    f"{secret_numbers[1]}"
                ),
                "body",
                C_TEXT,
                MAIN_WIDTH // 2,
                225,
                line_gap=12,
            )

            self._draw_history(history)

            self._draw_button(
                replay_button,
                "もう一度遊ぶ",
            )

            self._draw_button(
                quit_button,
                "終了する",
            )

            pygame.display.flip()
            self.clock.tick(FPS)