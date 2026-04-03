import tkinter as tk
from game import create_initial_state
from solver import bfs, dfs, ucs, astar
from optimized import bfs_optimized, dfs_optimized, ucs_optimized, astar_optimized
from test import create_easy_state
from copy import deepcopy
import threading
import os
from PIL import Image, ImageTk # Thư viện Pillow

CARD_W = 100
CARD_H = 130
COL_GAP = 130
START_X = 130
START_Y = 180

TOP_Y = 20

# ====================================
# Nhóm khởi tạo và thiết lập giao diện
# ====================================
class FreeCellGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FreeCell")
        self.root.geometry("1280x720")

        self.state = create_initial_state()
        self.initial_state = deepcopy(self.state)

        self.card_images = {}
        self.load_images()

        self.create_widgets()
        self.render()

        self.drag_data = {
            "tag": None,
            "start_x": 0,
            "start_y": 0
        }
    
    def load_images(self):
        suits = ["H", "D", "C", "S"]
        values = list(range(1, 14))

        for suit in suits:
            for val in values:
                img_path = f"asset/{suit}{val}.png"
                if os.path.exists(img_path):
                    img = Image.open(img_path)
                    img = img.resize((CARD_W, CARD_H), Image.LANCZOS)
                    self.card_images[f"{suit}{val}"] = ImageTk.PhotoImage(img)
                else:
                    print(f"Không tìm thấy {img_path}\n")

    def create_widgets(self):
        # Frame chính
        self.frame = tk.Frame(self.root)
        self.frame.pack()

        # Bàn chơi (Cascades)
        self.canvas = tk.Canvas(self.frame, width=1280, height=600, bg="#003300", highlightthickness=0)
        self.canvas.pack()

        # Phần Info + Buttons
        self.bottom_frame = tk.Frame(self.root, bg="#1E1E1E", height=150)
        self.bottom_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Khu vực hiển thị Info
        self.info_frame = tk.Frame(self.bottom_frame, bg="#000000", bd=2, relief=tk.SUNKEN)
        self.info_frame.pack(side=tk.LEFT, padx= 30, pady=15, fill=tk.X)

        self.info_label = tk.Label(
            self.bottom_frame, 
            text="Ready.", 
            fg="#00FF00", 
            bg="#000000", 
            font=("Consolas", 14, "bold"), 
            justify=tk.LEFT,
            anchor="w",
            width=50, padx=15, pady=5
        )
        self.info_label.pack(side=tk.LEFT, padx=20)

        # 2. Khu vực các nút bấm
        self.button_frame = tk.Frame(self.bottom_frame, bg="#1E1E1E")
        self.button_frame.pack(side=tk.RIGHT, padx=30, pady=15)

        # Cấu hình chung cho nút
        btn_font = ("Helvetica", 11, "bold")
        btn_common = {
            "font": btn_font, 
            "fg": "#00DD00", 
            "activeforeground": "white",
            "relief": tk.FLAT,
            "cursor": "hand2",
            "width": 8,
            "pady": 6
        }

        # Các nút chức năng
        tk.Button(self.button_frame, text="New Game", command=self.new_game, bg="#003300", activebackground="#002200", **btn_common).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="Restart", command=self.restart_game, bg="#003300", activebackground="#002200",**btn_common).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="BFS", command=self.solve_bfs, bg="#003300", activebackground="#002200",**btn_common).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="DFS", command=self.solve_dfs, bg="#003300", activebackground="#002200",**btn_common).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="UCS", command=self.solve_ucs, bg="#003300", activebackground="#002200",**btn_common).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="A*", command=self.solve_astar, bg="#003300", activebackground="#002200",**btn_common).pack(side=tk.LEFT, padx=5)

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

