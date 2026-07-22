"""
strikeout_gui.py - ストラックアウトGUIモジュール（物理演算 + ホールド投球版）

責務:
  - Pygame で 3×3 のストラックアウト盤面を描画する
  - 列ごとに上下スクロールする「動くマス」を描画する
  - ホールド投球（長押しで飛距離・マウスXで角度）操作を受け付ける
  - 物理演算で着弾位置を求め、スクロール中のパネルとの当たり判定を行う
  - 命中/外れの結果を STRIKE！ / OUT... エフェクトで表示する

ゲームプレイ（get_throw_target の流れ）:
  1. マウスX      → 発射角度（左右方向）を決める
  2. マウス長押し → パワーゲージが青→赤へ増加し、飛距離が伸びる
  3. ボタンを離す → その瞬間のパワーで投球（満タンなら自動発射）
  4. 着弾         → スクロール中のパネル矩形と当たり判定し、命中番号 or None を返す

担当しないこと:
  - Hit / Blow の計算
  - WebSocket の送受信
  - ゲームの進行管理（ターン数・球数の管理）

外部から使う関数（公開インターフェース）:
  reset_turn_marks()                                        → None
  get_throw_target(unavailable_numbers: set[str])          → str | None
  show_throw_result(hit_number: str | None, unavailable)   → None

例外:
  StrikeoutClosed  → ウィンドウが閉じられた（またはESC）ことを game.py へ通知する
"""

from __future__ import annotations

import os
import random
import sys
import time
from typing import Optional

try:
    import pygame
except ImportError:
    raise ImportError(
        "pygame がインストールされていません。\n"
        "以下のコマンドでインストールしてください:\n"
        "  pip install pygame"
    )


# ────
# 例外
# ────

class StrikeoutClosed(Exception):
    """ウィンドウが閉じられた（またはESCが押された）ことをgame.pyへ通知する。"""


# ────
# 定数
# ────

WINDOW_WIDTH  = 580
WINDOW_HEIGHT = 700
WINDOW_TITLE  = "Hit & Blow - ストラックアウト"
FPS = 60

# ── 日本語フォント ────
# システムフォントではなく同梱の源真ゴシックを使う。
# ファイルが無ければ SysFont(None, size) にフォールバックする。
FONT_REL_PATH = "src/hitblow/font/GenShinGothic-Bold.ttf"

# ── グリッド ────
CELL_SIZE = 120
CELL_GAP  = 14
GRID_COLS = 3
GRID_ROWS = 3
_GRID_W   = GRID_COLS * CELL_SIZE + (GRID_COLS - 1) * CELL_GAP  # 388 px
_GRID_H   = GRID_ROWS * CELL_SIZE + (GRID_ROWS - 1) * CELL_GAP  # 388 px
GRID_X    = (WINDOW_WIDTH - _GRID_W) // 2   # 96
GRID_Y    = 75                    # グリッド上端 Y 座標

# 動くマスのスクロール周期（1列分の縦方向の繰り返し長さ）
_COL_PERIOD = GRID_ROWS * (CELL_SIZE + CELL_GAP)  # 402 px

# 盤面配置（初期状態・スクロール前）:
#   [1][2][3]   row=0
#   [4][5][6]   row=1
#   [7][8][9]   row=2
#   列0=1,4,7 / 列1=2,5,8 / 列2=3,6,9

# ── 動くマス（スクロール） ────
SCROLL_SPEED = 140.0   # スクロール速度 [px/s]（定速）

# ── 発射台 ────
LAUNCH_X = WINDOW_WIDTH // 2   # 290 (画面水平中央)
LAUNCH_Y = 640                  # 発射台の Y 座標

# ── ホールド投球 ────
MAX_HOLD_TIME   = 1.8    # 最大ホールド秒数（これで満タン・自動発射）
MIN_POWER_RATIO = 0.15   # 最小パワー比（一瞬で離しても最低これだけ飛ぶ）
LAND_DEV_X = 30.0        # 着弾X偏差 ±px
LAND_DEV_Y = 20.0        # 着弾Y偏差 ±px
LAND_NOISE_K = 3.0       # 着弾Yノイズ指数減衰係数

