import random

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

def ms_rand_c(seed: int) -> tuple[int, int]:
    """
    Đây là rand() của Microsoft C runtime (MSVC)
    seed = (seed * 214013 + 2531011) & 0xFFFFFFFF
    return = (seed >> 16) & 0x7FFF  → 15-bit number
    """
    seed = (seed * 214013 + 2531011) & 0xFFFFFFFF
    return seed, (seed >> 16) & 0x7FFF


def generate_ms_deck_original(gamenumber: int):
    """
    Dịch 1-1 từ C gốc của Microsoft FreeCell.
    
    C gốc:
        srand(gamenumber);
        for (i = 0; i < 52; i++) {
            j = rand() % wLeft;
            card[(i%8)+1][i/8] = deck[j];
            deck[j] = deck[--wLeft];
        }
    """
    MAXCOL = 9   # col 0 bỏ trống, dùng col 1-8
    MAXPOS = 21
    EMPTY  = -1

    # Khởi tạo bảng bài (giống C: card[MAXCOL][MAXPOS])
    card = [[EMPTY] * MAXPOS for _ in range(MAXCOL)]

    # Khởi tạo deck 52 lá
    deck  = list(range(52))
    wLeft = 52
    seed  = gamenumber

    for i in range(52):
        seed, r = ms_rand_c(seed)
        j = r % wLeft                        # j = rand() % wLeft
        card[(i % 8) + 1][i // 8] = deck[j] # card[(i%8)+1][i/8] = deck[j]
        deck[j] = deck[wLeft - 1]            # deck[j] = deck[--wLeft]
        wLeft -= 1

    return card


def card_index_to_card(idx: int):
    """
    C gốc:
        SUIT(card)  = card % 4   → 0=Club, 1=Diamond, 2=Heart, 3=Spade
        VALUE(card) = card / 4   → 0=Ace, 1=Deuce, ..., 12=King
    """
    suits = ["C", "D", "H", "S"]   # Club=0, Diamond=1, Heart=2, Spade=3
    suit  = suits[idx % 4]
    rank  = idx // 4 + 1            # 1-based (1=Ace, 13=King)
    return (suit, rank)


def create_initial_state(gamenumber: int):
    """
    Tạo state từ layout gốc của MS FreeCell C code.
    card[col][pos] với col từ 1-8, pos từ 0 trở đi.
    """
    card = generate_ms_deck_original(gamenumber)
    EMPTY = -1

    cascades = []
    for col in range(1, 9):          # col 1 → 8
        column = []
        for pos in range(21):
            c = card[col][pos]
            if c == EMPTY:
                break
            column.append(card_index_to_card(c))
        cascades.append(column)

    return {
        "cascades": cascades,
        "freecells": [None] * 4,
        "foundations": {"H": 0, "D": 0, "C": 0, "S": 0},
    }

# Tạo màn chơi hướng dẫn
def create_instruction_state(seed=None):
    """
    Hàm tạo initial state lever easy cho newbie/algorithm giải được
    """
    state = {
        "cascades": [
            [('S',5), ('S',10), ('C',4)],
            [('C',12), ('C',8), ('D',7)],
            [('C',2), ('H',9), ('S',3), ('C',13)],
            [('C',11), ('D',10), ('S',9), ('H',8), ('S',7), ('D',6), ('C',5), ('H',4), ('C',3)],
            [('H',3), ('D',12), ('S',11), ('H',10), ('C',9), ('D',8), ('C',7)],
            [('H',13), ('S',12), ('D',11), ('C', 10)],
            [('D',5), ('D',9), ('S',8), ('H',7), ('S', 6)],
            [('H',6), ('D',13), ('C',6), ('H',5), ('S', 4)]
        ],
        "freecells": [('S', 13), ('H', 11), ('H',12), None],
        "foundations": {"H": 2, "D": 4, "C": 1, "S": 2},
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