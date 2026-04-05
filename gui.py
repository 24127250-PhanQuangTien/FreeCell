import tkinter as tk
from tkinter import ttk
import threading
import os
import random
import copy
import csv
from PIL import Image, ImageTk

from optimized import bfs_optimized, dfs_optimized, ucs_optimized, astar_optimized
import game as _game_module
from utilities import SUITS, SUIT_IDX, EMPTY, apply_safe_auto_moves

_SUIT_ORDER = ["H", "D", "C", "S"]

def _to_int_state(gui_state: dict) -> dict:
    """GUI state → int-based state (cho solver / apply_move nội bộ)."""
    foundations = tuple(gui_state["foundations"][s] for s in _SUIT_ORDER)
    freecells   = tuple(
        SUIT_IDX[c[0]] * 13 + (c[1] - 1) if c is not None else EMPTY
        for c in gui_state["freecells"]
    )
    cascades = tuple(
        tuple(SUIT_IDX[s] * 13 + (r - 1) for s, r in col)
        for col in gui_state["cascades"]
    )
    return {"foundations": foundations, "freecells": freecells, "cascades": cascades}


def _to_gui_state(int_state: dict) -> dict:
    """Int-based state → GUI state (sau apply_move)."""
    foundations = {s: int_state["foundations"][i] for i, s in enumerate(_SUIT_ORDER)}
    freecells   = [
        (SUITS[c // 13], c % 13 + 1) if c != EMPTY else None
        for c in int_state["freecells"]
    ]
    cascades = [
        [(SUITS[c // 13], c % 13 + 1) for c in col]
        for col in int_state["cascades"]
    ]
    return {"foundations": foundations, "freecells": freecells, "cascades": cascades}


def apply_move(gui_state: dict, move) -> dict:
    """Wrapper: nhận GUI state, trả GUI state. Bridge qua game.apply_move."""
    return _to_gui_state(_game_module.apply_move(_to_int_state(gui_state), move))


def create_initial_state(gamenumber: int) -> dict:
    return _to_gui_state(_game_module.create_initial_state(gamenumber))


def create_instruction_state() -> dict:
    return _to_gui_state(_game_module.create_instruction_state())

# ────────────────
# Layout constants
# ────────────────
CARD_W    = 96
CARD_H    = 144
COL_GAP   = 142
START_X   = 95
START_Y   = 260
TOP_Y     = 80
CASCADE_Y_STEP = 32

WIN_W     = 1280
WIN_H     = 720

BAR_H     = 56

# Colors (Regal Blue & Gold Theme)
BG          = "#0a1128"
FELT        = "#102a43"
BTN_BG      = "#1e3a8a"
BTN_ACTIVE  = "#2563eb"
BTN_BORDER  = "#3b82f6"

LOG_BG      = "#0f172a"
LOG_BORDER  = "#1e40af"

ACCENT      = "#fcd34d"
ACCENT2     = "#f59e0b"

BTN_TEXT    = "#fef08a" 
TEXT_DIM    = "#bca878"
TEXT_MID    = "#eab308"
TEXT_BRIGHT = "#fffbeb"

SUIT_COLOR  = {"H": "#ef5350", "D": "#e9413e", "C": "#000000", "S": "#000000"}


def move_to_label(move):
    """Convert move tuple → human-readable Vietnamese label."""
    if not move:
        return ""
    t = move[0]

    if t == "cascade_to_foundation":
        return f"Cột {move[1]+1} ➔ Đích"
    if t == "freecell_to_foundation":
        return f"Free {move[1]+1} ➔ Đích"
    if t == "cascade_to_freecell":
        return f"Cột {move[1]+1} ➔ Free {move[2]+1}"
    if t == "freecell_to_cascade":
        return f"Free {move[1]+1} ➔ Cột {move[2]+1}"
    if t == "cascade_to_cascade":
        return f"Cột {move[1]+1} ➔ Cột {move[2]+1}"
    return str(move)


# ────────────
# Seed Dialog
# ────────────
class SeedDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("New Game")
        self.configure(bg=FELT)
        self.resizable(False, False)
        self.grab_set()
        self._cancel_flag = False

        self.geometry(f"360x220+{parent.winfo_rootx()+460}+{parent.winfo_rooty()+250}")

        # Title
        tk.Label(self, text="🂠  NEW GAME", font=("Georgia", 16, "bold"),
                 fg=ACCENT, bg=FELT).pack(pady=(20, 6))
                 
        tk.Label(self, text="Nhập seed để tái tạo ván bài,\nhoặc để trống để deal ngẫu nhiên.",
                 font=("Consolas", 10), fg=TEXT_BRIGHT, bg=FELT, justify="center").pack()

        # Seed entry
        frame = tk.Frame(self, bg=FELT)
        frame.pack(pady=16)
        tk.Label(frame, text="Seed:", font=("Consolas", 11, "bold"),
                 fg=BTN_TEXT, bg=FELT).pack(side=tk.LEFT, padx=6)
                 
        self.entry = tk.Entry(frame, width=16, font=("Consolas", 12, "bold"),
                              bg=LOG_BG, fg=ACCENT2, insertbackground=ACCENT2,
                              relief="solid", bd=1, highlightthickness=1, highlightbackground=BTN_BORDER)
        self.entry.pack(side=tk.LEFT)

        # Buttons
        btn_frame = tk.Frame(self, bg=FELT)
        btn_frame.pack(pady=6)

        def make_btn(parent, text, cmd, accent=False):
            c = ACCENT if accent else BTN_BG
            tc = BG if accent else BTN_TEXT
            b = tk.Button(parent, text=text, command=cmd,
                          font=("Consolas", 10, "bold"),
                          bg=c, fg=tc, activebackground=BTN_ACTIVE,
                          activeforeground=TEXT_BRIGHT, relief="flat",
                          bd=0, padx=16, pady=6, cursor="hand2")
            b.pack(side=tk.LEFT, padx=8)
            return b

        make_btn(btn_frame, "Random", self._random)
        make_btn(btn_frame, "Deal ▶", self._ok, accent=True)

        self.entry.bind("<Return>", lambda e: self._ok())
        self.entry.focus_set()

    def _random(self):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, str(random.randint(1, 99999)))

    def _ok(self):
        txt = self.entry.get().strip()
        self.result = int(txt) if txt.isdigit() else None
        self.destroy()


# ──────────────
# Move Log Strip 
# ──────────────
class MoveLogStrip(tk.Frame):
    """
    Hiển thị 3 nước đi: [trước] ➔ [HIỆN TẠI] ➔ [sắp tới]
    """
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=LOG_BG, width=540, height=36,
                         highlightthickness=1, highlightbackground=LOG_BORDER, **kw)
        self.pack_propagate(False)

        self.content = tk.Frame(self, bg=LOG_BG)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.idx_var = tk.StringVar(value="")
        tk.Label(self.content, textvariable=self.idx_var,
                 font=("Consolas", 8), fg=TEXT_DIM, bg=LOG_BG).pack(side=tk.LEFT, padx=(0, 15))

        # Các label hiển thị nước đi
        self.lbl_prev = tk.Label(self.content, text="", font=("Consolas", 8), fg=TEXT_DIM, bg=LOG_BG)
        self.lbl_prev.pack(side=tk.LEFT)

        self.arrow1 = tk.Label(self.content, text="", font=("Consolas", 8), fg=TEXT_DIM, bg=LOG_BG)
        self.arrow1.pack(side=tk.LEFT)

        self.lbl_curr = tk.Label(self.content, text="", font=("Consolas", 10, "bold"), fg=TEXT_BRIGHT, bg=LOG_BG)
        self.lbl_curr.pack(side=tk.LEFT)

        self.arrow2 = tk.Label(self.content, text="", font=("Consolas", 8), fg=TEXT_DIM, bg=LOG_BG)
        self.arrow2.pack(side=tk.LEFT)

        self.lbl_next = tk.Label(self.content, text="", font=("Consolas", 8), fg=TEXT_DIM, bg=LOG_BG)
        self.lbl_next.pack(side=tk.LEFT)

        self._solution = []
        self._cur_idx = -1

    def set_solution(self, solution):
        self._solution = solution
        self._cur_idx = -1
        self._update_display()

    def set_index(self, idx):
        self._cur_idx = idx
        self._update_display()

    def _update_display(self):
        sol = self._solution
        i   = self._cur_idx
        n   = len(sol)

        prev_move = sol[i - 1] if (i > 0) else None
        curr_move = sol[i]     if (0 <= i < n) else None
        next_move = sol[i + 1] if (i + 1 < n) else None

        # Render text
        t_prev = move_to_label(prev_move)
        t_curr = move_to_label(curr_move)
        t_next = move_to_label(next_move)

        self.lbl_prev.config(text=t_prev)
        self.lbl_curr.config(text=t_curr)
        self.lbl_next.config(text=t_next)

        self.arrow1.config(text=" < " if t_prev else "")
        self.arrow2.config(text=" > " if t_next else "")

        if curr_move is not None and n > 0:
            self.idx_var.set(f"B.{i + 1}/{n}")
        else:
            self.idx_var.set("")

    def clear(self):
        self._solution = []
        self._cur_idx  = -1
        self.lbl_prev.config(text="")
        self.lbl_curr.config(text="")
        self.lbl_next.config(text="")
        self.arrow1.config(text="")
        self.arrow2.config(text="")
        self.idx_var.set("")


# ────────
# Main GUI
# ────────
class FreeCellGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FreeCell  ♠ ♥ ♦ ♣")
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.current_seed = random.randint(1, 64000)
        self.is_instruction = False
        self.state     = create_initial_state(self.current_seed)
        self.card_images = {}
        self.guide_image = None
        self._load_images()

        self._solving   = False
        self._anim_job  = None
        self._solution  = []
        self._cancel_flag = False

        self._build_ui()
        self.render()

        self.drag_data = {"tag": None, "start_x": 0, "start_y": 0}

    # ─────────────
    # Image loading
    # ─────────────

    def _load_images(self):
        suits  = ["C", "D", "H", "S"]
        values = range(1, 14)

        crop_x = 13
        crop_y = 16

        for suit in suits:
            for val in values:
                path = f"asset/{suit}{val}.png"
                if os.path.exists(path):
                    img = Image.open(path)
                    w, h = img.size
                    img = img.crop((crop_x, crop_y, w - crop_x, h - crop_y))
                    img = img.resize((CARD_W, CARD_H), Image.NEAREST)
                    self.card_images[f"{suit}{val}"] = ImageTk.PhotoImage(img)

        path_ins = "asset/guide.png"
        if os.path.exists(path_ins):
            img = Image.open(path_ins).resize((WIN_W, WIN_H - BAR_H), Image.LANCZOS)
            self.guide_image = ImageTk.PhotoImage(img)
        
        path_bg = "asset/background.png"
        if os.path.exists(path_bg):
            img_bg = Image.open(path_bg).resize((WIN_W, WIN_H - BAR_H), Image.LANCZOS)
            self.bg_image = ImageTk.PhotoImage(img_bg)
        else:
            self.bg_image = None

    # ───────────────
    # Build UI layout
    # ───────────────
    def _build_ui(self):
        # ── Bottom button bar
        self.bar = tk.Frame(self.root, bg=BTN_BG, height=BAR_H,
                            highlightthickness=1, highlightbackground=BTN_BORDER)
        self.bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.bar.pack_propagate(False)

        # ── Main canvas
        canvas_h = WIN_H - BAR_H - 2
        self.canvas = tk.Canvas(self.root, width=WIN_W, height=canvas_h,
                                bg=FELT, highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.X)

        self._build_buttons()

        # Canvas bindings
        self.canvas.bind("<Button-1>",        self.on_press)
        self.canvas.bind("<B1-Motion>",       self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

    def _build_buttons(self):
        # Status label (left side)
        self.status_var = tk.StringVar(value="Sẵn sàng")
        tk.Label(self.bar, textvariable=self.status_var,
                 font=("Consolas", 9), fg=TEXT_DIM, bg=BTN_BG,
                 width=22, anchor="w").pack(side=tk.LEFT, padx=(12, 5))

        self.move_log = MoveLogStrip(self.bar)
        self.move_log.pack(side=tk.LEFT, padx=5, pady=10)

        self._cancel_btn = tk.Button(
            self.bar, text="✖ Cancel", command=self._cancel_solver,
            font=("Consolas", 9, "bold"),
            bg="#b71c1c", fg="#ffcdd2",
            activebackground="#d32f2f", activeforeground="white",
            relief="flat", bd=0, padx=12, pady=0, cursor="hand2", height=2,
        )

        # Right-side buttons
        btn_specs = [
            ("⟳ New Game", self.new_game, ACCENT2, "#1a1a00"),
            ("↺ Restart",   self.restart_game, "#ff8f00", "#1a1a00"),
            ("BFS",          self.solve_bfs,  BTN_BG,  BTN_TEXT),
            ("DFS",          self.solve_dfs,  BTN_BG,  BTN_TEXT),
            ("UCS",          self.solve_ucs,  BTN_BG,  BTN_TEXT),
            ("A★",           self.solve_astar, ACCENT,  BG),
        ]
        
        # Duyệt và vẽ các nút tĩnh
        for text, cmd, bg, fg in btn_specs:
            b = tk.Button(
                self.bar, text=text, command=cmd,
                font=("Consolas", 9, "bold"),
                bg=bg, fg=fg,
                activebackground=BTN_ACTIVE, activeforeground=TEXT_BRIGHT,
                relief="flat", bd=0, padx=12, pady=0,
                cursor="hand2", height=2,
            )
            # Sắp xếp các nút từ phải qua trái
            b.pack(side=tk.RIGHT, padx=3, pady=8)
            # Hover effect
            b.bind("<Enter>", lambda e, btn=b: btn.config(bg=BTN_ACTIVE))
            b.bind("<Leave>", lambda e, btn=b, c=bg: btn.config(bg=c))

    def _show_cancel_btn(self):
        self._cancel_btn.pack(side=tk.RIGHT, padx=3, pady=8)

    def _hide_cancel_btn(self):
        self._cancel_btn.pack_forget()

    def _cancel_solver(self):
        self._cancel_flag = True
        self._cancel_anim()
        self._hide_cancel_btn()
        self._solving = False
        self.status_var.set("Đã hủy")

    def _show_victory(self):
        cx = WIN_W // 2
        cy = (WIN_H - BAR_H) // 2

        stats_text = "Bạn đã xuất sắc giải xong màn chơi!"
        
        if getattr(self, '_solved_by_bot', False):
            try:
                csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solver_runs.csv")
                with open(csv_path, "r", encoding="utf-8") as f:
                    lines = list(csv.DictReader(f))
                    if lines:
                        last_run = lines[-1]
                        algo = last_run.get("algorithm", "A★")
                        time_sec = last_run.get("time_sec", "0")
                        nodes = last_run.get("expanded_nodes", "0")
                        mem = last_run.get("memory_peak_traced_mb", "0")
                        moves = last_run.get("solution_length", "0")
                        
                        stats_text = (f"Thuật toán: {algo} | Nước đi: {moves}\n"
                                      f"Thời gian: {time_sec}s | Nodes: {nodes}\n"
                                      f"Bộ nhớ tiêu thụ: {mem} MB")
            except Exception:
                stats_text = "Bot đã giải xong ván bài! (Không thể đọc file CSV)"

        self.canvas.create_rectangle(
            cx-320, cy-110, cx+320, cy+110,
            fill="#1a1200", outline=ACCENT2, width=4, tags="victory")
        
        self.canvas.create_text(cx+3, cy-45+3, text="🏆  VICTORY  🏆",
            font=("Georgia", 38, "bold"), fill="#5a4000", tags="victory")
        self.canvas.create_text(cx, cy-45, text="🏆  VICTORY  🏆",
            font=("Georgia", 38, "bold"), fill=ACCENT2, tags="victory")
        self.canvas.create_text(cx, cy+25, text=stats_text,
            font=("Consolas", 14), fill="#ffe082", justify=tk.CENTER, tags="victory")
        self.canvas.create_text(cx, cy+85, text="[ Click để tiếp tục ]",
            font=("Georgia", 10), fill=TEXT_DIM, tags="victory")
        self.canvas.tag_bind("victory", "<Button-1>", lambda e: self.canvas.delete("victory"))

    def _get_y_step(self, col_length):
        """Tính Y Max để cards không bị tràn viền dưới"""
        if col_length <= 1:
            return CASCADE_Y_STEP

        max_allowed_height = (WIN_H - BAR_H) - START_Y - CARD_H - 15
        dynamic_step = max_allowed_height // (col_length - 1)  
        return min(CASCADE_Y_STEP, dynamic_step)

    # ──────────
    # Rendering
    # ──────────
    def render(self):
        c = self.canvas
        c.delete("all")

        if hasattr(self, 'bg_image') and self.bg_image:
            c.create_image(0, 0, anchor=tk.NW, image=self.bg_image, tags="bg")

        # ── Grid background lines
        for i in range(8):
            x = START_X + i * COL_GAP + CARD_W // 2
            c.create_line(x, TOP_Y + CARD_H + 10, x, 620,
                        fill="#1e3a8a", width=1, dash=(4, 8))

        # ── FreeCells (left 4)
        for i in range(4):
            x, y = START_X + i * COL_GAP, TOP_Y
            c.create_rectangle(x, y, x + CARD_W, y + CARD_H,
                                outline=LOG_BORDER, fill="#1e3a8a", width=1)
            c.create_text(x + CARD_W // 2, y + CARD_H // 2,
                          text="FREE", fill=TEXT_MID,
                          font=("Times New Roman", 8))
            card = self.state["freecells"][i]
            if card:
                self._draw_card(x, y, card[0], card[1], "freecell", i)

        # ── Foundations (right 4)
        suits = ["C", "D", "H", "S"]
        suit_sym = {"H": "♥", "D": "♦", "C": "♣", "S": "♠"}
        for i, suit in enumerate(suits):
            x = START_X + (i + 4) * COL_GAP
            y = TOP_Y
            c.create_rectangle(x, y, x + CARD_W, y + CARD_H,
                                outline=BTN_BORDER, fill="#1e3a8a", width=1)
            c.create_text(x + CARD_W // 2, y + CARD_H // 2,
                          text=suit_sym[suit],
                          fill=SUIT_COLOR[suit],
                          font=("Arial", 22))
            val = self.state["foundations"][suit]
            if val > 0:
                self._draw_card(x, y, suit, val, "foundation", i)

        # ── Cascades
        for i, col in enumerate(self.state["cascades"]):
            x = START_X + i * COL_GAP
            step = self._get_y_step(len(col))
            for j, (suit, value) in enumerate(col):
                y = START_Y + j * step
                self._draw_card(x, y, suit, value, i, j)

    def _draw_card(self, x, y, suit, value, col, row):
        tag     = f"card_{col}_{row}"
        img_key = f"{suit}{value}"

        self.canvas.create_rectangle(
            x, y, x + CARD_W, y + CARD_H,
            fill="", outline="", tags=(tag, "rect"))

        if img_key in self.card_images:
            self.canvas.create_image(
                x, y, anchor=tk.NW,
                image=self.card_images[img_key],
                tags=(tag, "image"))
        else:
            # Fallback card draw
            color = "#ef5350" if suit in ("H", "D") else "#e0e0e0"
            vm    = {1: "A", 11: "J", 12: "Q", 13: "K"}
            txt   = f"{vm.get(value, str(value))} {suit}"
            self.canvas.create_rectangle(
                x, y, x + CARD_W, y + CARD_H,
                fill="#fafafa", outline="#aaa", tags=(tag, "fallback_rect"))
            self.canvas.create_text(
                x + CARD_W // 2, y + CARD_H // 2,
                text=txt, fill=color,
                font=("Consolas", 11, "bold"), tags=(tag, "text"))

    def show_guide_overlay(self):
        if self.guide_image:
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.guide_image, tags="guide_overlay")
            
            self.canvas.create_rectangle(WIN_W-90, 10, WIN_W-70, 30, fill="#b71c1c", outline="white", tags="guide_overlay")
            self.canvas.create_text(WIN_W-80, 20, text="X", fill="white", 
                                    font=("Consolas", 10, "bold"), tags="guide_overlay")

            self.canvas.tag_bind("guide_overlay", "<Button-1>", lambda e: self.hide_guide_overlay())
            
            self.root.bind("<Escape>", lambda e: self.hide_guide_overlay())
        else:
            self.status_var.set("⚠ Không tìm thấy file guide.png")

    def hide_guide_overlay(self):
        self.canvas.delete("guide_overlay")
        self.root.unbind("<Escape>")
        self.status_var.set("✦ Bạn đang trong chế độ chơi thử hướng dẫn")

    # ────────────────────────
    # Smooth solution playback
    # ────────────────────────
    def play_solution(self, solution, index=0, delay_ms=380):
        if index >= len(solution):
            self.status_var.set(f"✓ Giải xong! {len(solution)} nước")
            self._solving = False
            self._hide_cancel_btn()
            self._show_victory()
            return

        self.move_log.set_index(index)
        move = solution[index]

        prev_state = copy.deepcopy(self.state)
        self.state = apply_move(self.state, move)

        # Flash highlight on moved card
        self._flash_move(move, prev_state, callback=lambda: (
            self.render(),
            setattr(self, '_anim_job',
                self.root.after(delay_ms,
                    lambda: self.play_solution(solution, index + 1, delay_ms)))
        ))

    def _flash_move(self, move, state_before, callback):
        """
        Brief highlight effect: 
        Draw a glowing rectangle on the destination then call callback.
        """
        self.render()
        # Determine destination coords
        dest_x, dest_y = self._move_dest_coords(move, state_before)
        if dest_x is not None:
            flash_id = self.canvas.create_rectangle(
                dest_x - 3, dest_y - 3,
                dest_x + CARD_W + 3, dest_y + CARD_H + 3,
                outline=ACCENT2, fill="", width=3,
                tags=("flash",))
            # Fade out over 300ms via 6 steps
            self._fade_flash(flash_id, 6, callback)
        else:
            callback()

    def _fade_flash(self, item_id, steps, callback, step=0):
        if getattr(self, '_cancel_flag', False):
            try:
                self.canvas.delete(item_id)
            except tk.TclError:
                pass
            return

        if step >= steps:
            try:
                self.canvas.delete(item_id)
            except tk.TclError:
                pass
            callback()
            return

        alpha = 1 - step / steps
        r = int(0xff * alpha + 0x0d * (1 - alpha))
        g = int(0xca * alpha + 0x24 * (1 - alpha))
        b = int(0x28 * alpha + 0x18 * (1 - alpha))
        color = f"#{r:02x}{g:02x}{b:02x}"
        try:
            self.canvas.itemconfig(item_id, outline=color)
        except tk.TclError:
            pass
        
        self._anim_job = self.root.after(50, lambda: self._fade_flash(item_id, steps, callback, step + 1))

    def _move_dest_coords(self, move, state_before):
        """Return pixel (x, y) of destination card after move."""
        t = move[0]
        cascades = self.state["cascades"]
        try:
            if t == "cascade_to_foundation":
                src_col = move[1]
                card = state_before["cascades"][src_col][-1]
                suit = card[0]
                i = ["C", "D", "H", "S"].index(suit)
                return START_X + (i + 4) * COL_GAP, TOP_Y

            if t == "freecell_to_foundation":
                fc_idx = move[1]
                card = state_before["freecells"][fc_idx]
                suit = card[0]
                i = ["C", "D", "H", "S"].index(suit)
                return START_X + (i + 4) * COL_GAP, TOP_Y
            if t == "cascade_to_freecell":
                j = move[2]
                return START_X + j * COL_GAP, TOP_Y
                
            if t in ("freecell_to_cascade", "cascade_to_cascade"):
                j = move[2]
                col = cascades[j]
                
                col_length = len(col)
                step = self._get_y_step(col_length)
                
                y = START_Y + max(0, col_length - 1) * step
                return START_X + j * COL_GAP, y
                
        except Exception:
            pass
        return None, None

    # ────────
    # Helpers
    # ────────
    def _check_victory(self):
        """Kiểm tra chiến thắng sau mỗi nước đi thủ công."""
        if all(v == 13 for v in self.state["foundations"].values()):
            self._show_victory()

    def _trigger_auto_moves(self):
        """Sau mỗi nước đi thủ công, kick off chuỗi auto-move."""
        self._play_next_auto_move()

    def _play_next_auto_move(self):
        """
        Tính lại auto-moves từ state HIỆN TẠI mỗi bước.
        Tránh IndexError khi replay list move cũ bị stale
        (freecell/cascade index thay đổi sau mỗi lần apply).
        """
        int_state = _to_int_state(self.state)
        _, auto_moves = apply_safe_auto_moves(int_state)
        if not auto_moves:
            self.render()
            self._check_victory()
            return
        move = auto_moves[0]
        prev_state = copy.deepcopy(self.state)
        self.state = apply_move(self.state, move)
        self._flash_move(move, prev_state, callback=lambda: (
            self.render(),
            self.root.after(120, self._play_next_auto_move)
        ))

    def _get_col_from_x(self, x):
        for i in range(len(self.state["cascades"])):
            left  = START_X + i * COL_GAP - COL_GAP // 2
            right = START_X + i * COL_GAP + COL_GAP // 2
            if left <= x <= right:
                return i
        return -1

    def _get_freecell_from_xy(self, event):
        for i in range(4):
            fx = START_X + i * COL_GAP
            if fx <= event.x <= fx + CARD_W and TOP_Y <= event.y <= TOP_Y + CARD_H:
                return i
        return -1

    def _get_foundation_from_xy(self, event):
        suits = ["C", "D", "H", "S"]
        for i in range(4):
            fx = START_X + (i + 4) * COL_GAP
            if fx <= event.x <= fx + CARD_W and TOP_Y <= event.y <= TOP_Y + CARD_H:
                return suits[i]
        return None

    def _is_red(self, suit):
        return suit in ("H", "D")

    def _can_stack(self, card1, card2):
        s1, r1 = card1; s2, r2 = card2
        return (self._is_red(s1) != self._is_red(s2)) and (r1 == r2 + 1)

    def _is_valid_stack(self, stack):
        for i in range(len(stack) - 1):
            if not self._can_stack(stack[i], stack[i + 1]):
                return False
        return True

    def _is_valid_move(self, card, col_to):
        cols = self.state["cascades"]
        if not (0 <= col_to < len(cols)):
            return False
        if not cols[col_to]:
            return True
        top = cols[col_to][-1]
        return (self._is_red(card[0]) != self._is_red(top[0])) and (card[1] == top[1] - 1)

    def _can_supermove(self, stack_size, col_from, col_to):
        cascades  = self.state["cascades"]
        freecells = self.state["freecells"]
    
        N = sum(1 for f in freecells if f is None)
    
        M = sum(
            1 for i, c in enumerate(cascades)
            if not c and i != col_to
        )

        if len(cascades[col_from]) == stack_size:
            M += 1
    
        max_cards = (N + 1) * (2 ** M)
        return stack_size <= max_cards

    # ────────────
    # Mouse events
    # ────────────
    def on_press(self, event):
        item = self.canvas.find_closest(event.x, event.y)
        if not item:
            return
        tags = self.canvas.gettags(item[0])
        if not tags or not tags[0].startswith("card_"):
            return
        tag   = tags[0]
        parts = tag.split("_")
        col_str, row_str = parts[1], parts[2]
    
        if col_str == "freecell":
            i = int(row_str)
            if self.state["freecells"][i]:
                self.drag_data.update({
                    "tag": tag, "col": "freecell", "row": i,
                    "stack": [self.state["freecells"][i]],
                    "start_x": event.x, "start_y": event.y
                })
                self.canvas.tag_raise(tag)
            return
    
        if col_str == "foundation":
            return
    
        col     = int(col_str)
        cascade = self.state["cascades"][col]
        step = self._get_y_step(len(cascade))

        clicked_row = len(cascade) - 1
        for j in range(len(cascade) - 1):
            card_top    = START_Y + j * step
            card_bottom = START_Y + (j + 1) * step
            if card_top <= event.y < card_bottom:
                clicked_row = j
                break
    
        row   = len(cascade) - 1
        stack = cascade[row:]
        for start in range(clicked_row, len(cascade)):
            candidate = cascade[start:]
            if self._is_valid_stack(candidate):
                row   = start
                stack = candidate
                break
    
        N = sum(1 for f in self.state["freecells"] if f is None)
        M = sum(1 for i, c in enumerate(self.state["cascades"]) if not c and i != col)
        max_drag = (N + 1) * (2 ** M)
    
        if len(stack) > max_drag:
            row   = len(cascade) - max_drag
            stack = cascade[row:]
    
        self.drag_data.update({
            "tag": f"card_{col}_{row}",
            "col": col, "row": row, "stack": list(stack),
            "start_x": event.x, "start_y": event.y
        })
    
        for j in range(row, len(cascade)):
            self.canvas.tag_raise(f"card_{col}_{j}")
    

    def on_drag(self, event):
        tag = self.drag_data.get("tag")
        if not tag:
            return
    
        dx = event.x - self.drag_data["start_x"]
        dy = event.y - self.drag_data["start_y"]
    
        col = self.drag_data.get("col")
        row = self.drag_data.get("row")
    
        if isinstance(col, int):
            for j in range(row, len(self.state["cascades"][col])):
                self.canvas.move(f"card_{col}_{j}", dx, dy)
        else:
            self.canvas.move(tag, dx, dy)
    
        self.drag_data["start_x"] = event.x
        self.drag_data["start_y"] = event.y

    def on_release(self, event):
        tag = self.drag_data.get("tag")
        if not tag:
            return
    
        parts    = tag.split("_")
        col_str  = parts[1]
        row_str  = parts[2]
    
        if col_str == "freecell":
            i      = int(row_str)
            card   = self.state["freecells"][i]
            moved  = False
    
            if card:
                col_to = self._get_col_from_x(event.x)
                if col_to != -1 and self._is_valid_move(card, col_to):
                    self.state["freecells"][i] = None
                    self.state["cascades"][col_to].append(card)
                    moved = True
    
                if not moved:
                    fs = self._get_foundation_from_xy(event)
                    if fs and card[0] == fs and card[1] == self.state["foundations"][fs] + 1:
                        self.state["freecells"][i] = None
                        self.state["foundations"][fs] += 1
    
            self._trigger_auto_moves()
            self.drag_data["tag"] = None
            return
    
        col_from = int(col_str)
        row      = int(row_str)
        stack    = self.drag_data.get("stack", [])
    
        if not stack:
            self.render()
            self.drag_data["tag"] = None
            return
    
        fc_idx = self._get_freecell_from_xy(event)
        if fc_idx != -1:
            if len(stack) == 1 and self.state["freecells"][fc_idx] is None:
                self.state["cascades"][col_from].pop()
                self.state["freecells"][fc_idx] = stack[0]
            self._trigger_auto_moves()
            self.drag_data["tag"] = None
            return
    
        fs = self._get_foundation_from_xy(event)
        if fs:
            if len(stack) == 1:
                card = stack[0]
                if card[0] == fs and card[1] == self.state["foundations"][fs] + 1:
                    self.state["cascades"][col_from].pop()
                    self.state["foundations"][fs] += 1
            self._trigger_auto_moves()
            self.drag_data["tag"] = None
            return
    
        col_to = self._get_col_from_x(event.x)
        if 0 <= col_to < 8 and col_to != col_from:
            if self._is_valid_move(stack[0], col_to) and self._can_supermove(len(stack), col_from, col_to):
                for _ in range(len(stack)):
                    self.state["cascades"][col_from].pop()
                self.state["cascades"][col_to].extend(stack)
    
        self._trigger_auto_moves()
        self.drag_data["tag"] = None

    def on_double_click(self, event):
        item = self.canvas.find_closest(event.x, event.y)
        if not item:
            return
        tags = self.canvas.gettags(item[0])
        if not tags or not tags[0].startswith("card_"):
            return
        parts   = tags[0].split("_")
        col_str, row_str = parts[1], parts[2]

        if col_str == "foundation":
            return

        if col_str == "freecell":
            i = int(row_str)
            card = self.state["freecells"][i]
            if not card:
                return
            suit, val = card
            if val == self.state["foundations"][suit] + 1:
                self.state["freecells"][i] = None
                self.state["foundations"][suit] += 1
            self._trigger_auto_moves()
            return

        col, row = int(col_str), int(row_str)
        if row != len(self.state["cascades"][col]) - 1:
            return
        card     = self.state["cascades"][col][row]
        suit, val = card

        if val == self.state["foundations"][suit] + 1:
            self.state["cascades"][col].pop()
            self.state["foundations"][suit] += 1
            self._trigger_auto_moves()
            return

        for i in range(len(self.state["cascades"])):
            if self._is_valid_move(card, i):
                self.state["cascades"][col].pop()
                self.state["cascades"][i].append(card)
                self._trigger_auto_moves(); return

        for i in range(4):
            if self.state["freecells"][i] is None:
                self.state["cascades"][col].pop()
                self.state["freecells"][i] = card
                self._trigger_auto_moves(); return

    # ───────────────
    # Button commands
    # ───────────────
    def new_game(self):
        self._solved_by_bot = False
        dlg = SeedDialog(self.root)
        self.root.wait_window(dlg)

        self._cancel_anim()
        self.move_log.clear()

        if dlg.result is not None:
            self.current_seed = dlg.result
            self.status_var.set(f"Seed: {self.current_seed}")
        else:
            self.current_seed = random.randint(1, 64000)
            self.status_var.set(f"Ngẫu nhiên (Seed: {self.current_seed})")

        self.is_instruction = False
        self.state = create_initial_state(self.current_seed)
        self.render()

    def restart_game(self):
        self._solved_by_bot = False
        self._cancel_anim()
        self._hide_cancel_btn()
        self._cancel_flag = False
        self._solving = False
        self.move_log.clear()
        if getattr(self, "is_instruction", False):
            self.state = create_instruction_state()
            self.status_var.set("✦ Instruction mode")
            self.render()
            self.show_guide_overlay()
        else:
            self.state = create_initial_state(self.current_seed)
            self.status_var.set(f"↺ Seed: {self.current_seed}")
            self.render()

    def _cancel_anim(self):
        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None
        self._solving = False

    def instruction_game(self):
        self._cancel_anim()
        self._hide_cancel_btn()
        self._cancel_flag = False
        self._solving = False
        self.move_log.clear()

        self.is_instruction = True
        self.state = create_instruction_state()

        self.status_var.set("Instruction mode")
        self.render()
        self.show_guide_overlay()

    def _run_solver(self, name, fn):
        if self._solving:
            return
        self._cancel_anim()
        self.move_log.clear()
        self._solving = True
        self._cancel_flag = False
        self.status_var.set(f"⏳ {name} đang tính...")
        self._show_cancel_btn()

        def worker():
            result = fn(_to_int_state(self.state))
            
            def done():
                self._hide_cancel_btn()

                if self._cancel_flag:    
                    return

                if result and result.get("solution") is not None:
                    self._solved_by_bot = True
                    
                    sol = result["solution"]
                    t   = round(result.get("time", 0), 3)
                    exp = result.get("expanded_nodes", 0)
                    mem = result.get("memory_peak_traced_mb", "?")
                    
                    self.status_var.set(
                        f"{name}: {len(sol)} nước | {t}s | {exp} nodes | Mem: {mem}MB")
                    
                    self.move_log.set_solution(sol)
                    self.play_solution(sol, index=0)
                else:
                    self.status_var.set(f"{name}: Không tìm được lời giải hoặc đã hủy")
                    self._solving = False
            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def solve_bfs(self):
        self._run_solver("BFS", bfs_optimized)

    def solve_dfs(self):
        self._run_solver("DFS", dfs_optimized)

    def solve_ucs(self):
        self._run_solver("UCS", ucs_optimized)

    def solve_astar(self):
        self._run_solver("A★", astar_optimized)