# ========================
# Nhóm hàm trợ giúp, logic
# ========================

    def get_col_from_x(self, x):
        for i in range(len(self.state["cascades"])):
            left = START_X + i * COL_GAP - COL_GAP // 2
            right = START_X + i * COL_GAP + COL_GAP // 2

            if left <= x <= right:
                return i

        return -1
    
    def get_freecell_from_xy(self, event):
        x = event.x
        y = event.y

        for i in range(4):
            fx = START_X + i * COL_GAP
            fy = TOP_Y
            if fx <= x <= fx + CARD_W and fy <= y <= fy + CARD_H:
                return i
        return -1 
    
    def get_foundation_from_xy(self, event):
        x, y = event.x, event.y
        suits = ["H", "D", "C", "S"]
        for i in range(4):
            fx = START_X + (i + 4) * COL_GAP
            fy = TOP_Y
            if fx <= x <= fx + CARD_W and fy <= y <= fy + CARD_H:
                return suits[i]
        return None
    
    def get_max_movable_cards(self, col_from, col_to):
        freecells = sum(1 for c in self.state["freecells"] if c is None)

        empty_cols = 0
        for i, col in enumerate(self.state["cascades"]):
            if i != col_from and i != col_to and len(col) == 0:
                empty_cols += 1

        return (freecells + 1) * (2 ** empty_cols)
    
    def is_valid_stack(self, stack):
        red = ["H", "D"]

        for i in range(len(stack) - 1):
            curr = stack[i]
            next_card = stack[i + 1]

            # khác màu
            if (curr[0] in red) == (next_card[0] in red):
                return False

            # giảm 1
            if curr[1] != next_card[1] + 1:
                return False

        return True

    def is_valid_move(self, card, col_to):
        cascades = self.state["cascades"]

        # ngoài bảng
        if col_to < 0 or col_to >= len(cascades):
            return False

        # nếu cột rỗng → ok
        if not cascades[col_to]:
            return True

        top = cascades[col_to][-1]

        # khác màu
        red = ["H", "D"]
        if (card[0] in red) == (top[0] in red):
            return False

        # giảm 1
        return card[1] == top[1] - 1
    
    def get_card_str(self, card):
        """Đổi lá bài thành chất (VD: (H, 13) -> K♥)"""
        if not card: return "Empty"
        suit_symbols = {"H": "♥", "D": "♦", "C": "♣", "S": "♠"}
        value_map = {1: "A", 11: "J", 12: "Q", 13: "K"}
        v = value_map.get(card[1], str(card[1]))
        return f"{v}{suit_symbols[card[0]]}"

    def get_move_info(self, state, move):
        """Tạo mô tả cho hành động"""
        move_type = move[0]
        if move_type == "cascade_to_foundation": # Bàn chơi -> foundation
            i = move[1]
            card = state["cascades"][i][-1]
            return f"Move {self.get_card_str(card)} from Column {i + 1} up to Foundation"
        elif move_type == "freecell_to_foundation":
            i = move[1]
            card = state["freecells"][i]
            return f"Move {self.get_card_str(card)} from FreeCell {i + 1} to Foundation"
        elif move_type == "cascade_to_freecell":
            i, j = move[1], move[2]
            card = state["cascades"][i][-1]
            return f"Move {self.get_card_str(card)} from Column {i + 1} up to FreeCell {j + 1}"
        elif move_type == "freecell_to_cascade":
            i, j = move[1], move[2]
            card = state["freecells"][i]
            return f"Move {self.get_card_str(card)} from FreeCell {i + 1} down to Column {j + 1}"
        elif move_type == "cascade_to_cascade":
            i, j = move[1], move[2]
            card = state["cascades"][i][-1]
            return f"Move {self.get_card_str(card)} from Column {i + 1} to Column {j + 1}"
        return str(move)

