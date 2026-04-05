from utilities import SUITS, SUIT_IDX, EMPTY, _is_safe_to_auto_move

# ────────────────────
# Deck / Initial state
# ────────────────────

_GAME_SUITS = ['C', 'D', 'H', 'S']

def _build_deck() -> list[int]:
    """Tạo bộ 52 card_id theo đúng thứ tự gốc của game."""
    deck = []
    for rank in range(1, 14):
        for suit in _GAME_SUITS:
            deck.append(SUIT_IDX[suit] * 13 + (rank - 1))
    return deck

_DECK = _build_deck()


def create_initial_state(gamenumber: int) -> dict:
    """Tạo state ban đầu từ game number."""
    indices = list(range(52))
    seed = gamenumber
    for i in range(51, 0, -1):
        seed = (seed * 214013 + 2531011) & 0x7FFFFFFF
        j = (seed >> 16) & 0x7FFF
        j %= i + 1
        indices[i], indices[j] = indices[j], indices[i]
    indices.reverse()

    shuffled = [_DECK[idx] for idx in indices]

    cols: list[list[int]] = [[] for _ in range(8)]
    for i, cid in enumerate(shuffled):
        cols[i % 8].append(cid)

    return {
        "cascades":    tuple(tuple(col) for col in cols),
        "freecells":   (EMPTY, EMPTY, EMPTY, EMPTY),
        "foundations": (0, 0, 0, 0),               # H, D, C, S
    }


def create_instruction_state() -> dict:
    """State dễ dành cho newbie / test thuật toán."""
    def c(suit: str, rank: int) -> int:
        return SUIT_IDX[suit] * 13 + (rank - 1)

    return {
        "cascades": (
            (c('S',13), c('H',12), c('S',11), c('D',10), c('C',9), c('H',8),),
            (c('C',12), c('D',11),),
            (c('H',11), c('C',13), c('S',7), c('H',13),),
            (c('S',8),),
            (c('D',12), c('C',11), c('H',10), c('S',9), c('D',8), c('C',7),),
            (c('S',12), c('D',13),),
            (),
            (c('C',10), c('D',9), c('C',8),),
        ),
        "freecells":   (c('H',9), c('S',10), EMPTY, EMPTY),
        "foundations": (7, 7, 6, 6),               # H, D, C, S
    }


# ──────────
# Game logic
# ──────────

def is_red(cid: int) -> bool:
    """True nếu lá bài màu đỏ (H hoặc D). suit < 2 vì H=0, D=1."""
    return (cid // 13) < 2


def can_stack(cid_top: int, cid_bottom: int) -> bool:
    """cid_top đặt lên cid_bottom: khác màu, rank nhỏ hơn 1."""
    red_top    = (cid_top    // 13) < 2
    red_bottom = (cid_bottom // 13) < 2
    rank_top   = cid_top    % 13 + 1
    rank_bot   = cid_bottom % 13 + 1
    return (red_top != red_bottom) and (rank_top == rank_bot - 1)


def can_move_to_foundation(cid: int, foundations) -> bool:
    suit = cid // 13
    rank = cid % 13 + 1
    return foundations[suit] == rank - 1


# ───────────────
# Move generation
# ───────────────

def get_moves(state) -> list:
    cascades    = state["cascades"]
    freecells   = state["freecells"]
    foundations = state["foundations"]
    moves       = []

    for i, col in enumerate(cascades):
        if col:
            cid = col[-1]
            if can_move_to_foundation(cid, foundations) and \
               _is_safe_to_auto_move(cid, foundations):
                return [("cascade_to_foundation", i)]

    for i, cid in enumerate(freecells):
        if cid != EMPTY:
            if can_move_to_foundation(cid, foundations) and \
               _is_safe_to_auto_move(cid, foundations):
                return [("freecell_to_foundation", i)]

    for i, col in enumerate(cascades):
        if col and can_move_to_foundation(col[-1], foundations):
            moves.append(("cascade_to_foundation", i))

    for i, cid in enumerate(freecells):
        if cid != EMPTY and can_move_to_foundation(cid, foundations):
            moves.append(("freecell_to_foundation", i))

    first_empty_fc = next((i for i, c in enumerate(freecells) if c == EMPTY), None)

    if first_empty_fc is not None:
        for i, col in enumerate(cascades):
            if col:
                moves.append(("cascade_to_freecell", i, first_empty_fc))

    for i, cid in enumerate(freecells):
        if cid == EMPTY:
            continue
        first_empty_col = None
        for j, col in enumerate(cascades):
            if not col:
                if first_empty_col is None:
                    first_empty_col = j
            else:
                if can_stack(cid, col[-1]):
                    moves.append(("freecell_to_cascade", i, j))
        if first_empty_col is not None:
            moves.append(("freecell_to_cascade", i, first_empty_col))

    for i, col1 in enumerate(cascades):
        if not col1:
            continue
        cid = col1[-1]
        first_empty_col = None
        for j, col2 in enumerate(cascades):
            if i == j:
                continue
            if not col2:
                if first_empty_col is None:
                    first_empty_col = j
            else:
                if can_stack(cid, col2[-1]):
                    moves.append(("cascade_to_cascade", i, j))
        if first_empty_col is not None:
            moves.append(("cascade_to_cascade", i, first_empty_col))

    return moves


# ───────────
# Apply move
# ───────────

def apply_move(state, move) -> dict:
    """
    Tạo state mới, chỉ copy những thứ thực sự thay đổi.
    Cascades là tuple-of-tuples nên slice O(1) với CPython (shared storage).
    """
    cascades    = list(state["cascades"])
    freecells   = list(state["freecells"])
    foundations = list(state["foundations"])
    mtype       = move[0]

    if mtype == "cascade_to_foundation":
        i   = move[1]
        cid = cascades[i][-1]
        cascades[i]          = cascades[i][:-1]
        foundations[cid // 13] += 1

    elif mtype == "freecell_to_foundation":
        i   = move[1]
        cid = freecells[i]
        freecells[i]           = EMPTY
        foundations[cid // 13] += 1

    elif mtype == "cascade_to_freecell":
        i, j        = move[1], move[2]
        cid         = cascades[i][-1]
        cascades[i] = cascades[i][:-1]
        freecells[j] = cid

    elif mtype == "freecell_to_cascade":
        i, j         = move[1], move[2]
        cid          = freecells[i]
        freecells[i] = EMPTY
        cascades[j]  = cascades[j] + (cid,)

    elif mtype == "cascade_to_cascade":
        i, j        = move[1], move[2]
        cid         = cascades[i][-1]
        cascades[i] = cascades[i][:-1]
        cascades[j] = cascades[j] + (cid,)

    return {
        "cascades":    tuple(cascades),
        "freecells":   tuple(freecells),
        "foundations": tuple(foundations),
    }


# ───────────────
# Goal / Hashing
# ───────────────

def is_goal(state) -> bool:
    return all(v == 13 for v in state["foundations"])


def state_to_tuple(state) -> tuple:
    """State đã là tuple-of-tuples, hash trực tiếp được."""
    return (state["cascades"], state["freecells"], state["foundations"])


# ──────────
# Quick test
# ──────────

if __name__ == "__main__":
    from utilities import id_to_card

    state = create_initial_state(164)
    for i, col in enumerate(state["cascades"]):
        print(f"Cột {i}: {[id_to_card(c) for c in col]}")