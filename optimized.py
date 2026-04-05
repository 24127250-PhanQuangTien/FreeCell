import heapq
import time
import csv
from collections import deque
import os
import tracemalloc

from game import get_moves, apply_move, is_goal, is_red
from utilities import state_key, filter_dominated_moves, EMPTY


# ──────────────────────────────────────────────────────────
# Heuristic  (REDESIGNED)
# ──────────────────────────────────────────────────────────

# def heuristic(state) -> float:
#     foundations = state["foundations"]
#     cascades    = state["cascades"]
#     freecells   = state["freecells"]

#     remaining = 52 - sum(foundations)
#     if remaining == 0:
#         return 0.0

#     # Burial depth của lá tiếp theo cần lên foundation cho mỗi suit
#     targets: dict = {}
#     for suit in range(4):
#         need_rank = foundations[suit] + 1
#         if need_rank <= 13:
#             targets[suit * 13 + (need_rank - 1)] = 0

#     unresolved = set(targets)
#     if unresolved:
#         for col in cascades:
#             for depth, cid in enumerate(reversed(col)):
#                 if cid in unresolved:
#                     targets[cid] = depth
#                     unresolved.discard(cid)
#                     if not unresolved:
#                         break
#             if not unresolved:
#                 break

#     need_depth  = sum(targets.values())
#     occupied_fc = sum(1 for c in freecells if c != EMPTY)

#     return float(remaining) + 1.5 * need_depth + 0.5 * occupied_fc