# ── 物理演算 ────
GRAVITY     = 700.0   # 重力加速度 [px/s²]
FLIGHT_TIME = 1.50    # 発射 → 着弾までの秒数
BALL_RADIUS = 14      # ボールの半径 [px]

# ── アニメーション時間 ────
ANIM_RESULT_SEC = 1.0    # STRIKE / OUT エフェクトの表示秒数

# ── 色 ────
C_BG           = ( 20,  26,  48)   # 背景（濃紺）
C_HEADER       = (200, 210, 245)   # タイトル文字
C_SUB          = ( 95, 105, 155)   # サブタイトル文字
C_BORDER       = ( 48,  56,  86)   # マス枠線

C_CELL_NORMAL  = (193, 198, 218)   # 通常マス
C_CELL_UNAVAIL = ( 62,  70,  98)   # 命中済みマス（暗いグレー）
C_CELL_HIT     = ( 58, 198, 108)   # 命中確定（緑）

C_TEXT_DARK    = ( 16,  20,  38)   # 明るいマス上のテキスト
C_TEXT_LIGHT   = (185, 195, 222)   # 暗いマス上のテキスト
C_MARK_HIT     = (188, 252, 208)   # ○マーク色

C_BALL         = (255, 198,  38)   # ボール本体（黄）
C_BALL_TRAIL   = (180, 115,   0)   # ボール軌跡
C_STATUS_INFO  = (178, 183, 218)   # 案内メッセージ
C_STATUS_OK    = ( 78, 218, 128)   # 命中メッセージ（緑）
C_STATUS_NG    = (218,  78,  78)   # 外れメッセージ（赤）
C_HIT_INFO     = (118, 188, 128)   # 命中済み一覧テキスト
C_LAUNCHER     = ( 88,  98, 138)   # 発射台本体
C_LAUNCHER_TIP = (118, 132, 175)   # 砲口
C_GAUGE_BG     = ( 40,  46,  72)   # ゲージ背景
C_GAUGE_BORDER = (120, 130, 170)   # ゲージ枠

# ── ゲージ寸法 ────
GAUGE_W = 200
GAUGE_H = 16

# ────
# モジュール内部状態
# ────

_screen    : Optional[pygame.Surface]     = None
_clock     : Optional[pygame.time.Clock]  = None
_fonts     : dict[str, pygame.font.Font]  = {}

# 列ごとのスクロール量（ターンを跨いでも継続する）
_scroll_offsets: list[float] = [0.0, 0.0, 0.0]

# ×マークは廃止したため実質未使用（互換のため残す）
_miss_marks: set[str] = set()

# ────
# 初期化・フォント
# ────

