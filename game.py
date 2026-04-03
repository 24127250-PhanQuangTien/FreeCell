from utilities import _is_safe_to_auto_move

def create_deck():
    suits = ['C', 'D', 'H', 'S'] 
    ranks = list(range(1, 14))
    
    deck = []
    for r in ranks:
        for s in suits:
            deck.append((s, r))
    return deck

def create_initial_state(gamenumber: int):
    indices = list(range(52))
    
    seed = gamenumber
    for i in range(51, 0, -1):
        seed = (seed * 214013 + 2531011) & 0x7FFFFFFF
        rand_val = (seed >> 16) & 0x7FFF
        j = rand_val % (i + 1)
        indices[i], indices[j] = indices[j], indices[i]
        
    indices.reverse()
    
    deck = create_deck()
    new_shuffled_deck = [deck[idx] for idx in indices]
    
    cascades = [[] for _ in range(8)]
    for i, card in enumerate(new_shuffled_deck):
        target_col = i % 8 
        cascades[target_col].append(card)
        
    return {
        "cascades": cascades,
        "freecells": [None] * 4,
        "foundations": {"H": 0, "D": 0, "C": 0, "S": 0},
    }

if __name__ == "__main__":
    # Test thử với ván bài 164
    state = create_initial_state(164)
    for i, col in enumerate(state["cascades"]):
        print(f"Cột {i}: {col}")

# Tạo màn chơi hướng dẫn
def create_instruction_state(seed=None):
    """
    Hàm tạo initial state lever easy cho newbie/algorithm giải được
    """
    state = {
        "cascades": [
            [('S',13), ('H',12), ('S',11), ('D',10), ('C',9), ('H',8)],
            [('C',12), ('D',11)],
            [('H',11), ('C',13), ('S',7), ('H',13), ('C',3), ('D',13)],
            [('S',8)],
            [('D',12), ('C',11), ('H',10), ('S',9), ('D',8), ('C',7), ('H',6)],
            [],
            [],
            [('C',10), ('D',9), ('C',8), ('H',7), ('C', 6), ('H',5), ('C',4)]
        ],
        "freecells": [('H', 9), ('S', 10), ('C',5), ('S',12)],
        "foundations": {"H": 4, "D": 7, "C": 2, "S": 6},
    }

    return state

#game_action
def is_red(suit):
    return suit in ["H", "D"]

def can_stack(card1, card2):
    suit1, rank1 = card1
    suit2, rank2 = card2

    return (is_red(suit1) != is_red(suit2)) and (rank1 == rank2 - 1)

def can_move_to_foundation(card, foundations):
    suit, rank = card
    return foundations[suit] == rank - 1

def get_moves(state):
    moves = []
    cascades = state["cascades"]
    freecells = state["freecells"]
    foundations = state["foundations"]

    #cascade -> foundation safe
    for i,col in enumerate(cascades):
        if col:
            card = col[-1]
            if can_move_to_foundation(card, foundations):
                if _is_safe_to_auto_move(card, foundations):
                    return [("cascade_to_foundation", i)]

    #freecell -> foundation safe
    for i, card in enumerate(freecells):
        if card:
            if can_move_to_foundation(card, foundations):
                if _is_safe_to_auto_move(card, foundations):
                    return [("freecell_to_foundation", i)]

    #cascade -> foundation
    for i,col in enumerate(cascades):
        if col:
            card = col[-1]
            if can_move_to_foundation(card, foundations):
                    moves.append(("cascade_to_foundation", i))

    #freecell -> foundation
    for i, card in enumerate(freecells):
        if card:
            if can_move_to_foundation(card, foundations):
                    moves.append(("freecell_to_foundation", i))

    #cascade -> freecell
    for i, col in enumerate(cascades):
        if col:
            for j in range(4):
                if freecells[j] is None:
                    moves.append(("cascade_to_freecell", i, j))
                    break  

    #freecell -> cascade
    for i, card in enumerate(freecells):
        if not card:
            continue

        empty_targets = []

        for j, col in enumerate(cascades):
            if not col:
                empty_targets.append(j)
            else:
                if can_stack(card, col[-1]):
                    moves.append(("freecell_to_cascade", i, j))

        if empty_targets:
            moves.append(("freecell_to_cascade", i, empty_targets[0]))

    #cascade -> cascade
    for i, col1 in enumerate(cascades):
        if not col1:
            continue

        card = col1[-1]
        empty_targets = []

        for j, col2 in enumerate(cascades):
            if i == j:
                continue

            if not col2:
                empty_targets.append(j)
            else:
                if can_stack(card, col2[-1]):
                    moves.append(("cascade_to_cascade", i, j))

        # chỉ lấy 1 cột rỗng
        if empty_targets:
            moves.append(("cascade_to_cascade", i, empty_targets[0]))

    return moves

def apply_move(state, move):
    """
    Tối ưu hóa: Chỉ tạo mới những cột thực sự thay đổi.
    Sử dụng tuple nếu có thể để giảm overhead của list.
    """
    # Không copy toàn bộ mảng cascades ngay từ đầu
    cascades = state["cascades"]
    freecells = state["freecells"]
    foundations = state["foundations"]
    
    # Tạo copy nông (shallow copy) nhanh chóng
    new_cascades = cascades.copy()
    new_freecells = freecells.copy()
    new_foundations = foundations.copy()
    
    move_type = move[0]

    if move_type == "cascade_to_foundation":
        i = move[1]
        # Chỉ copy cột bị ảnh hưởng
        new_cascades[i] = cascades[i][:-1] 
        suit = cascades[i][-1][0]
        new_foundations[suit] += 1

    elif move_type == "freecell_to_foundation":
        i = move[1]
        card = freecells[i]
        new_freecells[i] = None
        new_foundations[card[0]] += 1

    elif move_type == "cascade_to_freecell":
        i, j = move[1], move[2]
        card = cascades[i][-1]
        new_cascades[i] = cascades[i][:-1]
        new_freecells[j] = card

    elif move_type == "freecell_to_cascade":
        i, j = move[1], move[2]
        card = freecells[i]
        new_freecells[i] = None
        # Nối phần tử mới vào cuối
        new_cascades[j] = cascades[j] + [card] 

    elif move_type == "cascade_to_cascade":
        i, j = move[1], move[2]
        card = cascades[i][-1]
        new_cascades[i] = cascades[i][:-1]
        new_cascades[j] = cascades[j] + [card]

    return {
        "cascades": new_cascades,
        "freecells": new_freecells,
        "foundations": new_foundations
    }
    
#check GOAL
def is_goal(state):
    foundations = state["foundations"]
    return all(value == 13 for value in foundations.values())

def state_to_tuple(state):
    cascades = tuple(tuple(col) for col in state["cascades"])
    freecells = tuple(state["freecells"])
    foundations = tuple((k, state["foundations"][k]) for k in sorted(state["foundations"]))
    
    return (cascades, freecells, foundations)