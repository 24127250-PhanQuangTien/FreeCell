import heapq
import time
import csv
from collections import deque
import os
import tracemalloc

from game import get_moves, apply_move, is_goal, is_red
from utilities import encode_state, apply_safe_auto_moves, filter_dominated_moves, _is_safe_to_auto_move


# ──────────────────────────────────────────────────────────
# Heuristic
# ──────────────────────────────────────────────────────────

RED   = frozenset({"H", "D"})
BLACK = frozenset({"C", "S"})

# def heuristic(state):
#     foundations = state["foundations"]
#     total = 0

#     depth_map = {}
#     for col in state["cascades"]:
#         n = len(col)
#         for i, card in enumerate(col):
#             depth_map[card] = n - 1 - i

#     for suit in ("H", "D", "C", "S"):
#         for rank in range(foundations[suit] + 1, 14):
#             card = (suit, rank)
#             depth = depth_map.get(card, 0)
#             if _is_safe_to_auto_move(card, foundations):
#                 base_cost = 0.1
#             else:
#                 base_cost = 1.5
#             total += base_cost + depth * 1

#     return total

def heuristic(state) -> float:
    foundations = state["foundations"]
    cascades    = state["cascades"]
    freecells   = state["freecells"]

    total_h = 0.0
    card_pos = {}

    # ── Build card_pos map ────────────────────────────────
    for col_idx, col in enumerate(cascades):
        n = len(col)
        for i, card in enumerate(col):
            card_pos[card] = (col_idx, n - 1 - i)  # depth_from_top
    for card in freecells:
        if card:
            card_pos[card] = (-1, 0)

    # ── 1. Base cost ──────────────────────────────────────
    # safe=0.1 < actual 0.5 ✓
    # unsafe=0.99 < actual 1.0 ✓
    for suit in ("H", "D", "C", "S"):
        for rank in range(foundations[suit] + 1, 14):
            card = (suit, rank)
            if _is_safe_to_auto_move(card, foundations):
                total_h += 0.1
            else:
                total_h += 0.99

    # ── 2. Sequence break penalty ─────────────────────────
    # 1 break cần ít nhất 1 cascade move
    # min cascade cost = 1.0 (cascade tạo empty col)
    # → 0.3 per break < 1.0 ✓ admissible
    for col in cascades:
        for i in range(len(col) - 1):
            s1, r1 = col[i]
            s2, r2 = col[i + 1]
            if (is_red(s1) == is_red(s2)) or (r2 != r1 - 1):
                total_h += 0.3

    # ── 3. Target buried penalty ──────────────────────────
    # Mỗi lá đè cần ít nhất 1 move để dọn (min cost = 0.5)
    # → 0.1 per depth < 0.5 ✓ admissible
    for suit in ("H", "D", "C", "S"):
        next_rank = foundations[suit] + 1
        if next_rank > 13:
            continue
        target = (suit, next_rank)
        if target in card_pos:
            _, depth = card_pos[target]
            total_h += depth * 0.1

    return total_h


# ──────────────────────────────────────────────────────────
# Move cost
# ──────────────────────────────────────────────────────────

def move_cost(move, state_before, state_after) -> float:
    """
    Cost phải cùng scale với heuristic (đơn vị "1 move ~ 1 unit").

    foundation safe     → 0.1   (tiến trình thật, ưu tiên cao nhất)
    foundation (mb block) → 0.99
    tạo cột rỗng    → 1.0   (rất có giá trị)
    freecell→stack  → 1.5   (giải phóng freecell + xây stack)
    cascade bình thường → 2.0
    lấp cột rỗng    → 3.0   (tốn resource quý)
    cascade→freecell → 3.0  (cất tạm, tốn freecell)
    """
    mtype = move[0]

    if "foundation" in mtype:
        # Lấy card vừa được move lên foundation
        if mtype == "cascade_to_foundation":
            col = state_before["cascades"][move[1]]
            card = col[-1] if col else None
        else:  # freecell_to_foundation
            card = state_before["freecells"][move[1]]

        if card and _is_safe_to_auto_move(card, state_before["foundations"]):
            return 0.1   # safe: guaranteed progress
        return 0.99       # unsafe: có thể block lá khác


    cascades_before = state_before["cascades"]

    if mtype == "cascade_to_freecell":
        col_idx = move[1]
        if len(cascades_before[col_idx]) == 1:
            return 1.0   # tạo cột rỗng
        return 3.0

    if mtype == "freecell_to_cascade":
        dst_col = move[2]
        if not cascades_before[dst_col]:
            return 3.0   # lấp cột rỗng
        return 1.5

    if mtype == "cascade_to_cascade":
        src_col = move[1]
        dst_col = move[2]
        if len(cascades_before[src_col]) == 1:
            return 1.0   # tạo cột rỗng
        if not cascades_before[dst_col]:
            return 3.0   # lấp cột rỗng
        return 2.0

    return 2.0