def _resolve_font_path() -> Optional[str]:
    """同梱フォントの実ファイルパスを探す。見つからなければ None。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, FONT_REL_PATH),
        os.path.join(here, "font", "GenShinGothic-Bold.ttf"),
        os.path.join(os.getcwd(), FONT_REL_PATH),
        FONT_REL_PATH,
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _make_font(font_path: Optional[str], size: int) -> pygame.font.Font:
    """同梱フォントを読み込む。失敗時は SysFont(None, size) にフォールバック。"""
    if font_path is not None:
        try:
            return pygame.font.Font(font_path, size)
        except (OSError, pygame.error):
            pass
    return pygame.font.SysFont(None, size)


def _ensure_init() -> None:
    """
    Pygame が未初期化なら初期化してウィンドウを開く（冪等）。
    2回目以降は何もしない。
    """
    global _screen, _clock
    if _screen is not None:
        return
    pygame.init()
    pygame.display.set_caption(WINDOW_TITLE)
    _screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    _clock  = pygame.time.Clock()

    # 日本語対応: 同梱フォント優先、無ければ SysFont フォールバック
    font_path = _resolve_font_path()
    _fonts["num"]    = _make_font(font_path, 48)   # マス内の数字
    _fonts["mark"]   = _make_font(font_path, 34)   # ○ マーク
    _fonts["title"]  = _make_font(font_path, 22)   # タイトル
    _fonts["status"] = _make_font(font_path, 19)   # ステータス行
    _fonts["small"]  = _make_font(font_path, 16)   # 補助テキスト
    _fonts["effect"] = _make_font(font_path, 68)   # STRIKE / OUT エフェクト

# ────
# 座標・スクロール・物理ユーティリティ
# ────

def _update_scroll(dt: float) -> None:
    """
    列ごとのスクロール量を更新する（定速・周期ラップアラウンド）。

    列0（1,4,7）: 上方向（offset -= speed*dt）
    列1（2,5,8）: 下方向（offset += speed*dt）
    列2（3,6,9）: 上方向（offset -= speed*dt）
    """
    delta = SCROLL_SPEED * dt
    _scroll_offsets[0] = (_scroll_offsets[0] - delta) % _COL_PERIOD
    _scroll_offsets[1] = (_scroll_offsets[1] + delta) % _COL_PERIOD
    _scroll_offsets[2] = (_scroll_offsets[2] - delta) % _COL_PERIOD


def _panel_rect_scrolled(number: str) -> pygame.Rect:
    """
    スクロール適用後のパネルの実際の矩形を返す。

    パネル位置 = GRID_Y + row * (CELL_SIZE + CELL_GAP) + offset
    を周期 _COL_PERIOD でラップアラウンドさせ、
    top が [GRID_Y, GRID_Y + _COL_PERIOD) の範囲に来る「基準矩形」を返す。

    （実際の描画・当たり判定では、この矩形を ±_COL_PERIOD だけずらした
      複製も併せて扱い、スロットマシンのように連続スクロールさせる）
    """
    n   = int(number) - 1
    col = n % GRID_COLS
    row = n // GRID_COLS
    off = _scroll_offsets[col]
    x   = GRID_X + col * (CELL_SIZE + CELL_GAP)
    rel = (row * (CELL_SIZE + CELL_GAP) + off) % _COL_PERIOD
    return pygame.Rect(x, round(GRID_Y + rel), CELL_SIZE, CELL_SIZE)


def _panel_visible_rects(number: str) -> list[pygame.Rect]:
    """
    グリッド帯（描画領域）に重なる、パネルの可視矩形（複製含む）を返す。

    スクロールで基準矩形が帯の外へ出たとき、±_COL_PERIOD の複製で
    反対側の端から出現させるために使う。
    """
    base = _panel_rect_scrolled(number)
    rects = []
    for dy in (-_COL_PERIOD, 0, _COL_PERIOD):
        r = base.move(0, dy)
        if r.bottom >= GRID_Y and r.top <= GRID_Y + _GRID_H:
            rects.append(r)
    return rects


def _panel_hit(landing: tuple[float, float], unavailable: set[str]) -> Optional[str]:
    """
    着弾座標がどの有効パネル上にあるかを当たり判定する。

    命中済み（unavailable）パネルは判定対象外（当たっても外れ扱い）。
    どのパネルにも当たらなければ None。
    """
    lx, ly = landing
    for n in range(1, 10):
        s = str(n)
        if s in unavailable:
            continue
        for r in _panel_visible_rects(s):
            if r.collidepoint(lx, ly):
                return s
    return None


def _power_ratio(hold: float) -> tuple[float, float]:
    """
    ホールド秒数からパワーを算出する。

    Returns:
        (power_ratio, raw)
        power_ratio: 飛距離マッピング用（MIN_POWER_RATIO 〜 1.0）
        raw:         ゲージ表示用の生の充填率（0.0 〜 1.0）
    """
    raw = min(max(hold, 0.0) / MAX_HOLD_TIME, 1.0)
    power_ratio = MIN_POWER_RATIO + (1.0 - MIN_POWER_RATIO) * raw
    return power_ratio, raw


def _aim_target(mouse_x: int, power_ratio: float) -> tuple[float, float]:
    """
    マウスX（角度）とパワー（飛距離）から狙い座標を求める。

    target_x = GRID_X + (clamp(mouse_x, GRID_X, GRID_X + _GRID_W) - GRID_X)
               → マウスXをグリッド横幅にクランプ
    target_y = GRID_Y + _GRID_H - power_ratio * _GRID_H
               → 小パワーはグリッド下部、大パワーはグリッド上部
    """
    clamped_x = min(max(mouse_x, GRID_X), GRID_X + _GRID_W)
    target_x  = GRID_X + (clamped_x - GRID_X)
    target_y  = GRID_Y + _GRID_H - power_ratio * _GRID_H
    return target_x, target_y


def _calc_velocity(tx: float, ty: float) -> tuple[float, float]:
    """
    発射台 (LAUNCH_X, LAUNCH_Y) から (tx, ty) を
    FLIGHT_TIME 秒後に通過する初速度 (vx, vy) を返す（Y下向き正）。

        tx = LAUNCH_X + vx*T            → vx = (tx - LAUNCH_X) / T
        ty = LAUNCH_Y + vy*T + ½gT²    → vy = (ty - LAUNCH_Y) / T - ½gT
    """
    T  = FLIGHT_TIME
    vx = (tx - LAUNCH_X) / T
    vy = (ty - LAUNCH_Y) / T - 0.5 * GRAVITY * T
    return vx, vy


def _trajectory_pts(vx: float, vy: float, steps: int = 22) -> list[tuple[int, int]]:
    """(vx, vy) で発射したボールの放物線軌跡の点列を返す。"""
    pts = []
    T   = FLIGHT_TIME
    for i in range(steps + 1):
        t  = i * T / steps
        px = LAUNCH_X + vx * t
        py = LAUNCH_Y + vy * t + 0.5 * GRAVITY * t * t
        pts.append((round(px), round(py)))
    return pts

# ────
# 描画ヘルパー
# ────

def _draw_cell_at(
    rect     : pygame.Rect,
    number   : str,
    unavailable: set[str],
    override : Optional[tuple[int, int, int]],
) -> None:
    """指定矩形にマスを1枚描画する（スクロール複製の描画に使う）。"""
    assert _screen is not None
    is_unavail = number in unavailable

    if override is not None:
        bg, fg = override, C_TEXT_DARK
    elif is_unavail:
        bg, fg = C_CELL_UNAVAIL, C_TEXT_LIGHT
    else:
        bg, fg = C_CELL_NORMAL, C_TEXT_DARK

    pygame.draw.rect(_screen, bg,       rect, border_radius=10)
    pygame.draw.rect(_screen, C_BORDER, rect, 2, border_radius=10)

    # 命中済みは ○ マーク（×マークは廃止）
    mark = "O" if is_unavail else ""

    ns = _fonts["num"].render(number, True, fg)
    nr = ns.get_rect(center=rect.center)
    if mark:
        nr.centery -= 12
    _screen.blit(ns, nr)

    if mark:
        ms = _fonts["mark"].render(mark, True, C_MARK_HIT)
        mr = ms.get_rect(center=(rect.centerx, rect.centery + 22))
        _screen.blit(ms, mr)


def _draw_grid(
    unavailable: set[str],
    override   : Optional[dict[str, tuple[int, int, int]]] = None,
) -> None:
    """
    3×3 グリッドをスクロール適用して描画する。

    グリッド帯にクリップし、各パネルを可視複製込みで描くことで
    連続スクロール（スロットマシン風）を表現する。
    """
    assert _screen is not None
    prev_clip = _screen.get_clip()
    band = pygame.Rect(GRID_X - 6, GRID_Y, _GRID_W + 12, _GRID_H)
    _screen.set_clip(band)
    try:
        for n in range(1, 10):
            s  = str(n)
            ov = (override or {}).get(s)
            for r in _panel_visible_rects(s):
                _draw_cell_at(r, s, unavailable, ov)
    finally:
        _screen.set_clip(prev_clip)


def _draw_launcher() -> None:
    """発射台（砲台風）を描画する。"""
    assert _screen is not None
    pygame.draw.rect(
        _screen, C_LAUNCHER,
        pygame.Rect(LAUNCH_X - 22, LAUNCH_Y - 8, 44, 16),
        border_radius=5,
    )
    pygame.draw.rect(
        _screen, C_LAUNCHER_TIP,
        pygame.Rect(LAUNCH_X - 7, LAUNCH_Y - 30, 14, 24),
        border_radius=3,
    )
    pygame.draw.circle(_screen, (198, 215, 255), (LAUNCH_X, LAUNCH_Y - 30), 6)


def _draw_traj_dots(pts: list[tuple[int, int]]) -> None:
    """
    発射台から現在の狙い方向（マウスX + 現在パワー）への予測軌跡を
    ドット列で描画する。始点は小さく暗く、終点ほど大きく明るい。
    """
    assert _screen is not None
    n_pts = len(pts)
    for i, (px, py) in enumerate(pts):
        if not (0 <= px <= WINDOW_WIDTH and 0 <= py <= WINDOW_HEIGHT):
            continue
        progress = i / max(n_pts - 1, 1)
        size     = max(2, round(3 + progress * 3))
        bright   = round(55 + progress * 155)
        color    = (
            round(bright * 0.55),
            round(bright * 0.68),
            min(255, bright + 60),
        )
        pygame.draw.circle(_screen, color, (px, py), size)


def _draw_ball(bx: float, by: float, trail: list[tuple[float, float]]) -> None:
    """ボール本体と軌跡（trail）を描画する。"""
    assert _screen is not None
    n = len(trail)
    for i, (tx, ty) in enumerate(trail):
        prog = (i + 1) / max(n, 1)
        r    = max(2, round(BALL_RADIUS * 0.55 * prog))
        c    = tuple(round(ch * prog * 0.75) for ch in C_BALL_TRAIL)
        pygame.draw.circle(_screen, c, (round(tx), round(ty)), r)
    pygame.draw.circle(_screen, C_BALL, (round(bx), round(by)), BALL_RADIUS)
    pygame.draw.circle(
        _screen, (255, 248, 192),
        (round(bx) - 4, round(by) - 4),
        BALL_RADIUS // 3,
    )


def _draw_gauge(raw: float) -> None:
    """
    発射台の下に水平パワーゲージを描画する（幅 GAUGE_W）。
    充填色は青(低)→赤(高)のグラデーション。満タンで「AUTO」を表示。
    """
    assert _screen is not None
    gx = LAUNCH_X - GAUGE_W // 2
    gy = LAUNCH_Y + 16
    pygame.draw.rect(_screen, C_GAUGE_BG, (gx, gy, GAUGE_W, GAUGE_H), border_radius=6)

    fill_w = round(GAUGE_W * max(0.0, min(raw, 1.0)))
    if fill_w > 0:
        def _ch(v: float) -> int:
            return max(0, min(255, round(v)))
        color = (
            _ch(60 + 180 * raw),          # R: 低→高で増加
            _ch(120 * (1.0 - raw) + 40),  # G: 高で減少
            _ch(200 * (1.0 - raw) + 40),  # B: 低で高
        )
        pygame.draw.rect(_screen, color, (gx, gy, fill_w, GAUGE_H), border_radius=6)

    pygame.draw.rect(_screen, C_GAUGE_BORDER, (gx, gy, GAUGE_W, GAUGE_H), 2, border_radius=6)

    if raw >= 1.0:
        s = _fonts["small"].render("AUTO 発射！", True, (255, 230, 120))
        _screen.blit(s, s.get_rect(center=(LAUNCH_X, gy + GAUGE_H + 13)))


def _draw_status(msg: str, color: tuple[int, int, int]) -> None:
    """グリッド直下のステータス行を描画する。"""
    assert _screen is not None
    y = GRID_Y + _GRID_H + 26
    s = _fonts["status"].render(msg, True, color)
    _screen.blit(s, s.get_rect(center=(WINDOW_WIDTH // 2, y)))


def _draw_hit_info(unavailable: set[str]) -> None:
    """画面最下部に「命中済み番号」の情報を描画する。"""
    assert _screen is not None
    text = (
        f"命中済み: {', '.join(sorted(unavailable))}  ({len(unavailable)}/3)"
        if unavailable
        else "まだ命中なし"
    )
    s = _fonts["small"].render(text, True, C_HIT_INFO)
    _screen.blit(s, s.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 16)))


def _draw_effect(text: str, color: tuple[int, int, int]) -> None:
    """グリッドの上に STRIKE！ / OUT... の大きなエフェクト文字を重ねる。"""
    assert _screen is not None
    cx = WINDOW_WIDTH // 2
    cy = GRID_Y + _GRID_H // 2
    # 縁取り（黒）で視認性を上げる
    for ox, oy in ((-3, -3), (3, -3), (-3, 3), (3, 3)):
        sh = _fonts["effect"].render(text, True, (10, 12, 24))
        _screen.blit(sh, sh.get_rect(center=(cx + ox, cy + oy)))
    s = _fonts["effect"].render(text, True, color)
    _screen.blit(s, s.get_rect(center=(cx, cy)))


def _full_frame(
    unavailable : set[str],
    msg         : str,
    msg_color   : tuple[int, int, int],
    traj        : Optional[list[tuple[int, int]]]           = None,
    ball        : Optional[tuple[float, float]]             = None,
    trail       : Optional[list[tuple[float, float]]]       = None,
    override    : Optional[dict[str, tuple[int, int, int]]] = None,
    gauge       : Optional[float]                           = None,
    effect      : Optional[tuple[str, tuple[int, int, int]]] = None,
) -> None:
    """
    1フレーム分を全て描画して pygame.display.flip() を呼ぶ。

    Args:
        unavailable : 命中済み番号集合
        msg         : ステータス行のメッセージ
        msg_color   : ステータス行の色
        traj        : 予測軌跡の点列（エイム表示）
        ball        : ボールの現在位置 (bx, by)
        trail       : ボールの軌跡リスト（過去位置）
        override    : 特定パネルの色を上書きする辞書
        gauge       : パワーゲージの充填率（None なら非表示）
        effect      : (テキスト, 色) の STRIKE/OUT エフェクト
    """
    assert _screen is not None

    _screen.fill(C_BG)

    # ── タイトル行 ────
    t1 = _fonts["title"].render("HIT & BLOW & STRIKEOUT", True, C_HEADER)
    _screen.blit(t1, t1.get_rect(center=(WINDOW_WIDTH // 2, 22)))
    t2 = _fonts["small"].render(
        "マウスで方向 / 押し続けて飛距離を溜め、離して投球 / ESCで終了",
        True, C_SUB,
    )
    _screen.blit(t2, t2.get_rect(center=(WINDOW_WIDTH // 2, 46)))

    # ── グリッド（動くマス） ────
    _draw_grid(unavailable, override)

    # ── 予測軌跡（エイム表示） ────
    if traj:
        _draw_traj_dots(traj)

    # ── ステータス・命中情報 ────
    _draw_status(msg, msg_color)
    _draw_hit_info(unavailable)

    # ── 発射台 ────
    _draw_launcher()

    # ── パワーゲージ ────
    if gauge is not None:
        _draw_gauge(gauge)

    # ── ボール（飛翔中のみ） ────
    if ball is not None:
        _draw_ball(ball[0], ball[1], trail or [])

    # ── エフェクト（最前面） ────
    if effect is not None:
        _draw_effect(effect[0], effect[1])

    pygame.display.flip()

# ────
# ボール飛翔アニメーション（内部関数）
# ────

def _fly_ball_to(
    landing_x  : float,
    landing_y  : float,
    unavailable: set[str],
) -> bool:
    """
    発射台から着弾点 (landing_x, landing_y) まで放物線でボールを飛ばす。

    飛翔中もスクロールは継続する（着弾判定は着弾時の盤面位置に対して行う）。

    Returns:
        True:  正常完了
        False: ウィンドウが閉じられた / ESC が押された
    """
    assert _clock is not None

    vx, vy = _calc_velocity(landing_x, landing_y)
    trail : list[tuple[float, float]] = []
    start  = time.monotonic()

    while True:
        dt = _clock.tick(FPS) / 1000.0
        _update_scroll(dt)   # 飛翔中も盤面は動き続ける

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        t = time.monotonic() - start
        if t >= FLIGHT_TIME:
            break

        # 閉じた式で位置を求める（着弾点への到達精度を保つ）
        bx = LAUNCH_X + vx * t
        by = LAUNCH_Y + vy * t + 0.5 * GRAVITY * t * t

        trail.append((bx, by))
        if len(trail) > 12:
            trail.pop(0)

        _full_frame(
            unavailable,
            "投球中…",
            C_STATUS_INFO,
            ball=(bx, by),
            trail=trail,
        )

    return True


def _fire(
    mouse_x    : int,
    hold       : float,
    unavailable: set[str],
) -> Optional[str]:
    """
    ホールド情報から着弾点を求め、飛翔アニメ後に当たり判定を返す。

    Raises:
        StrikeoutClosed: 飛翔中にウィンドウが閉じられた場合。
    """
    power_ratio, _ = _power_ratio(min(hold, MAX_HOLD_TIME))
    tx, ty = _aim_target(mouse_x, power_ratio)

    # 着弾に自然なばらつきを加える
    landing_x = tx + random.uniform(-LAND_DEV_X, LAND_DEV_X)
    landing_y = ty + random.uniform(-LAND_DEV_Y, LAND_DEV_Y)

    ok = _fly_ball_to(landing_x, landing_y, unavailable)
    if not ok:
        raise StrikeoutClosed

    # 着弾時点の（スクロール済み）盤面に対して当たり判定
    return _panel_hit((landing_x, landing_y), unavailable)

# ────
# 公開インターフェース
# ────

def reset_turn_marks() -> None:
    """
    ターン開始時のリセット。

    ×マークは廃止したため実質 no-op（互換のため関数は残す）。
    スクロールはターンを跨いで継続させるためリセットしない。
    """
    _miss_marks.clear()


def get_throw_target(
    unavailable_numbers: set[str],
) -> str | None:
    """
    ホールド投球でボールを投げ、物理的な着弾判定の結果を返す。

    操作:
        マウスX      → 発射角度（左右）
        マウス長押し → パワーを溜める（青→赤ゲージ、飛距離が伸びる）
        ボタンを離す → 投球（満タンで自動発射）
        ESC / ×     → StrikeoutClosed

    Args:
        unavailable_numbers:
            そのターンに既に命中した番号の集合（選択不可・グレー表示）。

    Returns:
        "1"〜"9": 物理的に命中したパネルの番号
        None:     どのパネルにも当たらなかった（外れ）

    Raises:
        StrikeoutClosed: ウィンドウが閉じられた / ESC が押された。
    """
    _ensure_init()
    assert _clock is not None

    holding    = False
    hold_start = 0.0

    while True:
        dt  = _clock.tick(FPS) / 1000.0
        _update_scroll(dt)          # 動くマスは常にスクロール
        now = time.monotonic()
        mouse_x, _ = pygame.mouse.get_pos()

        fire_hold: Optional[float] = None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise StrikeoutClosed
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                raise StrikeoutClosed
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                holding    = True
                hold_start = now
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and holding:
                fire_hold = now - hold_start
                holding   = False

        # 満タンで自動発射
        if holding and (now - hold_start) >= MAX_HOLD_TIME:
            fire_hold = MAX_HOLD_TIME
            holding   = False

        if fire_hold is not None:
            return _fire(mouse_x, fire_hold, unavailable_numbers)

        # ── エイム表示（軌跡ドット + ゲージ） ────
        hold = (now - hold_start) if holding else 0.0
        power_ratio, raw = _power_ratio(hold)
        tx, ty = _aim_target(mouse_x, power_ratio)
        vx, vy = _calc_velocity(tx, ty)
        traj   = _trajectory_pts(vx, vy)

        if holding:
            msg = "溜め中… 離して投球（満タンで自動発射）"
        else:
            msg = "押し続けて飛距離を溜める → 離して投球"

        _full_frame(
            unavailable_numbers,
            msg,
            C_STATUS_INFO,
            traj=traj,
            gauge=raw,
        )


def show_throw_result(
    hit_number         : str | None,
    unavailable_numbers: set[str],
) -> None:
    """
    投球結果を STRIKE！ / OUT... エフェクトで表示する。

    命中（hit_number is not None）:
        対象パネルを緑色でハイライトし、「STRIKE！」（緑）を表示。
    外れ（hit_number is None）:
        「OUT...」（赤）を表示（パネルは特定しない）。

    表示中もスクロールは継続する。SPACE / ENTER で早送りできる。

    Args:
        hit_number:          命中したパネル番号。外れは None。
        unavailable_numbers: 命中済みの番号集合（○表示用）。
    """
    _ensure_init()
    assert _clock is not None

    is_hit = hit_number is not None
    if is_hit:
        effect     = ("STRIKE！", C_STATUS_OK)
        status_msg = f"命中！ 「{hit_number}」を獲得"
        status_col = C_STATUS_OK
        override   = {hit_number: C_CELL_HIT}
    else:
        effect     = ("OUT...", C_STATUS_NG)
        status_msg = "外れ… パネルに当たりませんでした"
        status_col = C_STATUS_NG
        override   = None

    deadline = time.monotonic() + ANIM_RESULT_SEC
    while time.monotonic() < deadline:
        dt = _clock.tick(FPS) / 1000.0
        _update_scroll(dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_SPACE, pygame.K_RETURN
            ):
                return

        _full_frame(
            unavailable_numbers,
            status_msg,
            status_col,
            override=override,
            effect=effect,
        )

# ────
# __main__: スタンドアロンテスト（サーバーなし・物理演算版）
# ────

if __name__ == "__main__":
    """
    サーバーなしで動作確認できるテストモード。

    命中/外れは確率ではなく「物理的な着弾判定」で決まる。
    3球投げ終わったら予想（guess）を画面とターミナルに表示する。

    操作:
      マウス移動    → 発射角度
      マウス長押し  → 飛距離を溜める（離して投球・満タンで自動発射）
      SPACE/ENTER  → 結果表示を早送り
      ESC / ×     → 終了
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from strikeout import (
        create_empty_throw_results,
        record_throw,
        is_turn_complete,
        to_guess,
    )

    print("=" * 54)
    print("strikeout_gui.py  スタンドアロンテスト（物理演算版）")
    print("操作: マウスで方向 / 長押しで飛距離 / 離して投球 / ESC で終了")
    print("命中判定: 確率ではなく物理的な着弾で決定")
    print("=" * 54)

    reset_turn_marks()
    throw_results = create_empty_throw_results()
    unavailable   : set[str] = set()

    try:
        for throw_idx in range(3):
            print(f"\n--- {throw_idx + 1} 球目 ---")

            # ① 物理演算で投球 → 命中番号 or 外れ(None) が直接返る
            hit = get_throw_target(unavailable)
            print(f"  結果: {'命中 ' + str(hit) if hit else '外れ'}")

            # ② 命中なら unavailable に追加（次球から選択不可）
            if hit is not None:
                unavailable.add(hit)

            # ③ 投球結果を strikeout.py のデータ構造に記録
            throw_results = record_throw(throw_results, hit)

            # ④ 結果エフェクトを表示
            show_throw_result(hit, unavailable)
    except StrikeoutClosed:
        print("ウィンドウを閉じました。終了します。")
        pygame.quit()
        sys.exit(0)

    # ── 3球終了: 予想を作成・表示 ────
    guess         = to_guess(throw_results)
    guess_display = "".join(g if g is not None else "X" for g in guess)

    print(f"\n=== 3球終了 ===")
    print(f"予想  : {guess_display}")
    print(f"内部  : {guess}")
    print(f"命中済: {sorted(unavailable)}")

    # ── 最終画面を表示して待機 ────
    _ensure_init()
    assert _screen is not None
    assert _clock  is not None

    _screen.fill(C_BG)
    r1 = _fonts["effect"].render(f"予想:  {guess_display}", True, (255, 212, 65))
    r2 = _fonts["status"].render("何かキーを押すか × で終了", True, (135, 138, 178))
    _screen.blit(r1, r1.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 28)))
    _screen.blit(r2, r2.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 42)))
    pygame.display.flip()

    waiting = True
    while waiting:
        for ev in pygame.event.get():
            if ev.type in (pygame.QUIT, pygame.KEYDOWN):
                waiting = False
        _clock.tick(30)

    pygame.quit()
    sys.exit(0)
