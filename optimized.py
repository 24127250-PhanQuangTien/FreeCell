import heapq
import time
import csv
from collections import deque
import os
import tracemalloc

from game import get_moves, apply_move, is_goal, is_red
from utilities import encode_state, apply_safe_auto_moves, filter_dominated_moves, _is_safe_to_auto_move


# ──────────────────────────────────────────────────────────
# Heuristic  (REDESIGNED)
# ──────────────────────────────────────────────────────────
#
# Vấn đề cũ:
#   - Values quá nhỏ (0.1 / 0.3 / 0.99) → h bị g nuốt khi search sâu
#   - Chỉ check burial depth của "lá cần tiếp theo" → bỏ sót nhiều thông tin
#
# Thiết kế mới:
#   h ≈ (số lá chưa lên foundation)
#     + (tổng burial depth của TẤT CẢ lá cần lên)  ← thay đổi lớn nhất
#     + (sequence break penalty mạnh hơn)
#     + (freecell occupancy penalty)
#
# Với weighted A* (w ≥ 3), không cần admissible → ưu tiên informative hơn.

# def heuristic(state) -> float:
#     foundations = state["foundations"]
#     cascades    = state["cascades"]
#     freecells   = state["freecells"]

#     remaining = 52 - sum(foundations.values())
#     if remaining == 0:
#         return 0.0

#     # ── Xây depth_map: mỗi lá → số lá đang đè lên nó ──
#     depth_map: dict = {}
#     for col in cascades:
#         n = len(col)
#         for i, card in enumerate(col):
#             depth_map[card] = n - 1 - i   # lá ở top → depth=0

#     total = float(remaining)  # Component 1: mỗi lá cần ≥1 move

#     # Component 2: burial depth của TẤT CẢ lá chưa lên foundation
#     for suit in ("H", "D", "C", "S"):
#         for rank in range(foundations[suit] + 1, 14):
#             card = (suit, rank)
#             depth = depth_map.get(card, 0)   # 0 nếu ở freecell hoặc top
#             total += depth                    # mỗi lá đè → cần thêm ≥1 move

#     # Component 3: sequence break penalty (tăng từ 0.3 → 1.5)
#     for col in cascades:
#         for i in range(len(col) - 1):
#             s1, r1 = col[i]
#             s2, r2 = col[i + 1]
#             if (is_red(s1) == is_red(s2)) or (r2 != r1 - 1):
#                 total += 1.5

#     # Component 4: freecell occupancy penalty
#     fc_occupied = sum(1 for c in freecells if c is not None)
#     total += fc_occupied * 1.5

#     return total

def heuristic(state) -> float:
    foundations = state["foundations"]
    cascades = state["cascades"]
    freecells = state["freecells"]

    remaining = 52 - sum(foundations.values())
    if remaining == 0:
        return 0.0

    # Tìm độ chôn của lá tiếp theo cần lên foundation cho mỗi suit
    need_depth = 0.0
    targets = {
        (suit, foundations[suit] + 1): None
        for suit in ("H", "D", "C", "S")
        if foundations[suit] < 13
    }

    unresolved = set(targets.keys())
    if unresolved:
        for col in cascades:
            for depth, card in enumerate(reversed(col)):
                if card in unresolved:
                    targets[card] = depth
                    unresolved.remove(card)
                    if not unresolved:
                        break
            if not unresolved:
                break

    for depth in targets.values():
        if depth is not None:
            need_depth += depth

    occupied_fc = sum(1 for c in freecells if c is not None)

    bad_adj = 0
    for col in cascades:
        for lower, upper in zip(col, col[1:]):
            if (is_red(lower[0]) == is_red(upper[0])) or (upper[1] != lower[1] - 1):
                bad_adj += 1

    return (
        float(remaining)
        + 1.25 * need_depth
        + 0.75 * occupied_fc
        + 0.35 * bad_adj
    )

# ──────────────────────────────────────────────────────────
# Move cost  (REDESIGNED — nhất quán, không oscillation)
# ──────────────────────────────────────────────────────────
#
# Vấn đề cũ:
#   cascade→freecell = 3.0  nhưng  freecell→cascade = 1.5
#   → "undo" rẻ hơn "do" → A* loop qua lại vô tận
#
# Thiết kế mới: uniform cost = 1.0, ưu đãi nhẹ cho foundation moves.
#   Mọi move đều cost bằng nhau → f = g + w*h sạch và dễ hiểu.
#   Foundation move (progress thật sự) → 0.5 để ưu tiên.