def heuristic(state) -> float:
    foundations = state["foundations"]
    cascades    = state["cascades"]
    freecells   = state["freecells"]

    remaining = 52 - sum(foundations)
    if remaining == 0:
        return 0.0

    # ─────────────────────────────
    # 1. Multi-layer targets
    # ─────────────────────────────
    targets = {}
    for suit in range(4):
        base = foundations[suit]
        for k in range(1, 4):
            rank = base + k
            if rank <= 13:
                cid = suit * 13 + (rank - 1)
                targets[cid] = 0

    unresolved = set(targets)

    for col in cascades:
        for depth, cid in enumerate(reversed(col)):
            if cid in unresolved:
                targets[cid] = depth * 1.3
                unresolved.discard(cid)
        if not unresolved:
            break

    need_depth = sum(targets.values())

    # ─────────────────────────────
    # 2. Freecell usage
    # ─────────────────────────────
    occupied_fc = 0
    for c in freecells:
        if c != EMPTY:
            occupied_fc += 1

    # ─────────────────────────────
    # 3. Bad sequence (INLINE)
    # ─────────────────────────────
    bad_seq = 0
    for col in cascades:
        for i in range(len(col) - 1):
            a = col[i]
            b = col[i + 1]

            # inline check:
            # same color OR not descending
            if (a // 13) % 2 == (b // 13) % 2 or (a % 13) != (b % 13 + 1):
                bad_seq += 1

    # ─────────────────────────────
    # 4. Mobility penalty
    # ─────────────────────────────
    empty_cols = 0
    for col in cascades:
        if not col:
            empty_cols += 1

    mobility = empty_cols + (len(freecells) - occupied_fc)

    if mobility == 0:
        mobility_penalty = 8.0
    elif mobility == 1:
        mobility_penalty = 4.0
    else:
        mobility_penalty = 0.0

    # ─────────────────────────────
    # FINAL
    # ─────────────────────────────
    return (
        1.0 * remaining
        + 1.1 * need_depth
        + 0.6 * occupied_fc
        + 0.8 * bad_seq
        + mobility_penalty
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
    Trả về list of (successor_state, move, step_cost).
    """
    raw_moves = get_moves(state)
    moves     = filter_dominated_moves(raw_moves, state)
    results   = []

    for move in moves:
        s1 = apply_move(state, move)
        cost = move_cost(move, state, s1)
        results.append((s1, move, cost))

    return results



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
#
# Thay đổi so với phiên bản cũ:
#   - Thêm max_nodes (mặc định 150_000) → tránh lag / OOM vô hạn
#   - Dùng parent_map thay vì lưu path trong mỗi queue entry
#     → tiết kiệm bộ nhớ đáng kể (O(nodes) thay vì O(nodes × depth))

def bfs_optimized(initial_state, max_nodes: int = 1_999_999):
    tracemalloc.start()
    try:
        start    = time.time()
        init_key = state_key(initial_state)

        queue      = deque([init_key])
        visited    = {init_key}
        parent_map = {init_key: (None, None)}   # key → (parent_key, move)
        state_map  = {init_key: initial_state}  # key → state (để expand)
        expanded   = 0

        while queue:
            if expanded >= max_nodes:
                break

            cur_key = queue.popleft()
            state   = state_map[cur_key]

            if is_goal(state):
                solution = _reconstruct_path(parent_map, cur_key)
                return _finalize("BFS", {
                    "solution": solution, "time": time.time() - start,
                    "expanded_nodes": expanded, "length": len(solution),
                })

            expanded += 1

            for succ, move, _cost in _expand(state):
                key = state_key(succ)
                if key not in visited:
                    visited.add(key)
                    parent_map[key] = (cur_key, move)
                    state_map[key]  = succ
                    queue.append(key)

            # Giải phóng state đã expand xong (không cần nữa)
            del state_map[cur_key]

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
#
# Thay đổi so với phiên bản cũ:
#   - Dùng parent_map thay vì lưu path trong stack
#     → giảm bộ nhớ, tránh copy list path mỗi node

def dfs_optimized(initial_state, max_depth: int = 300, max_node: int = 1_999_999):
    tracemalloc.start()
    try:
        start    = time.time()
        init_key = state_key(initial_state)

        # Stack lưu (key, depth) thay vì (state, path)
        stack      = [(init_key, 0)]
        visited    = {init_key}
        parent_map = {init_key: (None, None)}
        state_map  = {init_key: initial_state}
        expanded   = 0

        while stack:
            cur_key, depth = stack.pop()
            state = state_map.get(cur_key)
            if state is None:           # đã bị xóa (node cũ trong stack)
                continue

            if is_goal(state):
                solution = _reconstruct_path(parent_map, cur_key)
                return _finalize("DFS", {
                    "solution": solution, "time": time.time() - start,
                    "expanded_nodes": expanded, "length": len(solution),
                })

            if depth >= max_depth:
                continue

            if expanded >= max_node:
                break

            expanded += 1

            for succ, move, _cost in reversed(_expand(state)):
                key = state_key(succ)
                if key not in visited:
                    visited.add(key)
                    parent_map[key] = (cur_key, move)
                    state_map[key]  = succ
                    stack.append((key, depth + 1))

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
        parent_key, move = parent_map[key]
        solution.append(move)
        key = parent_key
    solution.reverse()
    return solution


def ucs_optimized(initial_state, max_nodes=1_999_999):
    tracemalloc.start()
    try:
        start = time.time()

        init_key     = state_key(initial_state)
        counter      = 0
        h0           = heuristic(initial_state)
        pq           = [(0, h0, counter, init_key)]
        g_score      = {init_key: 0}
        parent_map   = {init_key: (None, None)}
        key_to_state = {init_key: initial_state}
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

            for succ, move, step_cost in _expand(state):
                new_cost = cost + step_cost
                key = state_key(succ)

                if new_cost < g_score.get(key, float("inf")):
                    g_score[key]      = new_cost
                    parent_map[key]   = (cur_key, move)
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

def _astar_core(initial_state, weight: float, max_nodes: int = 1_999_999):
    """
    Pure A* search — không quản lý tracemalloc, không ghi CSV.
    Chỉ trả về raw result dict.
    Được gọi bởi astar_optimized (quản lý memory + CSV bên ngoài).
    """
    start = time.time()

    init_key = state_key(initial_state)
    counter  = 0

    h_cache: dict = {}

    def get_h(key, state):
        if key not in h_cache:
            h_cache[key] = heuristic(state)
        return h_cache[key]

    h0 = get_h(init_key, initial_state)
    pq = [(weight * h0, counter, 0.0, init_key)]   # (f, tie, g, key)

    g_score      = {init_key: 0.0}
    parent_map   = {init_key: (None, None)}
    key_to_state = {init_key: initial_state}

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
            return {
                "solution":       solution,
                "time":           time.time() - start,
                "expanded_nodes": expanded,
                "length":         len(solution),
            }

        if expanded >= max_nodes:
            break

        expanded += 1

        for succ, move, step_cost in _expand(state):
            key = state_key(succ)

            if key in closed:
                continue

            new_g = g + step_cost

            if new_g < g_score.get(key, float("inf")):
                g_score[key]      = new_g
                parent_map[key]   = (cur_key, move)
                key_to_state[key] = succ

                new_f = new_g + weight * get_h(key, succ)
                counter += 1
                heapq.heappush(pq, (new_f, counter, new_g, key))

        del key_to_state[cur_key]

    return {
        "solution":       None,
        "time":           time.time() - start,
        "expanded_nodes": expanded,
        "length":         0,
    }


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

    Sửa lỗi so với phiên bản cũ:
    - tracemalloc được quản lý TẠI ĐÂY, không trong _astar_core
      → tránh bị stop sớm sau lần gọi đầu tiên
    - _finalize (ghi CSV) chỉ gọi 1 lần duy nhất với expanded_nodes TỔNG CỘNG
      → stats CSV chính xác
    - finally block đảm bảo tracemalloc.stop() dù có exception
    """
    tracemalloc.start()
    t0             = time.time()
    total_expanded = 0

    try:
        for w in _ASTAR_WEIGHTS:
            result = _astar_core(initial_state, weight=w, max_nodes=_ASTAR_MAX_NODES)
            total_expanded += result["expanded_nodes"]

            if result["solution"] is not None:
                return _finalize("A*", {
                    "solution":       result["solution"],
                    "time":           round(time.time() - t0, 4),
                    "expanded_nodes": total_expanded,
                    "length":         result["length"],
                })

        # Không tìm được với bất kỳ weight nào
        return _finalize("A*", {
            "solution":       None,
            "time":           round(time.time() - t0, 4),
            "expanded_nodes": total_expanded,
            "length":         0,
        })

    finally:
        # Safety net: _finalize đã stop tracemalloc rồi,
        # nhưng nếu có exception trước đó thì cần stop tại đây.
        if tracemalloc.is_tracing():
            tracemalloc.stop()