# ──────────────────────────────────────────────────────────
# Helper: expand 1 state
# ──────────────────────────────────────────────────────────

def _expand(state):
    """
    Sinh tất cả successor states.
    Trả về list of (successor_state, primary_move, auto_moves, step_cost).
    """
    raw_moves = get_moves(state)
    moves     = filter_dominated_moves(raw_moves, state)
    results   = []

    for move in moves:
        s1 = apply_move(state, move)
        s2, auto = apply_safe_auto_moves(s1)
        cost = move_cost(move, state, s1) + len(auto) * 0.1
        results.append((s2, move, auto, cost))

    return results


def _full_path(primary_move, auto_moves, path):
    return path + [primary_move] + auto_moves


# ──────────────────────────────────────────────────────────
# Helper: save stats
# ──────────────────────────────────────────────────────────

_SOLVER_STATS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solver_runs.csv")

def _append_solver_csv(algorithm_name, result, memory_peak_bytes):
    fieldnames = [
        "algorithm", "time_sec",
        "memory_peak_traced_bytes", "memory_peak_traced_mb",
        "expanded_nodes", "solution_length", "solved",
    ]
    row = {
        "algorithm":                  algorithm_name,
        "time_sec":                   result["time"],
        "memory_peak_traced_bytes":   memory_peak_bytes,
        "memory_peak_traced_mb":      round(memory_peak_bytes / (1024 * 1024), 4),
        "expanded_nodes":             result["expanded_nodes"],
        "solution_length":            result["length"],
        "solved":                     result["solution"] is not None,
    }
    file_exists = os.path.isfile(_SOLVER_STATS_CSV)
    with open(_SOLVER_STATS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            w.writeheader()
        w.writerow(row)


def _finalize(algorithm_name, result):
    _, peak = tracemalloc.get_traced_memory()
    if tracemalloc.is_tracing():
        tracemalloc.stop()
    _append_solver_csv(algorithm_name, result, peak)
    return result


# ──────────────────────────────────────────────────────────
# BFS optimized
# ──────────────────────────────────────────────────────────

def bfs_optimized(initial_state):
    tracemalloc.start()
    try:
        start = time.time()

        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        queue    = deque([(init_state, init_auto)])
        visited  = {init_key}
        expanded = 0

        while queue:
            state, path = queue.popleft()

            if is_goal(state):
                return _finalize("BFS", {
                    "solution": path, "time": time.time() - start,
                    "expanded_nodes": expanded, "length": len(path),
                })

            expanded += 1

            for succ, move, auto, _cost in _expand(state):
                key = encode_state(succ)
                if key not in visited:
                    expanded += len(auto)
                    visited.add(key)
                    queue.append((succ, _full_path(move, auto, path)))

        return _finalize("BFS", {
            "solution": None, "time": time.time() - start,
            "expanded_nodes": expanded, "length": 0,
        })
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# DFS optimized
# ──────────────────────────────────────────────────────────

def dfs_optimized(initial_state, max_depth=300):
    tracemalloc.start()
    try:
        start = time.time()

        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        stack    = [(init_state, init_auto)]
        visited  = {init_key}
        expanded = 0

        while stack:
            state, path = stack.pop()

            if is_goal(state):
                return _finalize("DFS", {
                    "solution": path, "time": time.time() - start,
                    "expanded_nodes": expanded, "length": len(path),
                })

            if len(path) > max_depth:
                continue

            expanded += 1

            for succ, move, auto, _cost in reversed(_expand(state)):
                key = encode_state(succ)
                if key not in visited:
                    expanded += len(auto)
                    visited.add(key)
                    stack.append((succ, _full_path(move, auto, path)))

        return _finalize("DFS", {
            "solution": None, "time": time.time() - start,
            "expanded_nodes": expanded, "length": 0,
        })
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# UCS optimized
# ──────────────────────────────────────────────────────────

def _reconstruct_path(parent_map, goal_key):
    solution = []
    key = goal_key
    while parent_map[key][0] is not None:
        parent_key, move, auto = parent_map[key]
        solution = [move] + auto + solution
        key = parent_key
    _, _, init_auto = parent_map[key]
    return init_auto + solution


def ucs_optimized(initial_state, max_nodes=500_000):
    tracemalloc.start()
    try:
        start = time.time()

        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        counter      = 0
        h0           = heuristic(init_state)
        pq           = [(0, h0, counter, init_key)]
        g_score      = {init_key: 0}
        parent_map   = {init_key: (None, None, init_auto)}
        key_to_state = {init_key: init_state}
        expanded     = 0

        while pq:
            cost, _h, _, cur_key = heapq.heappop(pq)

            if cost > g_score.get(cur_key, float("inf")):
                continue

            state = key_to_state[cur_key]

            if is_goal(state):
                solution = _reconstruct_path(parent_map, cur_key)
                return _finalize("UCS", {
                    "solution": solution, "time": time.time() - start,
                    "expanded_nodes": expanded, "length": len(solution),
                })

            if expanded >= max_nodes:
                break

            expanded += 1

            for succ, move, auto, step_cost in _expand(state):
                new_cost = cost + step_cost
                key = encode_state(succ)

                if new_cost < g_score.get(key, float("inf")):
                    expanded += len(auto)
                    g_score[key]      = new_cost
                    parent_map[key]   = (cur_key, move, auto)
                    key_to_state[key] = succ
                    counter += 1
                    # Dùng heuristic thật làm tie-breaker (tốt hơn h_light)
                    heapq.heappush(pq, (new_cost, heuristic(succ), counter, key))

        return _finalize("UCS", {
            "solution": None, "time": time.time() - start,
            "expanded_nodes": expanded, "length": 0,
        })
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# A* core (dùng chung cho astar_optimized và weighted variant)
# ──────────────────────────────────────────────────────────

def _astar_core(initial_state, weight: float, label: str, max_nodes: int = 500_000):
    tracemalloc.start()
    try:
        start = time.time()

        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        counter = 0

        # ── caches ─────────────────────────────
        h_cache = {}

        def get_h(key, state):
            if key not in h_cache:
                h_cache[key] = heuristic(state)
            return h_cache[key]

        # ── core structures ────────────────────
        h0 = get_h(init_key, init_state)

        pq = [(weight * h0, counter, 0, init_key)]  # (f, tie, g, key)

        g_score = {init_key: 0}
        parent_map = {init_key: (None, None, init_auto)}
        key_to_state = {init_key: init_state}

        closed = set()
        expanded = 0

        # ──────────────────────────────────────
        while pq:
            f, _, g, cur_key = heapq.heappop(pq)

            if cur_key in closed:
                continue
            closed.add(cur_key)

            state = key_to_state[cur_key]

            # ── GOAL ──────────────────────────
            if is_goal(state):
                solution = _reconstruct_path(parent_map, cur_key)
                return _finalize(label, {
                    "solution": solution,
                    "time": time.time() - start,
                    "expanded_nodes": expanded,
                    "length": len(solution),
                })

            if expanded >= max_nodes:
                break

            expanded += 1

            # ── EXPAND ────────────────────────
            for succ, move, auto, step_cost in _expand(state):
                key = encode_state(succ)

                if key in closed:
                    continue

                new_g = g + step_cost

                if new_g < g_score.get(key, float("inf")):
                    expanded += len(auto)
                    g_score[key] = new_g
                    parent_map[key] = (cur_key, move, auto)
                    key_to_state[key] = succ

                    new_f = new_g + weight * get_h(key, succ)

                    counter += 1
                    heapq.heappush(pq, (new_f, counter, new_g, key))

            # ── MEMORY CLEAN (rất quan trọng) ──
            del key_to_state[cur_key]

        # ── FAIL ─────────────────────────────
        return _finalize(label, {
            "solution": None,
            "time": time.time() - start,
            "expanded_nodes": expanded,
            "length": 0,
        })

    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# A* optimized  (Anytime Weighted A*)
# ──────────────────────────────────────────────────────────

# Danh sách weights thử lần lượt.
# w=2.0: nhanh, gần optimal. w=3.0→5.0: fallback cho ván cực khó.
_ASTAR_WEIGHTS   = [2.0, 3.0, 5.0]
_ASTAR_MAX_NODES = 150_000   # limit mỗi lần thử; tổng ~450K nodes

def astar_optimized(initial_state):
    """
    Anytime Weighted A*:

    Thử lần lượt weight=[2.0, 3.0, 5.0]. Mỗi lần cho phép expand
    tối đa _ASTAR_MAX_NODES nodes. Trả về solution đầu tiên tìm được.

    - Ván dễ (h < 100): thường giải được ở w=2.0, < 0.5s
    - Ván khó (h ~ 190): có thể cần w=3.0 hoặc 5.0, < 3s
    - Nếu không giải được: trả về solution=None

    Lý do dùng nhiều weights thay vì 1 weight lớn:
      w=2.0 tìm solution ngắn hơn (tiết kiệm animation)
      w=5.0 dùng làm backup khi w=2.0 kẹt ở local region
    """
    tracemalloc.start()
    t0       = time.time()
    total_expanded = 0

    for w in _ASTAR_WEIGHTS:
        result = _astar_core(initial_state, weight=w,
                             label="A*", max_nodes=_ASTAR_MAX_NODES)
        total_expanded += result["expanded_nodes"]

        if result["solution"] is not None:
            # Ghi đè stats với tổng nodes thật sự
            result["expanded_nodes"] = total_expanded
            result["time"]           = round(time.time() - t0, 4)
            return result

    # Không tìm được với bất kỳ weight nào
    return {
        "solution":      None,
        "time":          round(time.time() - t0, 4),
        "expanded_nodes": total_expanded,
        "length":        0,
    }