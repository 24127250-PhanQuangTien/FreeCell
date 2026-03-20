from collections import deque
from game import get_moves, apply_move, is_goal, state_to_tuple
import time
import heapq

#optmize move
def prioritize_moves(moves):
    foundation_moves = [
        m for m in moves
        if m[0] in ["cascade_to_foundation", "freecell_to_foundation"]
    ]
    return foundation_moves if foundation_moves else moves


#BFS
def bfs_optimized(initial_state):
    start_time = time.time()

    queue = deque()
    visited = set()

    queue.append((initial_state, []))
    visited.add(state_to_tuple(initial_state))

    expanded_nodes = 0

    while queue:
        state, path = queue.popleft()

        if is_goal(state):
            end_time = time.time()
            return {
                "solution": path,
                "time": end_time - start_time,
                "expanded_nodes": expanded_nodes,
                "length": len(path)
            }

        expanded_nodes += 1

        moves = get_moves(state)

        # ưu tiên move tốt
        moves = prioritize_moves(moves)

        for move in moves:
            new_state = apply_move(state, move)
            state_key = state_to_tuple(new_state)

            if state_key not in visited:
                visited.add(state_key)
                queue.append((new_state, path + [move]))

    end_time = time.time()
    return {
        "solution": None,
        "time": end_time - start_time,
        "expanded_nodes": expanded_nodes,
        "length": 0
    }

import time
from game import get_moves, apply_move, is_goal, state_to_tuple

#DFS
def dfs_optimized(initial_state, max_depth = 1000):
    start_time = time.time()

    stack = []
    visited = set()

    stack.append((initial_state, []))
    visited.add(state_to_tuple(initial_state))

    expanded_nodes = 0

    while stack:
        state, path = stack.pop()

        if is_goal(state):
            end_time = time.time()
            return {
                "solution": path,
                "time": end_time - start_time,
                "expanded_nodes": expanded_nodes,
                "length": len(path)
            }

        # giới hạn độ sâu
        if len(path) > max_depth:
            continue

        expanded_nodes += 1

        moves = get_moves(state)

        #optimize ở đây
        moves = prioritize_moves(moves)

        # DFS cần reverse để giữ thứ tự hợp lý
        moves.reverse()

        for move in moves:
            new_state = apply_move(state, move)
            state_key = state_to_tuple(new_state)

            if state_key not in visited:
                visited.add(state_key)
                stack.append((new_state, path + [move]))

    end_time = time.time()
    return {
        "solution": None,
        "time": end_time - start_time,
        "expanded_nodes": expanded_nodes,
        "length": 0
    }

#UCS
def ucs_optimized(initial_state):
    start_time = time.time()

    pq = []
    visited = set()

    heapq.heappush(pq, (0, id(initial_state), initial_state, []))
    visited.add(state_to_tuple(initial_state))

    expanded_nodes = 0

    while pq:
        cost, _, state, path = heapq.heappop(pq)

        if is_goal(state):
            end_time = time.time()
            return {
                "solution": path,
                "time": end_time - start_time,
                "expanded_nodes": expanded_nodes,
                "length": len(path)
            }

        expanded_nodes += 1

        moves = get_moves(state)

        #optimize ở đây
        moves = prioritize_moves(moves)

        for move in moves:
            new_state = apply_move(state, move)
            state_key = state_to_tuple(new_state)

            if state_key not in visited:
                visited.add(state_key)

                new_cost = cost + 1

                heapq.heappush(
                    pq,
                    (new_cost, id(new_state), new_state, path + [move])
                )

    end_time = time.time()
    return {
        "solution": None,
        "time": end_time - start_time,
        "expanded_nodes": expanded_nodes,
        "length": 0
    }

#A STAR
#Heuristic
def Heuristic(state):
    return 52 - sum(state["foundations"].values())


def astar_optimized(initial_state):
    start_time = time.time()

    pq = []
    g_score = {}
    closed_set = set()

    start_key = state_to_tuple(initial_state)
    g_score[start_key] = 0

    heapq.heappush(pq, (Heuristic(initial_state), id(initial_state), 0, initial_state, []))

    expanded_nodes = 0

    while pq:
        f, _, g, state, path = heapq.heappop(pq)
        state_key = state_to_tuple(state)

        # ❗ nếu đã duyệt rồi → bỏ
        if state_key in closed_set:
            continue

        closed_set.add(state_key)

        if is_goal(state):
            return {
                "solution": path,
                "time": time.time() - start_time,
                "expanded_nodes": expanded_nodes,
                "length": len(path)
            }

        expanded_nodes += 1

        moves = get_moves(state)
        moves = prioritize_moves(moves)

        for move in moves:
            new_state = apply_move(state, move)
            new_key = state_to_tuple(new_state)

            new_g = g + 1

            if new_key not in g_score or new_g < g_score[new_key]:
                g_score[new_key] = new_g

                new_f = new_g + Heuristic(new_state)

                heapq.heappush(
                    pq,
                    (new_f, id(new_state), new_g, new_state, path + [move])
                )

    return {
        "solution": None,
        "time": time.time() - start_time,
        "expanded_nodes": expanded_nodes,
        "length": 0
    }