# ====================================
# Nhóm xử lý tương tác chuột
# ====================================

    def on_press(self, event):
        # Tìm object gần nhất trên Canvas tại vị trí click
        item = self.canvas.find_closest(event.x, event.y)
        if not item:
            return
        tags = self.canvas.gettags(item[0])
        if not tags:
            return
        
        tag = tags[0]
        # Bỏ qua nếu click vào vùng trống
        if not tag.startswith("card_"): 
            return

        parts = tag.split("_")
        col_str, row_str = parts[1], parts[2]

        # Nếu click vào FreeCell
        if col_str == "freecell":
            i = int(row_str)
            card = self.state["freecells"][i]
            if card:
                self.drag_data["tag"] = tag
                self.drag_data["start_x"] = event.x
                self.drag_data["start_y"] = event.y
            return
        
        # Nếu click vào foundation thì sẽ bỏ qua
        if col_str == "foundation":
            return
        
        # Nếu click vào bàn chơi
        col, row = int(col_str), int(row_str)
        column = self.state["cascades"][col]
        stack = column[row:]

        # Kiểm tra xem có bốc được cả một cụm bài hợp lệ hay không
        if not self.is_valid_stack(stack): 
            return
        
        # Lưu lại dữ liệu cho việc drag
        self.drag_data.update({
            "tag": tag, 
            "col": col, 
            "row": row, 
            "stack": stack, 
            "start_x": event.x, 
            "start_y": event.y
        })

    def on_double_click(self, event):
        item = self.canvas.find_closest(event.x, event.y)
        if not item: return
        tags = self.canvas.gettags(item[0])
        if not tags or not tags[0].startswith("card"): return

        tag = tags[0]
        parts = tag.split("_")
        
        # Không cho nhận double click ở ô freecell hoặc foundation 
        if parts[1] == "foundations":
            return
        
        if parts[1] == "freecell":
            i = int(parts[2])
            card = self.state["freecells"][i]
            if not card:
                return

            suit, value = card

            # move lên foundation nếu hợp lệ
            if value == self.state["foundations"][suit] + 1:
                self.state["freecells"][i] = None
                self.state["foundations"][suit] += 1
                self.render()
            return
        
        col, row = int(parts[1]), int(parts[2])

        # chỉ cho lá trên cùng
        if row != len(self.state["cascades"][col]) - 1:
            return

        card = self.state["cascades"][col][row]
        suit, value = card

        # ===== FOUNDATION =====
        if value == self.state["foundations"][suit] + 1:
            self.state["cascades"][col].pop()
            self.state["foundations"][suit] += 1
            self.render()
            return

        # ===== CASCADE =====
        for i in range(len(self.state["cascades"])):
            if self.is_valid_move(card, i):
                self.state["cascades"][col].pop()
                self.state["cascades"][i].append(card)
                self.render()
                return

        # ===== FREECELL =====
        for i in range(4):
            if self.state["freecells"][i] is None:
                self.state["cascades"][col].pop()
                self.state["freecells"][i] = card
                self.render()
                return

    def on_drag(self, event):
        tag = self.drag_data["tag"]
        if not tag:
            return

        dx = event.x - self.drag_data["start_x"]
        dy = event.y - self.drag_data["start_y"]

        col = self.drag_data.get("col")
        row = self.drag_data.get("row")

        if col is not None and isinstance(col, int):
            # Kéo nguyên 1 cụm bài từ bàn chơi
            for j in range(row, len(self.state["cascades"][col])):
                self.canvas.move(f"card_{col}_{j}", dx, dy)
        else:
            # Kéo 1 lá bài lẻ
            self.canvas.move(tag, dx, dy)

        self.drag_data["start_x"] = event.x
        self.drag_data["start_y"] = event.y

    def on_release(self, event):
        tag = self.drag_data["tag"]
        if not tag:
            return

        parts = tag.split("_")
        col_str, row_str = parts[1], parts[2]

        # ===== CASE 1: kéo từ freecell =====
        if col_str == "freecell":
            i = int(row_str)
            col_to = self.get_col_from_x(event.x)
            if col_to != -1:
                card = self.state["freecells"][i]
                if card and self.is_valid_move(card, col_to):
                    self.state["freecells"][i] = None
                    self.state["cascades"][col_to].append(card)
            self.render()
            self.drag_data["tag"] = None
            return

        # ===== CASE 2: kéo từ cascade =====
        col_from, row = int(col_str), int(row_str)
        stack = self.drag_data.get("stack")

        # CHECK THẢ VÀO FREECELL
        freecell_index = self.get_freecell_from_xy(event)
        if freecell_index != -1:
            if len(stack) == 1 and self.state["freecells"][freecell_index] is None:
                self.state["cascades"][col_from].pop()
                self.state["freecells"][freecell_index] = stack[0]
            self.render()
            self.drag_data["tag"] = None
            return
        
        foundation_suit = self.get_foundation_from_xy(event)
        if foundation_suit:
            card = self.state["freecells"][i]
            suit, val = card
            if suit == foundation_suit and val == self.state["foundations"][suit] + 1:
                self.state["freecells"][i] = None
                self.state["foundations"][suit] += 1
            self.render()
            self.drag_data["tag"] = None
            return

        # CHECK THẢ VÀO FOUNDATION
        foundation_suit = self.get_foundation_from_xy(event)
        if foundation_suit:
            if len(stack) == 1:
                card = stack[0]
                suit, val = card
                # Hợp lệ nếu cùng chất và giá trị lớn hơn 1
                if suit == foundation_suit and val == self.state["foundations"][suit] + 1:
                    self.state["cascades"][col_from].pop()
                    self.state["foundations"][suit] += 1
            self.render()
            self.drag_data["tag"] = None
            return

        # ===== CASCADE DROP =====
        items = self.canvas.find_withtag(tag)

        rect = None
        for item in items:
            if "rect" in self.canvas.gettags(item):
                rect = item
                break

        if rect is None:
            self.render()
            self.drag_data["tag"] = None
            return

        x1, y1, x2, y2 = self.canvas.coords(rect)
        center_x = (x1 + x2) / 2

        col_to = self.get_col_from_x(center_x)

        if col_to < 0 or col_to >= len(self.state["cascades"]):
            self.render()
            self.drag_data["tag"] = None
            return

        if stack:
            max_move = self.get_max_movable_cards(col_from, col_to)

            if len(stack) > max_move:
                print("Exceeds move limit")
                self.render()
                self.drag_data["tag"] = None
                return

            if self.is_valid_move(stack[0], col_to):
                for _ in range(len(stack)):
                    self.state["cascades"][col_from].pop()

                self.state["cascades"][col_to].extend(stack)
            else:
                print("Invalid move")

        self.render()
        self.drag_data["tag"] = None

