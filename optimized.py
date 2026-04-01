import heapq
import time
import csv
from collections import deque
import os
import tracemalloc

from game import get_moves, apply_move, is_goal
from utilities import encode_state, apply_safe_auto_moves, filter_dominated_moves


# ──────────────────────────────────────────────────────────
# Heuristic (dùng cho A*)
# ──────────────────────────────────────────────────────────

RED   = frozenset({"H", "D"})
BLACK = frozenset({"C", "S"})

def heuristic(state) -> float:
    """
    Với mỗi lá chưa lên foundation, tính lower bound:
        lb(card) = 1 + depth_from_top
    
    Tổng lb là admissible vì các move này phân biệt nhau 
    (1 move xử lý 1 lá tại 1 thời điểm)
    
    Consistent vì: mỗi move có thể giảm h đi <= 1
    """
    foundations = state["foundations"]
    total = 0

    depth_map = {} 
    for col in state["cascades"]:
        n = len(col)
        for i, card in enumerate(col):
            depth_map[card] = n - 1 - i  # 0 nếu là lá trên cùng

    for suit in ["H", "D", "C", "S"]:
        for rank in range(foundations[suit] + 1, 14):
            card = (suit, rank)
            
            if card in depth_map:
                # Trong cascade: cần dọn depth lá + 1 move lên foundation
                total += 1 + depth_map[card]
            else:
                # Trong freecell: chỉ cần 1 move
                total += 1

    return total


# ──────────────────────────────────────────────────────────
# Move cost table (dùng cho UCS và A*)
# ──────────────────────────────────────────────────────────
#
# Move type                             | Cost
# --------------------------------------|------
# Lên Foundation (cascade/freecell)     |  0.1 
# Giải phóng hoàn toàn 1 cột            |  1
# Freecell → Cascade (stack hợp lệ)     |  1.5   
# Cascade → Cascade (stack bình thường) |  2   
# Lấp đầy 1 cột đang trống              |  3   
# Cascade → Freecell (tốn ô tạm)        |  3  

def move_cost(move, state_before, state_after) -> float:
    """
    Tính cost thực của 1 move dựa trên ngữ cảnh game.
    Dùng cost nhỏ, sát nhau để UCS không phải explore quá nhiều nodes.
    """
    mtype = move[0]

    # Lên foundation: ưu tiên tuyệt đối
    if "foundation" in mtype:
        return 0.1

    cascades_before = state_before["cascades"]

    if mtype == "cascade_to_freecell":
        col_idx = move[1]
        # Cột chỉ còn 1 lá → sau move tạo cột rỗng → rất có giá trị
        if len(cascades_before[col_idx]) == 1:
            return 1
        return 3

    if mtype == "freecell_to_cascade":
        dst_col = move[2]
        # Lấp vào cột rỗng
        if not cascades_before[dst_col]:
            return 3
        return 1.5   # stack hợp lệ → giải phóng freecell

    if mtype == "cascade_to_cascade":
        src_col = move[1]
        dst_col = move[2]
        # Tạo cột rỗng
        if len(cascades_before[src_col]) == 1:
            return 1
        # Lấp vào cột rỗng
        if not cascades_before[dst_col]:
            return 3
        return 2

    return 2


# ──────────────────────────────────────────────────────────
# Helper: expand 1 state → list (new_state, move, auto_moves, step_cost)
# ──────────────────────────────────────────────────────────

def _expand(state):
    """
    Sinh tất cả successor states, mỗi successor đã được:
      1. apply primary move do solver chọn
      2. apply tất cả safe auto-moves tiếp theo

    Trả về list of (successor_state, primary_move, auto_moves_list, step_cost)
      - step_cost: chi phí của primary move theo bảng move_cost()
      - auto_moves đã được tính thêm cost 0.5 mỗi lá (lên foundation)
    """
    raw_moves = get_moves(state)
    moves     = filter_dominated_moves(raw_moves, state)
    results   = []

    for move in moves:
        s1 = apply_move(state, move)
        s2, auto = apply_safe_auto_moves(s1)
        # cost primary move + cost auto moves (mỗi auto là to_foundation → 0.5)
        cost = move_cost(move, state, s1) + len(auto) * 0.5
        results.append((s2, move, auto, cost))

    return results


def _full_path(primary_move, auto_moves, path):
    """Gộp primary move + auto moves vào path hiện tại."""
    return path + [primary_move] + auto_moves

# ──────────────────────────────────────────────────────────
# Helper: save data of algorithms
# ──────────────────────────────────────────────────────────

_SOLVER_STATS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solver_runs.csv")

