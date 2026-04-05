# ─────────
# Constants
# ─────────

SUITS = ["H", "D", "C", "S"]
SUIT_IDX = {s: i for i, s in enumerate(SUITS)}

EMPTY = -1

EMPTY_CARD      = 0b111111
MAX_CARDS_PER_COL = 13

BITS_PER_CARD   = 6
BITS_FOUNDATION = 4
BITS_FREECELL   = 6
BITS_COL_LEN    = 3

OFFSET_FOUNDATION = 0
OFFSET_FREECELLS  = 16
OFFSET_COL_LENS   = 40
OFFSET_CARDS      = 64

# ────────────────────
# Card encode / decode
# ────────────────────

def card_to_id(card) -> int:
    """(suit_str, rank_int) → int [0, 51]"""
    suit, rank = card
    return SUIT_IDX[suit] * 13 + (rank - 1)

def id_to_card(cid: int):
    """int [0, 51] → (suit_str, rank_int)"""
    return (SUITS[cid // 13], cid % 13 + 1)

def encode_state(state) -> int:
    key = 0

    # ── foundations ──────────────────────────
    for i, val in enumerate(state["foundations"]):
        key |= (val & 0xF) << (OFFSET_FOUNDATION + i * BITS_FOUNDATION)

    # ── freecells (sorted canonical) ─────────
    fc_ids = sorted(
        cid if cid != EMPTY else EMPTY_CARD
        for cid in state["freecells"]
    )
    for i, cid in enumerate(fc_ids):
        key |= (cid & 0x3F) << (OFFSET_FREECELLS + i * BITS_FREECELL)

    # ── cascades: non-empty trước, empty sau ─
    cascades = state["cascades"]
    nonempty = [col for col in cascades if col]
    cols = nonempty + [()] * (8 - len(nonempty))

    for col_idx, col in enumerate(cols):
        length = len(col)
        key |= (length & 0x7) << (OFFSET_COL_LENS + col_idx * BITS_COL_LEN)

        base = OFFSET_CARDS + col_idx * MAX_CARDS_PER_COL * BITS_PER_CARD
        for row, cid in enumerate(col):
            key |= (cid & 0x3F) << (base + row * BITS_PER_CARD)

    return key

def state_key(state) -> tuple:
    fc = tuple(sorted(state["freecells"]))
    cols = state["cascades"]
    nonempty = tuple(c for c in cols if c)
    normalized = nonempty + ((),) * (8 - len(nonempty))
    return (normalized, fc, state["foundations"])

def decode_state(key: int):
    """integer key → state dict (int-based).  Chỉ dùng debug."""
    foundations = tuple(
        (key >> (OFFSET_FOUNDATION + i * BITS_FOUNDATION)) & 0xF
        for i in range(4)
    )

    freecells = []
    for i in range(4):
        raw = (key >> (OFFSET_FREECELLS + i * BITS_FREECELL)) & 0x3F
        freecells.append(EMPTY if raw == EMPTY_CARD else raw)

    cascades = []
    for col_idx in range(8):
        length = (key >> (OFFSET_COL_LENS + col_idx * BITS_COL_LEN)) & 0x7
        col = []
        for row in range(length):
            bit_pos = OFFSET_CARDS + (col_idx * MAX_CARDS_PER_COL + row) * BITS_PER_CARD
            col.append((key >> bit_pos) & 0x3F)
        cascades.append(tuple(col))

    return {
        "foundations": foundations,
        "freecells":   tuple(freecells),
        "cascades":    tuple(cascades),
    }


# ────────────────────────────────
# Pruning: Auto-move to foundation
# ────────────────────────────────

def _is_safe_to_auto_move(cid: int, foundations) -> bool:
    """
    An toàn để tự động đẩy lên foundation khi tất cả lá
    ngược màu có rank = rank-1 đã ở trên foundation.

    H=0, D=1 → đỏ  |  C=2, S=3 → đen
    """
    rank = cid % 13 + 1
    if rank == 1:
        return True

    suit = cid // 13
    if suit < 2:                                   # đỏ -> cần lá đen
        min_opp = min(foundations[2], foundations[3])
    else:                                          # đen -> cần lá đỏ
        min_opp = min(foundations[0], foundations[1])

    return min_opp >= rank - 1


def apply_safe_auto_moves(state_parent) -> tuple:
    """
    Áp dụng tất cả safe auto-moves liên tục.
    Làm việc trực tiếp với int, không tạo object mới không cần thiết.
    """
    # Shallow-copy ra list để mutate
    foundations = list(state_parent["foundations"])
    freecells   = list(state_parent["freecells"])
    cascades    = list(state_parent["cascades"])

    auto_moves = []
    changed = True

    while changed:
        changed = False

        # Cascade → Foundation
        for i, col in enumerate(cascades):
            if not col:
                continue
            cid  = col[-1]
            suit = cid // 13
            rank = cid % 13 + 1
            if foundations[suit] == rank - 1 and _is_safe_to_auto_move(cid, foundations):
                cascades[i] = col[:-1]
                foundations[suit] += 1
                auto_moves.append(("cascade_to_foundation", i))
                changed = True

        # Freecell → Foundation
        for i, cid in enumerate(freecells):
            if cid == EMPTY:
                continue
            suit = cid // 13
            rank = cid % 13 + 1
            if foundations[suit] == rank - 1 and _is_safe_to_auto_move(cid, foundations):
                freecells[i] = EMPTY
                foundations[suit] += 1
                auto_moves.append(("freecell_to_foundation", i))
                changed = True

    new_state = {
        "foundations": tuple(foundations),
        "freecells":   tuple(freecells),
        "cascades":    tuple(cascades),
    }
    return new_state, auto_moves


# ───────────────────────────────────
# Pruning: Dominance filter cho moves
# ───────────────────────────────────

def filter_dominated_moves(moves, state) -> list:
    freecells   = state["freecells"]
    cascades    = state["cascades"]
    foundations = state["foundations"]

    safe_fnd = []
    for m in moves:
        if "foundation" not in m[0]:
            continue
        cid = cascades[m[1]][-1] if m[0] == "cascade_to_foundation" \
              else freecells[m[1]]
        if _is_safe_to_auto_move(cid, foundations):
            safe_fnd.append(m)
    if safe_fnd:
        return safe_fnd

    first_empty_fc  = next((i for i, c in enumerate(freecells) if c == EMPTY), None)
    empty_col_idxs  = [i for i, col in enumerate(cascades) if not col]
    first_empty_col = empty_col_idxs[0] if empty_col_idxs else None

    cards_with_real_cascade: set[int] = set()
    cards_with_any_cascade:  set[int] = set()
    for m in moves:
        if m[0] != "cascade_to_cascade":
            continue
        col = cascades[m[1]]
        if not col:
            continue
        cid = col[-1]
        cards_with_any_cascade.add(cid)
        if cascades[m[2]]:
            cards_with_real_cascade.add(cid)

    filtered:  list  = []
    seen_c2f:  set   = set()
    seen_f2c:  set   = set()
    seen_f2e:  bool  = False
    seen_c2e:  set   = set()

    for move in moves:
        mtype = move[0]

        if mtype == "cascade_to_freecell":
            col_idx = move[1]
            col = cascades[col_idx]
            if not col or first_empty_fc is None:
                continue
            cid = col[-1]

            if cid in cards_with_real_cascade:
                continue
            if col_idx in seen_c2f:
                continue

            seen_c2f.add(col_idx)
            filtered.append(("cascade_to_freecell", col_idx, first_empty_fc))
            continue

        # ── freecell→cascade ─────────────────────────────────────────────────
        if mtype == "freecell_to_cascade":
            fc_idx  = move[1]
            dst_col = move[2]
            cid     = freecells[fc_idx]
            if cid == EMPTY:
                continue

            if not cascades[dst_col]:              # empty dest
                if seen_f2e:                       # [R5]
                    continue
                best = max(
                    (c for c in freecells if c != EMPTY),
                    key=lambda c: c % 13 + 1       # rank cao nhất
                )
                if cid != best:
                    continue
                seen_f2e = True
                filtered.append(("freecell_to_cascade", fc_idx, first_empty_col))
                continue
            else:
                key = (cid, dst_col)               # [R3] dedup non-empty
                if key in seen_f2c:
                    continue
                seen_f2c.add(key)

            filtered.append(move)
            continue

        # ── cascade→cascade ──────────────────────────────────────────────────
        if mtype == "cascade_to_cascade":
            src_col = move[1]
            dst_col = move[2]
            col = cascades[src_col]
            if not col:
                continue
            cid = col[-1]

            if not cascades[dst_col]:
                if cid in cards_with_real_cascade:
                    continue
                if src_col in seen_c2e:
                    continue
                seen_c2e.add(src_col)
                filtered.append(("cascade_to_cascade", src_col, first_empty_col))
                continue

        filtered.append(move)

    return filtered if filtered else moves