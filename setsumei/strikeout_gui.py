"""
strikeout_gui.py - ストラックアウトGUIモジュール（物理演算版）

責務:
  - Pygame で 3×3 のストラックアウト盤面を描画する
  - 物理演算によるボール投球操作を受け付け、照準パネルの番号を返す
  - サーバーから受け取った投球結果（命中/外れ）を画面に表示する
  - 命中済みのマスをそのターン中は選択不可として描画する

物理演算ゲームプレイ（get_throw_target の流れ）:
  1. マウスを動かす  → 最も近い有効なパネルが黄色にハイライト（照準）される
  2. 照準パネルへの  → 放物線の予測軌跡がドット列でプレビュー表示される
  3. クリックする    → ボールが初速度 + 重力による放物線運動でアニメーション
  4. 着弾           → 照準していたパネルの番号を返す

担当しないこと:
  - Hit / Blow の計算
  - WebSocket の送受信
  - ゲームの進行管理（ターン数・球数の管理）

外部から使う関数（公開インターフェース）:
  reset_turn_marks()                                      → None
  get_throw_target(unavailable_numbers: set[str])         → str | None
  show_throw_result(target, hit_number, unavailable)      → None
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

# ──────────────────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────────────────

WINDOW_WIDTH  = 580
WINDOW_HEIGHT = 700
WINDOW_TITLE  = "Hit & Blow - ストラックアウト"
FPS = 60

# ── グリッド ──────────────────────────────────────────────
CELL_SIZE = 120
CELL_GAP  = 14
GRID_COLS = 3
GRID_ROWS = 3
_GRID_W   = GRID_COLS * CELL_SIZE + (GRID_COLS - 1) * CELL_GAP  # 388 px
_GRID_H   = GRID_ROWS * CELL_SIZE + (GRID_ROWS - 1) * CELL_GAP  # 388 px
GRID_X    = (WINDOW_WIDTH - _GRID_W) // 2   # 96
GRID_Y    = 75                               # グリッド上端 Y 座標

# 盤面配置:
#   [1][2][3]   row=0 (y: 75〜195)
#   [4][5][6]   row=1 (y: 209〜329)
#   [7][8][9]   row=2 (y: 343〜463)

# ── 発射台 ────────────────────────────────────────────────
LAUNCH_X = WINDOW_WIDTH // 2   # 290 (画面水平中央)
LAUNCH_Y = 640                  # 発射台の Y 座標

# ── 物理演算 ──────────────────────────────────────────────
GRAVITY     = 700.0   # 重力加速度 [px/s²]
FLIGHT_TIME = 0.80    # 発射 → 照準パネル中心に到達するまでの秒数
BALL_RADIUS = 14      # ボールの半径 [px]

# 投球のランダム偏差（毎回の投球に自然なばらつきを加える）
THROW_DEV_VX = 35.0   # 水平速度の偏差 ±px/s
THROW_DEV_VY = 20.0   # 垂直速度の偏差 ±px/s

# ── アニメーション時間 ────────────────────────────────────
ANIM_LANDING_SEC = 0.18   # 着弾後のホールド秒数（サーバー応答待ち中の演出）
ANIM_RESULT_SEC  = 1.4    # 命中/外れ結果を表示する秒数

# ── 色 ───────────────────────────────────────────────────
C_BG           = ( 20,  26,  48)   # 背景（濃紺）
C_HEADER       = (200, 210, 245)   # タイトル文字
C_SUB          = ( 95, 105, 155)   # サブタイトル文字
C_BORDER       = ( 48,  56,  86)   # マス枠線

C_CELL_NORMAL  = (193, 198, 218)   # 通常マス
C_CELL_AIMED   = (255, 218,  55)   # 照準中のマス（黄）
C_CELL_UNAVAIL = ( 62,  70,  98)   # 命中済みマス（暗いグレー）
C_CELL_HIT     = ( 58, 198, 108)   # 命中確定（緑）
C_CELL_MISS    = (198,  62,  62)   # 外れ確定（赤）

C_TEXT_DARK    = ( 16,  20,  38)   # 明るいマス上のテキスト
C_TEXT_LIGHT   = (185, 195, 222)   # 暗いマス上のテキスト
C_MARK_HIT     = (188, 252, 208)   # ○マーク色
C_MARK_MISS    = (252, 182, 182)   # ×マーク色

C_BALL         = (255, 198,  38)   # ボール本体（黄）
C_BALL_TRAIL   = (180, 115,   0)   # ボール軌跡
C_STATUS_INFO  = (178, 183, 218)   # 案内メッセージ
C_STATUS_OK    = ( 78, 218, 128)   # 命中メッセージ（緑）
C_STATUS_NG    = (218,  78,  78)   # 外れメッセージ（赤）
C_HIT_INFO     = (118, 188, 128)   # 命中済み一覧テキスト
C_LAUNCHER     = ( 88,  98, 138)   # 発射台本体
C_LAUNCHER_TIP = (118, 132, 175)   # 砲口

# ──────────────────────────────────────────────────────────
# モジュール内部状態
# ──────────────────────────────────────────────────────────

_screen    : Optional[pygame.Surface]      = None
_clock     : Optional[pygame.time.Clock]  = None
_fonts     : dict[str, pygame.font.Font]   = {}

# このターンで「外れ」になったパネル番号（×マーク表示用）
# ○マーク（命中済み）は unavailable_numbers から自動描画するのでここに不要
_miss_marks: set[str] = set()

# ──────────────────────────────────────────────────────────
# 初期化
# ──────────────────────────────────────────────────────────

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
    _fonts["num"]    = pygame.font.SysFont(None, 56)   # マス内の数字
    _fonts["mark"]   = pygame.font.SysFont(None, 44)   # ○ × マーク
    _fonts["title"]  = pygame.font.SysFont(None, 26)   # タイトル
    _fonts["status"] = pygame.font.SysFont(None, 23)   # ステータス行
    _fonts["small"]  = pygame.font.SysFont(None, 20)   # 補助テキスト

# ──────────────────────────────────────────────────────────
# 座標・物理ユーティリティ
# ──────────────────────────────────────────────────────────

def _cell_rect(number: str) -> pygame.Rect:
    """
    数字 "1"〜"9" に対応するマスの pygame.Rect を返す。

    盤面レイアウト:
        [1][2][3]   row=0
        [4][5][6]   row=1
        [7][8][9]   row=2
    """
    n   = int(number) - 1
    col = n % GRID_COLS
    row = n // GRID_COLS
    x   = GRID_X + col * (CELL_SIZE + CELL_GAP)
    y   = GRID_Y + row * (CELL_SIZE + CELL_GAP)
    return pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)


def _cell_center(number: str) -> tuple[float, float]:
    """マスの中心座標 (cx, cy) を float で返す。"""
    r = _cell_rect(number)
    return float(r.centerx), float(r.centery)


def _nearest_valid_panel(
    pos: tuple[int, int],
    unavailable: set[str],
) -> Optional[str]:
    """
    マウス座標に最も近い「有効な（命中済みでない）」パネルの番号を返す。

    全て unavailable の場合は None（通常のゲームプレイでは発生しない）。
    """
    bx, by   = pos
    best_num = None
    best_d2  = float("inf")
    for n in range(1, 10):
        s = str(n)
        if s in unavailable:
            continue
        cx, cy = _cell_center(s)
        d2 = (bx - cx) ** 2 + (by - cy) ** 2
        if d2 < best_d2:
            best_d2, best_num = d2, s
    return best_num


def _calc_velocity(tx: float, ty: float) -> tuple[float, float]:
    """
    発射台 (LAUNCH_X, LAUNCH_Y) から (tx, ty) を
    FLIGHT_TIME 秒後に通過するための初速度 (vx, vy) を返す。

    物理式（Y 軸は下向き正）:
        tx = LAUNCH_X + vx * T            → vx = (tx - LAUNCH_X) / T
        ty = LAUNCH_Y + vy * T + ½g T²   → vy = (ty - LAUNCH_Y) / T - ½g T

    計算例（パネル 5 の中心 = (290, 269)）:
        T  = 0.8
        vx = (290 - 290) / 0.8       = 0.0       (真上に発射)
        vy = (269 - 640) / 0.8 - 280 = -743.75   (上向き初速度)
    """
    T  = FLIGHT_TIME
    vx = (tx - LAUNCH_X) / T
    vy = (ty - LAUNCH_Y) / T - 0.5 * GRAVITY * T
    return vx, vy


def _trajectory_pts(
    vx: float,
    vy: float,
    steps: int = 22,
) -> list[tuple[int, int]]:
    """
    (vx, vy) で発射したボールの放物線軌跡の点列を返す。

    t = 0 〜 FLIGHT_TIME を steps+1 個の等間隔で計算する。
    最初の点が発射台 (LAUNCH_X, LAUNCH_Y)、
    最後の点が照準パネルの中心になる。
    """
    pts = []
    T   = FLIGHT_TIME
    for i in range(steps + 1):
        t  = i * T / steps
        px = LAUNCH_X + vx * t
        py = LAUNCH_Y + vy * t + 0.5 * GRAVITY * t * t
        pts.append((round(px), round(py)))
    return pts

# ──────────────────────────────────────────────────────────
# 描画ヘルパー
# ──────────────────────────────────────────────────────────

def _draw_cell(
    number   : str,
    unavailable: set[str],
    aimed    : Optional[str],
    override : Optional[tuple[int, int, int]],
) -> None:
    """
    1マスを描画する。

    背景色の優先順位:
      override（アニメーション用色） > aimed（照準中・黄）
      > unavailable（命中済み・暗グレー） > normal（通常・薄グレー）
    """
    assert _screen is not None
    rect       = _cell_rect(number)
    is_unavail = number in unavailable
    is_miss    = number in _miss_marks

    if override is not None:
        bg, fg = override, C_TEXT_DARK
    elif number == aimed:
        bg, fg = C_CELL_AIMED, C_TEXT_DARK
    elif is_unavail:
        bg, fg = C_CELL_UNAVAIL, C_TEXT_LIGHT
    else:
        bg, fg = C_CELL_NORMAL, C_TEXT_DARK

    pygame.draw.rect(_screen, bg,       rect, border_radius=10)
    pygame.draw.rect(_screen, C_BORDER, rect, 2, border_radius=10)

    # ○（命中済み）or ×（このターンの外れ）マークを決定
    if is_unavail:
        mark, mc = "O", C_MARK_HIT
    elif is_miss:
        mark, mc = "X", C_MARK_MISS
    else:
        mark, mc = "", C_MARK_HIT   # mark == "" のときは描画しない

    # 数字テキスト（マークがあれば上にずらす）
    ns = _fonts["num"].render(number, True, fg)
    nr = ns.get_rect(center=rect.center)
    if mark:
        nr.centery -= 14
    _screen.blit(ns, nr)

    if mark:
        ms = _fonts["mark"].render(mark, True, mc)
        mr = ms.get_rect(center=(rect.centerx, rect.centery + 20))
        _screen.blit(ms, mr)


def _draw_grid(
    unavailable: set[str],
    aimed      : Optional[str]                               = None,
    override   : Optional[dict[str, tuple[int, int, int]]]   = None,
) -> None:
    """3×3 グリッド全体（9マス）を描画する。"""
    for n in range(1, 10):
        s  = str(n)
        ov = (override or {}).get(s)
        _draw_cell(s, unavailable, aimed, ov)


def _draw_launcher() -> None:
    """
    発射台（砲台風）を描画する。
    LAUNCH_X, LAUNCH_Y を中心とした小さな砲台アイコン。
    """
    assert _screen is not None
    # 台座（横長の矩形）
    pygame.draw.rect(
        _screen, C_LAUNCHER,
        pygame.Rect(LAUNCH_X - 22, LAUNCH_Y - 8, 44, 16),
        border_radius=5,
    )
    # 砲身（縦長の矩形、上向き）
    pygame.draw.rect(
        _screen, C_LAUNCHER_TIP,
        pygame.Rect(LAUNCH_X - 7, LAUNCH_Y - 30, 14, 24),
        border_radius=3,
    )
    # 砲口（小さな円）
    pygame.draw.circle(_screen, (198, 215, 255), (LAUNCH_X, LAUNCH_Y - 30), 6)


def _draw_traj_dots(pts: list[tuple[int, int]]) -> None:
    """
    照準中の放物線予測軌跡をドット列で描画する。

    発射台（始点）では小さく暗く、
    パネル（終点）に近づくほど大きく明るくなる。
    """
    assert _screen is not None
    n_pts = len(pts)
    for i, (px, py) in enumerate(pts):
        # 画面外は描画しない
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


def _draw_ball(
    bx   : float,
    by   : float,
    trail: list[tuple[float, float]],
) -> None:
    """
    ボール本体と軌跡（trail）を描画する。

    trail は過去の位置リスト（古い順）。
    古い点ほど暗く小さく、新しい点ほど明るく大きい。
    """
    assert _screen is not None

    # ── 軌跡 ──────────────────────────────────────
    n = len(trail)
    for i, (tx, ty) in enumerate(trail):
        prog = (i + 1) / max(n, 1)
        r    = max(2, round(BALL_RADIUS * 0.55 * prog))
        c    = tuple(round(ch * prog * 0.75) for ch in C_BALL_TRAIL)
        pygame.draw.circle(_screen, c, (round(tx), round(ty)), r)

    # ── ボール本体 ────────────────────────────────
    pygame.draw.circle(_screen, C_BALL, (round(bx), round(by)), BALL_RADIUS)
    # ハイライト（艶）
    pygame.draw.circle(
        _screen, (255, 248, 192),
        (round(bx) - 4, round(by) - 4),
        BALL_RADIUS // 3,
    )


def _draw_status(msg: str, color: tuple[int, int, int]) -> None:
    """グリッド直下のステータス行を描画する。"""
    assert _screen is not None
    y = GRID_Y + _GRID_H + 28
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
    _screen.blit(s, s.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 18)))


def _full_frame(
    unavailable : set[str],
    msg         : str,
    msg_color   : tuple[int, int, int],
    aimed       : Optional[str]                              = None,
    traj        : Optional[list[tuple[int, int]]]            = None,
    ball        : Optional[tuple[float, float]]              = None,
    trail       : Optional[list[tuple[float, float]]]        = None,
    override    : Optional[dict[str, tuple[int, int, int]]]  = None,
) -> None:
    """
    1フレーム分を全て描画して pygame.display.flip() を呼ぶ。

    Args:
        unavailable : 命中済み番号集合
        msg         : ステータス行のメッセージ
        msg_color   : ステータス行の色
        aimed       : 照準中のパネル番号（黄色ハイライト）
        traj        : 放物線プレビュー点列（照準中のみ）
        ball        : ボールの現在位置 (bx, by)
        trail       : ボールの軌跡リスト（過去位置）
        override    : 特定パネルの色を上書きする辞書（アニメーション用）
    """
    assert _screen is not None

    _screen.fill(C_BG)

    # ── タイトル行 ────────────────────────────────
    t1 = _fonts["title"].render("STRIKOUT  HIT & BLOW", True, C_HEADER)
    _screen.blit(t1, t1.get_rect(center=(WINDOW_WIDTH // 2, 22)))
    t2 = _fonts["small"].render(
        "マウスで照準 → クリックで投球 / ESC で終了", True, C_SUB
    )
    _screen.blit(t2, t2.get_rect(center=(WINDOW_WIDTH // 2, 45)))

    # ── グリッド ──────────────────────────────────
    _draw_grid(unavailable, aimed, override)

    # ── 軌跡プレビュー（照準中のみ） ─────────────
    if traj:
        _draw_traj_dots(traj)

    # ── ステータス・命中情報 ──────────────────────
    _draw_status(msg, msg_color)
    _draw_hit_info(unavailable)

    # ── 発射台 ────────────────────────────────────
    _draw_launcher()

    # ── ボール（飛翔アニメーション中のみ） ────────
    if ball is not None:
        _draw_ball(ball[0], ball[1], trail or [])

    pygame.display.flip()

# ──────────────────────────────────────────────────────────
# ボール飛翔アニメーション（内部関数）
# ──────────────────────────────────────────────────────────

def _fly_ball(
    vx0        : float,
    vy0        : float,
    aimed      : str,
    unavailable: set[str],
) -> bool:
    """
    ボールを物理演算で飛ばすアニメーションを再生する。

    フェーズ 1（飛翔）:
        FLIGHT_TIME 秒間、重力付きの放物線運動でボールを動かす。
        毎フレーム vy += GRAVITY * dt、bx/by を更新して描画。

    フェーズ 2（着弾ホールド）:
        ANIM_LANDING_SEC 秒間、ボールをパネル中心に静止させる。
        サーバー応答待ちの間の演出として機能する。

    Args:
        vx0, vy0:    初速度（THROW_DEV による偏差を含む）
        aimed:       照準したパネル番号
        unavailable: 命中済み番号集合（描画用）

    Returns:
        True:  正常完了（ウィンドウはそのまま）
        False: ウィンドウが閉じられた
    """
    assert _clock is not None

    bx    = float(LAUNCH_X)
    by    = float(LAUNCH_Y)
    vx    = float(vx0)
    vy    = float(vy0)
    trail : list[tuple[float, float]] = []
    dt    = 1.0 / FPS

    # ─── フェーズ 1: 飛翔 ──────────────────────────
    start = time.monotonic()
    while time.monotonic() - start < FLIGHT_TIME:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

        # 物理更新（重力加速度を加算）
        vy += GRAVITY * dt
        bx += vx * dt
        by += vy * dt

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
        _clock.tick(FPS)

    # ─── フェーズ 2: 着弾ホールド ────────────────
    tx, ty   = _cell_center(aimed)
    hold_end = time.monotonic() + ANIM_LANDING_SEC

    while time.monotonic() < hold_end:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

        _full_frame(
            unavailable,
            f"「{aimed}」に着弾！",
            C_STATUS_INFO,
            ball=(tx, ty),
            trail=[],
            override={aimed: C_CELL_AIMED},   # 着弾パネルを黄色でホールド
        )
        _clock.tick(FPS)

    return True

# ──────────────────────────────────────────────────────────
# 公開インターフェース
# ──────────────────────────────────────────────────────────

def reset_turn_marks() -> None:
    """
    ターン開始時に外れマーク（×）をリセットする。

    game.py が各ターン開始時に呼び出すこと。
    呼ばないと前のターンの外れマークが画面に残り続ける。
    """
    _miss_marks.clear()


def get_throw_target(
    unavailable_numbers: set[str],
) -> str | None:
    """
    物理演算によるストラックアウト画面を表示し、投球したパネルの番号を返す。

    ゲームフロー:
        マウス移動    → 最も近い有効パネルが黄色にハイライトされる
        軌跡プレビュー → 発射台からそのパネルへの放物線がドットで表示される
        マウスクリック → ボールが物理演算（重力付きパラボラ）で飛ぶ
        着弾後         → 照準していたパネルの番号を返す

    インターフェース仕様:
        - 戻り値は「照準していたパネル」の番号 ("1"〜"9")
        - 物理偏差でボールが視覚的に少しずれることがあるが、
          戻り値は常に「照準パネル番号」であり、サーバーが最終判定する
        - ESC キー / ウィンドウ × ボタン で None を返す

    Args:
        unavailable_numbers:
            そのターンに既に命中した番号の集合。
            これらのパネルはグレーアウトされ、照準不可になる。

    Returns:
        "1"〜"9": 投球したパネルの番号
        None:     ESC キーまたはウィンドウを閉じた場合
    """
    _ensure_init()
    assert _clock is not None

    while True:
        # ── イベント処理 ──────────────────────────
        mouse_pos = pygame.mouse.get_pos()
        aimed     = _nearest_valid_panel(mouse_pos, unavailable_numbers)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if aimed is not None:
                    # 照準パネルへの正確な初速度を計算
                    tx, ty = _cell_center(aimed)
                    vx, vy = _calc_velocity(tx, ty)
                    # ランダム偏差を加えて投球の自然なばらつきを表現
                    vx += random.uniform(-THROW_DEV_VX, THROW_DEV_VX)
                    vy += random.uniform(-THROW_DEV_VY, THROW_DEV_VY)
                    # 飛翔アニメーションを再生
                    ok = _fly_ball(vx, vy, aimed, unavailable_numbers)
                    if not ok:
                        return None   # ウィンドウが閉じられた
                    return aimed      # 照準していたパネル番号を返す

        # ── 描画 ─────────────────────────────────
        # 照準パネルへの軌跡プレビューを計算
        traj = None
        if aimed is not None:
            tx, ty = _cell_center(aimed)
            vx_a, vy_a = _calc_velocity(tx, ty)
            traj = _trajectory_pts(vx_a, vy_a)

        msg = (
            f"「{aimed}」を照準中 → クリックで投球"
            if aimed is not None
            else "照準中…"
        )
        _full_frame(
            unavailable_numbers,
            msg,
            C_STATUS_INFO,
            aimed=aimed,
            traj=traj,
        )
        _clock.tick(FPS)


def show_throw_result(
    target_number      : str,
    hit_number         : str | None,
    unavailable_numbers: set[str],
) -> None:
    """
    サーバーが確定した投球結果を画面に表示する。

    表示内容:
        命中（hit_number is not None）: 対象パネルを緑色でハイライト + 「命中！」
        外れ（hit_number is None）:     対象パネルを赤色でハイライト + 「外れ…」

    外れの場合は _miss_marks に target_number を追加し、
    次フレームから × マークが表示されるようにする。

    SPACE / ENTER キーで早送りできる。ウィンドウは閉じない。

    Args:
        target_number:       プレイヤーが投球したパネルの番号 ("1"〜"9")
        hit_number:          サーバーが確定した命中番号。外れは None。
        unavailable_numbers: 既に命中済みの番号集合。
    """
    _ensure_init()
    assert _clock is not None

    is_hit     = hit_number is not None
    cell_color = C_CELL_HIT  if is_hit else C_CELL_MISS
    status_msg = f"【{target_number}】 命中！" if is_hit else f"【{target_number}】 外れ…"
    status_col = C_STATUS_OK if is_hit else C_STATUS_NG

    # 外れの場合はこのターンの外れマークに登録（× 表示用）
    if not is_hit:
        _miss_marks.add(target_number)

    deadline = time.monotonic() + ANIM_RESULT_SEC
    while time.monotonic() < deadline:
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
            override={target_number: cell_color},
        )
        _clock.tick(FPS)

# ──────────────────────────────────────────────────────────
# __main__: スタンドアロンテスト（サーバーなし・物理演算版）
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    サーバーなしで動作確認できるテストモード。

    動作:
      - マウスで照準してクリックで投球できる
      - 投球結果は 65% の確率で命中、35% で外れのランダム判定
      - 3球終了後に予想（guess）を画面とターミナルに表示する
      - 実際のゲームと全く同じ関数呼び出し順で動作する

    操作:
      マウス移動    → パネルを照準
      クリック     → 投球（物理演算アニメーション）
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
    print("操作: マウスで照準 → クリックで投球 / ESC で終了")
    print("サーバーなしモード: 命中確率 65% のランダム判定")
    print("=" * 54)

    # ターン開始: 外れマークをリセット
    reset_turn_marks()
    throw_results = create_empty_throw_results()
    unavailable   : set[str] = set()

    for throw_idx in range(3):
        print(f"\n--- {throw_idx + 1} 球目 ---")

        # ① GUI で照準・投球させる（物理演算アニメーション付き）
        target = get_throw_target(unavailable)
        if target is None:
            print("ウィンドウを閉じました。終了します。")
            pygame.quit()
            sys.exit(0)

        print(f"  照準パネル: {target}")

        # ② サーバー処理をシミュレート（65% 命中）
        hit: str | None = target if random.random() < 0.65 else None
        print(f"  結果: {'命中 ' + str(hit) if hit else '外れ'}")

        # ③ 命中なら unavailable に追加（次球から選択不可）
        if hit is not None:
            unavailable.add(hit)

        # ④ 投球結果を strikeout.py のデータ構造に記録
        throw_results = record_throw(throw_results, hit)

        # ⑤ GUI にサーバー確定結果を表示
        show_throw_result(target, hit, unavailable)

    # ── 3球終了: 予想を作成・表示 ──────────────────
    guess         = to_guess(throw_results)
    guess_display = "".join(g if g is not None else "X" for g in guess)

    print(f"\n=== 3球終了 ===")
    print(f"予想  : {guess_display}")
    print(f"内部  : {guess}")
    print(f"命中済: {sorted(unavailable)}")

    # ── 最終画面を表示して待機 ──────────────────────
    _ensure_init()
    assert _screen is not None
    assert _clock  is not None

    _screen.fill(C_BG)

    f_big = pygame.font.SysFont(None, 58)
    f_sub = pygame.font.SysFont(None, 26)
    r1 = f_big.render(f"予想:  {guess_display}", True, (255, 212, 65))
    r2 = f_sub.render("何かキーを押すか × で終了", True, (135, 138, 178))

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