def _append_solver_csv(algorithm_name, result, memory_peak_bytes):
    fieldnames = [
        "algorithm",
        "time_sec",
        "memory_peak_traced_bytes",
        "memory_peak_traced_mb",
        "expanded_nodes",
        "solution_length",
        "solved",
    ]
    row = {
        "algorithm": algorithm_name,
        "time_sec": result["time"],
        "memory_peak_traced_bytes": memory_peak_bytes,
        "memory_peak_traced_mb": round(memory_peak_bytes / (1024 * 1024), 4),
        "expanded_nodes": result["expanded_nodes"],
        "solution_length": result["length"],
        "solved": result["solution"] is not None,
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

        # Apply auto-moves cho initial state luôn
        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        queue   = deque([(init_state, init_auto)])   # (state, path_so_far)
        visited = {init_key}
        expanded = 0

        while queue:
            state, path = queue.popleft()

            if is_goal(state):
                return _finalize("BFS", {
                    "solution": path,
                    "time": time.time() - start,
                    "expanded_nodes": expanded,
                    "length": len(path),
                })

            expanded += 1

            for succ, move, auto, _cost in _expand(state):
                key = encode_state(succ)
                if key not in visited:
                    visited.add(key)
                    queue.append((succ, _full_path(move, auto, path)))

        return _finalize("BFS", {
            "solution": None,
            "time": time.time() - start,
            "expanded_nodes": expanded,
            "length": 0
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
                    "solution": path,
                    "time": time.time() - start,
                    "expanded_nodes": expanded,
                    "length": len(path),
                })

            if len(path) > max_depth:
                continue

            expanded += 1

            succs = _expand(state)
            # Reverse để DFS đi theo thứ tự tự nhiên
            for succ, move, auto, _cost in reversed(succs):
                key = encode_state(succ)
                if key not in visited:
                    visited.add(key)
                    stack.append((succ, _full_path(move, auto, path)))

        return _finalize("DFS", {
            "solution": None,
            "time": time.time() - start,
            "expanded_nodes": expanded,
            "length": 0
        })
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# UCS optimized
# ──────────────────────────────────────────────────────────

def _reconstruct_path(parent_map, goal_key):
    """
    Reconstruct solution từ parent_map.
    parent_map[key] = (parent_key, primary_move, auto_moves)
    """
    solution = []
    key = goal_key
    while parent_map[key][0] is not None:
        parent_key, move, auto = parent_map[key]
        solution = [move] + auto + solution
        key = parent_key
    # Thêm init_auto (auto-moves của initial state)
    _, _, init_auto = parent_map[key]
    return init_auto + solution


def ucs_optimized(initial_state, max_nodes=500_000):
    tracemalloc.start()
    try:
        start = time.time()

        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        # Dùng h nhỏ làm tie-breaker trong heap: (cost, h_tiebreak, counter, key)
        # → UCS vẫn optimal (cost là priority chính) nhưng explore ít hơn
        def h_light(state):
            """Đếm số lá chưa lên foundation — tie-break nhanh, không tốn CPU."""
            fnd = state["foundations"]
            return 52 - sum(fnd.values())

        counter     = 0
        h0          = h_light(init_state)
        pq          = [(0, h0, counter, init_key)]
        g_score     = {init_key: 0}
        parent_map  = {init_key: (None, None, init_auto)}
        key_to_state = {init_key: init_state}
        expanded    = 0

        while pq:
            cost, _h, _, cur_key = heapq.heappop(pq)

            if cost > g_score.get(cur_key, float("inf")):
                continue

            state = key_to_state[cur_key]

            if is_goal(state):
                solution = _reconstruct_path(parent_map, cur_key)
                return _finalize("UCS", {
                    "solution": solution,
                    "time": time.time() - start,
                    "expanded_nodes": expanded,
                    "length": len(solution),
                })

            if expanded >= max_nodes:
                break

            expanded += 1

            for succ, move, auto, step_cost in _expand(state):
                new_cost = cost + step_cost
                key = encode_state(succ)

                if new_cost < g_score.get(key, float("inf")):
                    g_score[key]      = new_cost
                    parent_map[key]   = (cur_key, move, auto)
                    key_to_state[key] = succ
                    counter += 1
                    heapq.heappush(pq, (new_cost, h_light(succ), counter, key))

        return _finalize("UCS", {
            "solution": None,
            "time": time.time() - start,
            "expanded_nodes": expanded,
            "length": 0
        })
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()


# ──────────────────────────────────────────────────────────
# A* optimized
# ──────────────────────────────────────────────────────────

def astar_optimized(initial_state):
    tracemalloc.start()
    try:
        start = time.time()

        init_state, init_auto = apply_safe_auto_moves(initial_state)
        init_key = encode_state(init_state)

        counter  = 0
        h0       = heuristic(init_state)
        pq       = [(h0, counter, 0, init_state, init_auto)]
        g_score  = {init_key: 0}
        closed   = set()
        expanded = 0

        while pq:
            f, _, g, state, path = heapq.heappop(pq)

            cur_key = encode_state(state)
            if cur_key in closed:
                continue
            closed.add(cur_key)

            if is_goal(state):
                return _finalize("A*", {
                    "solution": path,
                    "time": time.time() - start,
                    "expanded_nodes": expanded,
                    "length": len(path),
                })

            expanded += 1

            for succ, move, auto, step_cost in _expand(state):
                key = encode_state(succ)
                if key in closed:
                    continue

                new_g = g + step_cost

                if new_g < g_score.get(key, float("inf")):
                    g_score[key] = new_g
                    new_f = new_g + heuristic(succ)
                    counter += 1
                    heapq.heappush(pq, (new_f, counter, new_g, succ,
                                        _full_path(move, auto, path)))
        return _finalize("A*", {
            "solution": None,
            "time": time.time() - start,
            "expanded_nodes": expanded,
            "length": 0
        })
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()