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

    def draw_card(self, x, y, suit, value):
        color = "red" if suit in ["H", "D"] else "black"

        value_map = {1:"A", 11:"J", 12:"Q", 13:"K"}
        v = value_map.get(value, str(value))

        text = f"{v}{suit}"

        # rectangle
        self.canvas.create_rectangle(
            x, y, x + CARD_W, y + CARD_H,
            fill="white", outline="black"
        )

        # text
        self.canvas.create_text(
            x + CARD_W//2,
            y + CARD_H//2,
            text=text,
            fill=color,
            font=("Arial", 12, "bold")
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
        # Freecells
        for i, card in enumerate(self.state["freecells"]):
            text = str(card) if card else "Empty"
            self.freecell_labels[i].config(text=text)

        # Foundations
        for suit in ["H", "D", "C", "S"]:
            value = self.state["foundations"][suit]
            self.foundation_labels[suit].config(text=f"{suit}:{value}")

        # Cascades
        self.canvas.delete("all")

        # draw cascades
        for i, col in enumerate(self.state["cascades"]):
            x = START_X + i * COL_GAP

            for j, (suit, value) in enumerate(col):
                y = START_Y + j * 20
                self.draw_card(x, y, suit, value)

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