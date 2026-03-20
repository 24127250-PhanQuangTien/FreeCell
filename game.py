import random
from copy import deepcopy

#basic 
def create_deck():
    suits = ["H", "D", "C", "S"]
    ranks = list(range(1, 14))
    
    return [(s, r) for s in suits for r in ranks]

def shuffle_deck(deck):
    random.shuffle(deck)
    return deck

def deal_cards(deck):
    cascades = []
    index = 0
    
    for i in range(8):
        if i < 4:
            cascades.append(deck[index:index+7])
            index += 7
        else:
            cascades.append(deck[index:index+6])
            index += 6
    
    return cascades

def create_initial_state():
    deck = shuffle_deck(create_deck())
    
    return {
        "cascades": deal_cards(deck),
        "freecells": [None]*4,
        "foundations": {"H": 0, "D": 0, "C": 0, "S": 0}
    }

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

    foundation_moves = [m for m in moves if "foundation" in m[0]]
    if foundation_moves:
        return foundation_moves

    return moves

def apply_move(state, move):
    new_state = {
        "cascades": [col[:] for col in state["cascades"]],
        "freecells": state["freecells"][:],
        "foundations": state["foundations"].copy()
    
    }

    freecells = new_state["freecells"]
    cascades = new_state["cascades"]
    foundations = new_state["foundations"]

    move_type = move[0]

    #cascade -> foundation
    if move_type == "cascade_to_foundation":
        i = move[1]
        card = cascades[i].pop()
        suit, rank = card
        foundations[suit] += 1

    #freecell -> foundation
    elif move_type == "freecell_to_foundation":
        i = move[1]
        card = freecells[i]
        freecells[i] = None
        suit, rank = card
        foundations[suit] += 1

    #cascade -> freecell
    elif move_type == "cascade_to_freecell":
        i, j = move[1], move[2]
        card = cascades[i].pop()
        freecells[j] = card

    #freecell -> cascade
    elif move_type == "freecell_to_cascade":
        i, j = move[1], move[2]
        card = freecells[i]
        freecells[i] = None
        cascades[j].append(card)

    #cascade -> cascade
    elif move_type == "cascade_to_cascade":
        i, j = move[1], move[2]
        card = cascades[i].pop()
        cascades[j].append(card)

    return new_state

#check GOAL
def is_goal(state):
    foundations = state["foundations"]
    return all(value == 13 for value in foundations.values())

def state_to_tuple(state):
    cascades = tuple(tuple(col) for col in state["cascades"])
    freecells = tuple(state["freecells"])
    foundations = tuple((k, state["foundations"][k]) for k in sorted(state["foundations"]))
    
    return (cascades, freecells, foundations)

if __name__ == "__main__":
    state = create_initial_state()
    print(state_to_tuple(state))