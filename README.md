# 🃏 FreeCell Solver

> **Course:** CSC14003 – Introduction to Artificial Intelligence  
> **University:** University of Science, VNU-HCM (HCMUS)

---

## 📖 Table of Contents

- [Overview](#overview)
- [FreeCell Rules](#freecell-rules)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [How to Run](#how-to-run)
- [State Representation](#state-representation)
- [Search Algorithms](#search-algorithms)
- [Heuristic Function](#heuristic-function)
- [Pruning Strategies](#pruning-strategies)
- [GUI Features](#gui-features)
- [Performance & Statistics](#performance--statistics)
- [Authors](#authors)

---

## 📌 Overview

This project solves the classic **FreeCell solitaire card game** using AI search algorithms. Given a shuffled deck, the solver finds a sequence of moves to transfer all 52 cards from the cascades to the 4 foundation piles.

FreeCell is a compelling AI benchmark because:
- It is a **perfect-information** problem — the full board is always visible
- It is **PSPACE-complete** in the general case
- Nearly every deal (>99.999%) is solvable, yet requires strategic planning

---

## 🎮 FreeCell Rules
```
┌──────────────────────────────────────────────────────────────┐
│         FREE CELLS (4)          │      FOUNDATIONS (4)       │
│        [ ] [ ] [ ] [ ]          │      [♣] [♦] [♥] [♠]       │
├──────────────────────────────────────────────────────────────┤
│                   CASCADES (8 columns)                       │
│           [1]  [2]  [3]  [4]  [5]  [6]  [7]  [8]             │
└──────────────────────────────────────────────────────────────┘
```

| Zone | Count | Rule |
|---|---|---|
| **Free Cells** | 4 slots | Hold 1 card each (any card) |
| **Foundations** | 4 piles | Built up A→K, same suit |
| **Cascades** | 8 columns | Stack in descending rank, alternating color |

**Supermove rule:** Multiple cards in a valid sequence can be moved at once, limited by `(free_cells + 1) × 2^(empty_columns)`.

**Goal:** Move all 52 cards to the foundations.

---

## 📁 Project Structure
```
freecell/
├── main.py            # Entry point — launches the GUI
├── gui.py             # Tkinter GUI, drag-and-drop, animation, solver bridge
├── game.py            # Core game logic: get_moves, apply_move, is_goal
├── optimized.py       # Search algorithms: BFS, DFS, UCS, A*
├── utilities.py       # State encoding, pruning, auto-move logic
├── requirements.txt   # Python dependencies
├── asset/             # Card images (PNG) and background
│   ├── H1.png … S13.png
│   ├── background.png
│   └── guide.png
└── solver_runs.csv    # Auto-generated performance log 
```

---

## 🔧 Installation

**Requirements:** Python 3.8+
```bash
# Clone the repository
git clone https://github.com/24127250-PhanQuangTien/FreeCell.git
cd freecell

# Install dependencies
pip install -r requirements.txt
# or
# python3 -m pip install -r requirements.txt
```

`requirements.txt` content:
```
Pillow
```

---

## ▶️ How to Run
```bash
python main.py
# or
# python3 main.py
```

The GUI will open. You can:
- **Play manually** with drag-and-drop
- **Enter a seed** to replay a specific deal
- **Click a solver button** (BFS / DFS / UCS / A★) to watch the AI solve it

---

## ⚙️ State Representation

### Bitmask Encoding (`utilities.py`)

Each game state is encoded into a **single integer** for O(1) hashing and comparison:
```
Bit layout (offset → field):
  [0  – 15]   Foundations  — 4 suits × 4 bits (top rank, 0–13)
  [16 – 39]   Free Cells   — 4 slots × 6 bits (card id, sorted)
  [40 – 63]   Column Lens  — 8 columns × 3 bits (length 0–7)
  [64 – ...]  Card Data    — 8 cols × 13 cards × 6 bits
```

Each card is encoded as:
```python
card_id = suit_index × 13 + (rank − 1)   # range [0, 51]
# Suits: H=0, D=1, C=2, S=3
```

### Canonicalization

To avoid counting the same state multiple times:
- **Free cells** are sorted before encoding
- **Empty cascade columns** are pushed to the end

This ensures equivalent board configurations always hash to the same key.

---

## 🧠 Search Algorithms (`optimized.py`)

All algorithms share the same `_expand()` function and pruning pipeline.

### BFS — Breadth-First Search
- **Complete:** ✅ Always finds a solution if one exists but local machine can not find find solution because OOM
- **Optimal:** ✅ Minimizes number of moves
- **Complexity:** O(b^d) time and memory
- **Notes:** High memory usage; best for shallow solutions

### DFS — Depth-First Search
- **Complete:** ✅ (with depth limit) but local machine can not find find solution because OOM
- **Optimal:** ❌
- **Complexity:** O(max_depth) memory
- **Notes:** Fast exploration; may find long solutions

### UCS — Uniform Cost Search
- **Complete:** ✅ but local machine can not find find solution because OOM
- **Optimal:** ✅ Minimizes total move cost
- **Notes:** Uses a priority queue ordered by `g(n)` (cumulative cost)

### A\* — A-Star Search
- **Complete:** ✅
- **Optimal:** ❌
- **Implementation:** **Anytime Weighted A\*** — tries weights `[2.0, 3.0, 5.0]` in sequence, returns the first solution found
- **Notes:** Most practical; balances speed and solution quality

#### Move Costs

| Move type | Cost |
|---|---|
| To foundation | 0.5 (rewarded) |
| Creates empty column | 0.8 |
| Other cascade move | 1.0 |

---

## 📐 Heuristic Function (`optimized.py → heuristic()`)

Used by UCS (as tiebreaker) and A★ (as primary guide):

```
h(n) = 1.0 × remaining_cards
     + 1.1 × burial_depth_score
     + 0.6 × occupied_free_cells
     + 0.8 × bad_sequences
     + mobility_penalty
```

| Term | Description |
|---|---|
| `remaining_cards` | Cards not yet on foundation |
| `burial_depth_score` | Weighted depth of next needed cards buried in cascades |
| `occupied_free_cells` | Number of non-empty free cells |
| `bad_sequences` | Adjacent pairs in cascades that violate alternating-color / descending-rank |
| `mobility_penalty` | 8.0 if no free cells/empty cols, 4.0 if only 1, else 0 |

---

## ✂️ Pruning Strategies (`utilities.py`)

### 1. Safe Auto-Moves
Cards are automatically sent to the foundation (without expanding the search tree) when it is **provably safe**:

> A card is safe to auto-move if all cards of the **opposite color** with `rank − 1` are already on the foundation.

This is applied after every move, collapsing entire chains of forced moves into a single step.
At first, we applied it to the algorithms, but because it caused BFS to lose its essence and took quite a lot of time, we abandoned it.

### 2. Dominated Move Filter
All **8 rules** are applied in order before generating successors. The function operates on 5 move types: `cascade_to_foundation`, `freecell_to_foundation`, `cascade_to_freecell`, `freecell_to_cascade`, `cascade_to_cascade`.
 
---
 
**R1 — Safe foundation priority**
 
If any move sends a card to the foundation AND that card satisfies the safety condition → return **only** those moves, discard everything else immediately.
 
```python
if safe_fnd:
    return safe_fnd
```
 
---
 
**R2 — No wasteful cascade → freecell**
 
Skip `cascade→freecell` for a card if it already has a valid move to a **non-empty cascade** (`cards_with_real_cascade`). Using a free cell slot when a real cascade target exists is strictly dominated.
 
---
 
**R3 — Deduplicate cascade → freecell by source column**
 
All free cell slots are interchangeable. Only keep **one** `cascade→freecell` move per source column, always targeting `first_empty_fc`. Multiple moves from the same source column are redundant.
 
---
 
**R4 — Deduplicate freecell → cascade (non-empty destination)**
 
For moves from a free cell to a **non-empty** cascade column, deduplicate by `(card_id, destination_col)`. If two free cell slots hold identical cards, moving either one to the same column produces the same resulting state.
 
---
 
**R5 — Only highest-rank freecell card may move to empty column**
 
For `freecell→cascade` targeting an **empty** column, only allow the freecell card with the **highest rank**. Moving a lower-rank card to an empty column while a higher-rank card sits idle in another free cell is wasteful — the higher-rank card has more stacking potential.
 
---
 
**R6 — At most one freecell → empty-column move total**
 
Even after R5 selects the best card, only **one** such move is allowed across the entire move list (`seen_f2e` flag). All empty columns are equivalent — there is no reason to generate separate moves for `first_empty_col`, `second_empty_col`, etc.
 
---
 
**R7 — No wasteful cascade → empty column**
 
Skip `cascade→cascade` targeting an **empty** column if the card already has a valid move to a **non-empty cascade**. Occupying an empty column is only worthwhile when there is no real cascade target available.
 
---
 
**R8 — Deduplicate cascade → empty-column by source column**
 
All empty columns are equivalent. Only keep **one** `cascade→cascade` move to an empty column per source column, always targeting `first_empty_col`. Multiple empty-column targets for the same source card produce identical game states.
 
---
 
> **Fallback:** If all rules eliminate every move (edge case in degenerate states), the original unfiltered move list is returned unchanged.
 

---

## 🖥️ GUI Features (`gui.py`)

| Feature | Description |
|---|---|
| 🖱️ Drag & Drop | Drag single cards or valid sequences between columns |
| 🖱️ Double-click | Auto-move card to best destination |
| 🌱 Seed input | Enter a number to reproduce any specific deal |
| ⚡ Auto-moves | Safe foundation moves play automatically after each action |
| 🎬 Solver animation | Watch the AI solve step-by-step with flash highlights |
| 📊 Move log strip | Shows previous / current / next move during playback |
| 🏆 Victory screen | Displays algorithm stats on completion |
| ✖ Cancel button | Stop the solver mid-animation |

---

## 📊 Performance & Statistics

Every solver run is logged automatically to `solver_runs.csv`:

| Column | Description |
|---|---|
| `algorithm` | BFS / DFS / UCS / A* |
| `time_sec` | Wall-clock time |
| `memory_peak_traced_mb` | Peak memory (tracemalloc) |
| `expanded_nodes` | Total nodes expanded |
| `solution_length` | Number of moves in solution |
| `solved` | True / False |

---

## 👨‍💻 Authors

| Name | Student ID |
|---|---|
| Phan Quang Tiến | 24127250 |
| Nguyễn Chí Tài | 24127529 |
| Nguyễn Ngọc Thiên | 24127545 |

---

## 📄 License

Submitted as coursework for **CSC14003 – Introduction to Artificial Intelligence, HCMUS**.  
This project is open source