def move_cost(move, state_before, state_after) -> float:
    mtype = move[0]

    if "foundation" in mtype:
        return 0.5      # tiến trình thật → luôn ưu tiên

    # Tạo cột rỗng: có giá trị → khuyến khích nhẹ
    if mtype in ("cascade_to_freecell", "cascade_to_cascade"):
        src = move[1]
        if len(state_before["cascades"][src]) == 1:
            return 0.8  # tạo empty col

    return 1.0          # tất cả các move khác đều bằng nhau


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
        cost = move_cost(move, state, s1) + len(auto) * 0.5
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
                    heapq.heappush(pq, (new_cost, heuristic(succ), counter, key))

        return _finalize("UCS", {
            "solution": None, "time": time.time() - start,
            "expanded_nodes": expanded, "length": 0,
        })
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# A* core
# ──────────────────────────────────────────────────────────

def _astar_core(initial_state, weight: float, label: str, max_nodes: int = 500_000):
    tracemalloc.start()
    try:
        start = time.time()

        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        counter = 0

        h_cache: dict = {}

        def get_h(key, state):
            if key not in h_cache:
                h_cache[key] = heuristic(state)
            return h_cache[key]

        h0 = get_h(init_key, init_state)
        pq = [(weight * h0, counter, 0.0, init_key)]  # (f, tie, g, key)

        g_score    = {init_key: 0.0}
        parent_map = {init_key: (None, None, init_auto)}
        key_to_state = {init_key: init_state}

        closed   = set()
        expanded = 0

        while pq:
            f, _, g, cur_key = heapq.heappop(pq)

            if cur_key in closed:
                continue
            closed.add(cur_key)

            state = key_to_state[cur_key]

            if is_goal(state):
                solution = _reconstruct_path(parent_map, cur_key)
                return _finalize(label, {
                    "solution":      solution,
                    "time":          time.time() - start,
                    "expanded_nodes": expanded,
                    "length":        len(solution),
                })

            if expanded >= max_nodes:
                break

            expanded += 1

            for succ, move, auto, step_cost in _expand(state):
                key = encode_state(succ)

                if key in closed:
                    continue

                new_g = g + step_cost

                if new_g < g_score.get(key, float("inf")):
                    expanded += len(auto)
                    g_score[key]      = new_g
                    parent_map[key]   = (cur_key, move, auto)
                    key_to_state[key] = succ

                    new_f = new_g + weight * get_h(key, succ)
                    counter += 1
                    heapq.heappush(pq, (new_f, counter, new_g, key))

            del key_to_state[cur_key]

        return _finalize(label, {
            "solution":      None,
            "time":          time.time() - start,
            "expanded_nodes": expanded,
            "length":        0,
        })

    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# A* optimized  (Anytime Weighted A*)
# ──────────────────────────────────────────────────────────
#
# Thay đổi so với phiên bản cũ:
#   - Weights: [2.0, 3.0, 5.0] → [3.0, 5.0, 8.0]
#     w=3.0 đã đủ aggressive với heuristic mới; w=8.0 là fallback
#   - max_nodes: 150K → 200K (heuristic tốt hơn → ít nodes hơn trên thực tế)
#
# Tại sao w cao hơn?
#   h mới lớn hơn nhiều → cùng 1 w, search đã focused hơn.
#   Với h ~ 80-150, w=3 → 2h_old ≈ 3h_new về mức độ greedy.

_ASTAR_WEIGHTS   = [3.0, 5.0, 8.0]
_ASTAR_MAX_NODES = 500_000

def astar_optimized(initial_state):
    """
    Anytime Weighted A*:
    Thử lần lượt weight=[3.0, 5.0, 8.0]. Trả về solution đầu tiên tìm được.
    """
    tracemalloc.start()
    t0             = time.time()
    total_expanded = 0

    for w in _ASTAR_WEIGHTS:
        result = _astar_core(initial_state, weight=w,
                             label="A*", max_nodes=_ASTAR_MAX_NODES)
        total_expanded += result["expanded_nodes"]

        if result["solution"] is not None:
            result["expanded_nodes"] = total_expanded
            result["time"]           = round(time.time() - t0, 4)
            return result

    return {
        "solution":       None,
        "time":           round(time.time() - t0, 4),
        "expanded_nodes": total_expanded,
        "length":         0,
    }