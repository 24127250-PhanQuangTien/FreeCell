from collections import deque
from game import get_moves, apply_move, is_goal, state_to_tuple, can_stack
import heapq
import time

#BFS
def bfs(initial_state):
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
                "solution" : path,
                "time": end_time - start_time,
                "expanded_nodes": expanded_nodes,
                "length": len(path)
            }
        expanded_nodes += 1

        moves = get_moves(state)

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

#DFS
def dfs(initial_state, max_depth = 1000):
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

        #tránh đi quá sâu (rất quan trọng)
        if len(path) > max_depth:
            continue

        expanded_nodes += 1

        moves = get_moves(state)

        # (optional) đảo ngược để giống DFS chuẩn
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
def ucs(initial_state):
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

        for move in moves:
            new_state = apply_move(state, move)
            state_key = state_to_tuple(new_state)

            if state_key not in visited:
                visited.add(state_key)
                new_cost = cost + 1

                heapq.heappush(pq, (new_cost, id(new_state), new_state, path + [move]))

    end_time = time.time()
    return {
        "solution": None,
        "time": end_time - start_time,
        "expanded_nodes": expanded_nodes,
        "length": 0
    }

#A Star
# h(n) = numbers of leaf havent reached foundation 
def blocked_cards(state):
    count = 0
    for cascade in state["cascades"]:
        for i in range(len(cascade)-1):
            if not can_stack(cascade[i], cascade[i+1]):
                count += 1
    return count

RED = {'H', 'D'}
BLACK = {'S', 'C'}

def is_descending_alternating(card1, card2):
    s1, r1 = card1
    s2, r2 = card2

    return (
        r1 == r2 - 1 and
        ((s1 in RED and s2 in BLACK) or (s1 in BLACK and s2 in RED))
    )

def disorder_penalty(state):
    count = 0
    for cascade in state["cascades"]:
        for i in range(len(cascade)-1):
            if not is_descending_alternating(cascade[i], cascade[i+1]):
                count += 1
    return count

def empty_space_bonus(state):
    free_empty = sum(1 for cell in state["freecells"] if cell is None)
    empty_cascade = sum(1 for col in state["cascades"] if len(col) == 0)

    # bonus thêm nếu có thể move stack lớn
    mobility = (free_empty + 1) * (2 ** empty_cascade)

    return free_empty + 2 * empty_cascade + mobility * 0.1

def reverse_move(move):
    if move[0] == "cascade_to_freecell":
        return ("freecell_to_cascade", move[2], move[1])
    if move[0] == "freecell_to_cascade":
        return ("cascade_to_freecell", move[2], move[1])
    if move[0] == "cascade_to_cascade":
        return ("cascade_to_cascade", move[2], move[1])
    return None

#Heuristic
def Heuristic(state):
    foundations = state["foundations"]
    h1 = 52 - sum(foundations.values())
    h2 = blocked_cards(state)
    h3 = disorder_penalty(state)
    h4 = empty_space_bonus(state)

    return 5 * h1 + 3 * h2 + 2 * h3 - 2 * h4

def astar(initial_state):
    start_time = time.time()

    pq = []
    g_score = {}

    g_cost = 0
    h_cost = Heuristic(initial_state)

    heapq.heappush(pq, (g_cost + h_cost, id(initial_state), g_cost, initial_state, []))
    g_score[state_to_tuple(initial_state)] = 0

    expanded_nodes = 0

    while pq:
        f, _, g, state, path = heapq.heappop(pq)

        current_key = state_to_tuple(state)
        if g > g_score.get(current_key, float('inf')):
            continue

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

        for move in moves:
            if path and move == reverse_move(path[-1]):
                continue

            new_state = apply_move(state, move)
            state_key = state_to_tuple(new_state)

            new_g = g + 1

            if state_key not in g_score or new_g < g_score[state_key]:
                g_score[state_key] = new_g

                new_h = Heuristic(new_state)

                heapq.heappush(
                    pq,
                    (new_g + new_h, id(new_state), new_g, new_state, path + [move])
                )

    end_time = time.time()
    return {
        "solution": None,
        "time": end_time - start_time,
        "expanded_nodes": expanded_nodes,
        "length": 0
    }