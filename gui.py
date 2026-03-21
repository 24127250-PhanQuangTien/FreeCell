import tkinter as tk
from game import create_initial_state
from solver import bfs, dfs, ucs, astar
from optimized import bfs_optimized, dfs_optimized, ucs_optimized, astar_optimized
from test import create_easy_state
import threading

CARD_W = 50
CARD_H = 70
COL_GAP = 80
START_X = 20
START_Y = 120

class FreeCellGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FreeCell")

        self.state = create_initial_state()

        self.create_widgets()
        self.render()

        self.drag_data = {
            "tag": None,
            "start_x": 0,
            "start_y": 0
        }

    def create_widgets(self):
        # Frame chính
        self.frame = tk.Frame(self.root)
        self.frame.pack()

        # Freecells
        self.freecells_frame = tk.Frame(self.frame)
        self.freecells_frame.pack()

        self.freecell_labels = []
        for i in range(4):
            lbl = tk.Label(self.freecells_frame, text="Empty", width=10, borderwidth=2, relief="solid")
            lbl.pack(side=tk.LEFT, padx=5)
            self.freecell_labels.append(lbl)

        # Foundations
        self.foundation_frame = tk.Frame(self.frame)
        self.foundation_frame.pack()

        self.foundation_labels = {}
        for suit in ["H", "D", "C", "S"]:
            lbl = tk.Label(self.foundation_frame, text=f"{suit}:0", width=10, borderwidth=2, relief="solid")
            lbl.pack(side=tk.LEFT, padx=5)
            self.foundation_labels[suit] = lbl

        # Cascades
        self.canvas = tk.Canvas(self.frame, width=700, height=400, bg="darkgreen")
        self.canvas.pack()

        # Buttons
        self.button_frame = tk.Frame(self.root)
        self.button_frame.pack(pady=10)

        tk.Button(self.button_frame, text="New Game", command=self.new_game).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="BFS", command=self.solve_bfs).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="DFS", command=self.solve_dfs).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="UCS", command=self.solve_ucs).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="A*", command=self.solve_astar).pack(side=tk.LEFT, padx=5)

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def get_col_from_x(self, x):
        for i in range(len(self.state["cascades"])):
            left = START_X + i * COL_GAP - COL_GAP // 2
            right = START_X + i * COL_GAP + COL_GAP // 2

            if left <= x <= right:
                return i

        return -1

    def on_press(self, event):
        item = self.canvas.find_closest(event.x, event.y)

        if not item:
            return

        tags = self.canvas.gettags(item[0])
        if not tags:
            return

        tag = tags[0]

        col, row = map(int, tag.split("_")[1:])

        # chỉ cho lá trên cùng
        if row != len(self.state["cascades"][col]) - 1:
            return

        card = self.state["cascades"][col][row]

        # ===== AUTO MOVE TO FOUNDATION =====
        suit, value = card
        if value == self.state["foundations"][suit] + 1:
            self.state["cascades"][col].pop()
            self.state["foundations"][suit] += 1
            self.render()
            return

        # ===== AUTO MOVE TO EMPTY COLUMN =====
        for i in range(len(self.state["cascades"])):
            if not self.state["cascades"][i]:  # cột rỗng
                self.state["cascades"][col].pop()
                self.state["cascades"][i].append(card)
                self.render()
                return

        # ===== AUTO MOVE TO VALID CASCADE =====
        for i in range(len(self.state["cascades"])):
            if self.is_valid_move(card, i):
                self.state["cascades"][col].pop()
                self.state["cascades"][i].append(card)
                self.render()
                return

        # ===== nếu không auto được → cho drag =====
        self.drag_data["tag"] = tag
        self.drag_data["start_x"] = event.x
        self.drag_data["start_y"] = event.y

    def on_drag(self, event):
        tag = self.drag_data["tag"]
        if not tag:
            return

        dx = event.x - self.drag_data["start_x"]
        dy = event.y - self.drag_data["start_y"]

        self.canvas.move(tag, dx, dy)

        self.drag_data["start_x"] = event.x
        self.drag_data["start_y"] = event.y

    def on_release(self, event):
        tag = self.drag_data["tag"]
        if not tag:
            return

        col_from, row = map(int, tag.split("_")[1:])
        card = self.state["cascades"][col_from][row]

        # xác định cột đích
        items = self.canvas.find_withtag(tag)

        rect = None
        for item in items:
            if "rect" in self.canvas.gettags(item):
                rect = item
                break

        if rect is None:
            self.render()
            return
            
        x1, y1, x2, y2 = self.canvas.coords(rect)
        center_x = (x1 + x2) / 2

        col_to = self.get_col_from_x(center_x)

        if col_to < 0 or col_to >= len(self.state["cascades"]):
            self.render()
            self.drag_data["tag"] = None
            return

        valid = self.is_valid_move(card, col_to)

        if valid:
            # cập nhật state
            self.state["cascades"][col_from].pop()
            self.state["cascades"][col_to].append(card)
        else:
            print("Invalid move")

        # vẽ lại (tự reset vị trí)
        self.render()

        self.drag_data["tag"] = None

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

    def draw_card(self, x, y, suit, value, col, row):
        color = "red" if suit in ["H", "D"] else "black"

        value_map = {1:"A", 11:"J", 12:"Q", 13:"K"}
        v = value_map.get(value, str(value))

        text = f"{v}{suit}"

        tag = f"card_{col}_{row}"

        # rectangle
        self.canvas.create_rectangle(
            x, y, x + CARD_W, y + CARD_H,
            fill="white", outline="black",
            tags=(tag, "rect")
        )

        # text
        self.canvas.create_text(
            x + CARD_W//2,
            y + CARD_H//2,
            text=text,
            fill=color,
            font=("Arial", 12, "bold"),
            tags=(tag, "text")
        )

    def play_solution(self, solution, index = 0):
        if index >= len(solution):
            return
        move = solution[index]
            
        from game import apply_move
        self.state = apply_move(self.state, move)
        self.render()
        self.root.after(500, lambda: self.play_solution(solution, index + 1))

    def render(self):
        # ===== UPDATE FREECELLS =====
        for i, card in enumerate(self.state["freecells"]):
            text = f"{card[1]}{card[0]}" if card else "Empty"
            self.freecell_labels[i].config(text=text)

        # ===== UPDATE FOUNDATIONS =====
        for suit in ["H", "D", "C", "S"]:
            value = self.state["foundations"][suit]
            self.foundation_labels[suit].config(text=f"{suit}:{value}")

        # ===== CLEAR CANVAS =====
        self.canvas.delete("all")

        # ===== DRAW CASCADES =====
        for i, col in enumerate(self.state["cascades"]):
            x = START_X + i * COL_GAP

            for j, (suit, value) in enumerate(col):
                y = START_Y + j * 20
                self.draw_card(x, y, suit, value, i, j)

    def new_game(self):
        self.state = create_initial_state()
        self.render()

    def solve_bfs(self):
        def run():
            result = bfs(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))

        threading.Thread(target=run).start()

    def solve_dfs(self):
        def run():
            result = dfs(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))

        threading.Thread(target=run).start()

    def solve_ucs(self):
        def run():
            result = ucs(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))

        threading.Thread(target=run).start()

    def solve_astar(self):
        def run():
            result = astar(self.state)
            print(result)

            if result["solution"]:
                self.root.after(0, lambda: self.play_solution(result["solution"]))

        threading.Thread(target=run).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = FreeCellGUI(root)

    root.mainloop()