# ===========================
# Nhóm Rendering và Animation
# ===========================

    def draw_card(self, x, y, suit, value, col, row):
        tag = f"card_{col}_{row}"
        img_key = f"{suit}{value}"

        # Vẽ khung trống làm hitbox cho kéo thả
        self.canvas.create_rectangle(
            x, y, x + CARD_W, y + CARD_H,
            fill="", outline="", # Rỗng để ẩn hitbox
            tags=(tag, "rect")
        )

        # Hiển thị ảnh Asset nếu tìm thấy trong cache
        if img_key in self.card_images:
            self.canvas.create_image(
                x, y, 
                anchor=tk.NW, # Đặt mỏ neo ở góc cùng bên trái
                image=self.card_images[img_key],
                tags=(tag, "image") 
            )
        else:
            # Fallback: Nếu thiếu ảnh, tự động vẽ lá bài tĩnh
            color = "red" if suit in ["H", "D"] else "black"
            value_map = {1:"A", 11:"J", 12:"Q", 13:"K"}
            v = value_map.get(value, str(value))

            suit_symbols = {"H": "♥", "D": "♦", "C": "♣", "S": "♠"}
            text = f"{v}{suit_symbols[suit]}"

            self.canvas.create_rectangle(
                x, y, x + CARD_W, y + CARD_H,
                fill="white", outline="black",
                tags=(tag, "fallback_rect")
            )
            self.canvas.create_text(
                x + CARD_W//2, y + CARD_H//2 - 30,
                text=text, fill=color, font=("Times New Roman", 12, "bold"),
                tags=(tag, "text")
            )

    def play_solution(self, solution, index = 0):
        if index >= len(solution):
            self.info_label.config(text= "Goal State achieved!")
            return
        
        move = solution[index]
        step_left = len(solution) - index
        info = self.get_move_info(self.state, move)

        self.info_label.config(text=f"Remain: {step_left} steps\nInfo: {info}")
            
        from game import apply_move
        self.state = apply_move(self.state, move)
        self.render()

        self.root.after(500, lambda: self.play_solution(solution, index + 1))

    def render(self):
        # Dọn sạch bản vẽ
        self.canvas.delete("all")

        # Vẽ 4 ô FreeCell (bên trái)
        for i in range(4):
            x = START_X + i * COL_GAP
            y = TOP_Y
            # Vẽ viền cho ô
            self.canvas.create_rectangle(x, y, x + CARD_W, y + CARD_H, outline="lightgreen", width=2)

            # Nếu có bài thì vẽ vào
            card = self.state["freecells"][i]
            if card:
                # Dùng "freecell" làm tên cột để phân biệt
                self.draw_card(x, y, card[0], card[1], "freecell", i)

        # Vẽ 4 ô Foundations (bên phải)
        suits = ["H", "D", "C", "S"]
        suit_symbols = {"H": "♥", "D": "♦", "C": "♣", "S": "♠"}
        for i, suit in enumerate(suits):
            x = START_X + (i + 4) * COL_GAP
            y = TOP_Y
            # Vẽ viền ô trống kèm chữ chìm
            self.canvas.create_rectangle(x, y, x + CARD_W, y + CARD_H, outline="lightgreen", width=2)
            self.canvas.create_text(x + CARD_W//2, y + CARD_H//2, text=suit_symbols[suit], fill="lightgreen", font=("Times New Roman", 36))

            # Nếu có bài thêm vào thì sẽ nằm ở trên cùng
            val = self.state["foundations"][suit]
            if val > 0:
                self.draw_card(x, y, suit, val, "foundation", i)

        # Vẽ bàn chơi CASCADES =====
        for i, col in enumerate(self.state["cascades"]):
            x = START_X + i * COL_GAP
            for j, (suit, value) in enumerate(col):
                y = START_Y + j * 35
                self.draw_card(x, y, suit, value, i, j)

# ================
# Nhóm tích hợp AI
# ================

    def new_game(self):
        self.state = create_initial_state()
        self.initial_state = deepcopy(self.state)
        self.info_label.config(text="Ready!")
        self.render()
    
    def restart_game(self):
        self.state = deepcopy(self.initial_state)
        self.info_label.config(text="Again!")
        self.render()

    def solve_bfs(self):
        self.info_label.config(text="Running BFS solution...")
        def run():
            result = bfs(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))
            else:
                self.root.after(0, lambda: self.info_label.config(text="No solution found."))

        threading.Thread(target=run).start()

    def solve_dfs(self):
        self.info_label.config(text="Running DFS solution...")
        def run():
            result = dfs(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))
            else:
                self.root.after(0, lambda: self.info_label.config(text="No solution found."))

        threading.Thread(target=run).start()

    def solve_ucs(self):
        self.info_label.config(text="Running UCS solution...")
        def run():
            result = ucs(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))
            else:
                self.root.after(0, lambda: self.info_label.config(text="No solution found."))

        threading.Thread(target=run).start()

    def solve_astar(self):
        self.info_label.config(text="Running A* solution...")
        def run():
            result = astar(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))
            else:
                self.root.after(0, lambda: self.info_label.config(text="No solution found."))

        threading.Thread(target=run).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = FreeCellGUI(root)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nĐã tắt game thủ công!")