# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

SUITS = ["H", "D", "C", "S"]          # index 0-3
SUIT_IDX = {s: i for i, s in enumerate(SUITS)}
EMPTY_CARD = 0b111111                  # 63 — sentinel cho slot rỗng (6 bits)
MAX_CARDS_PER_COL = 13                 # tối đa 13 lá / cột (thực tế 7)

BITS_PER_CARD   = 6    # 2^6 = 64 > 52 card ids + sentinel
BITS_FOUNDATION = 4    # 0-13
BITS_FREECELL   = 6    # card id hoặc 63=empty
BITS_COL_LEN    = 3    # 0-7

# Offsets trong integer (từ bit 0 = LSB)
#   foundation  : bits [0, 16)
#   freecells   : bits [16, 40)
#   col_lens    : bits [40, 64)
#   cards       : bits [64, 64 + 8*13*6) = [64, 688)
OFFSET_FOUNDATION = 0
OFFSET_FREECELLS  = 16
OFFSET_COL_LENS   = 40
OFFSET_CARDS      = 64
BITS_CARDS_TOTAL  = 8 * MAX_CARDS_PER_COL * BITS_PER_CARD  # 624 bits

# ──────────────────────────────────────────────
# Card encode / decode
# ──────────────────────────────────────────────

def card_to_id(card) -> int:
    """(suit_str, rank_int) → int [0, 51]"""
    suit, rank = card
    return SUIT_IDX[suit] * 13 + (rank - 1)

def id_to_card(cid: int):
    """int [0, 51] → (suit_str, rank_int)"""
    return (SUITS[cid // 13], cid % 13 + 1)

# ──────────────────────────────────────────────
# Encode state → compact integer key
# ──────────────────────────────────────────────

def encode_state(state) -> int:
    key = 0

    # ── foundations ───────────────────────
    fnd = state["foundations"]
    for i, suit in enumerate(SUITS):
        key |= (fnd[suit] & 0xF) << (OFFSET_FOUNDATION + i * BITS_FOUNDATION)

    # ── freecells (sorted canonical) ──────
    fc_ids = sorted(
        card_to_id(c) if c is not None else EMPTY_CARD
        for c in state["freecells"]
    )
    for i, cid in enumerate(fc_ids):
        key |= (cid & 0x3F) << (OFFSET_FREECELLS + i * BITS_FREECELL)

    # ── cascades (OPTIMIZED) ──────────────
    cascades = state["cascades"]

    # ⚠️ KHÔNG sort full cascades nữa
    # chỉ gom non-empty trước, empty sau
    nonempty = [col for col in cascades if col]
    empty_count = 8 - len(nonempty)

    cols = nonempty + [[]] * empty_count

    for col_idx, col in enumerate(cols):
        length = len(col)
        key |= (length & 0x7) << (OFFSET_COL_LENS + col_idx * BITS_COL_LEN)

        base = OFFSET_CARDS + col_idx * MAX_CARDS_PER_COL * BITS_PER_CARD

        for row, card in enumerate(col):
            cid = card_to_id(card)
            key |= (cid & 0x3F) << (base + row * BITS_PER_CARD)

    return key


# ──────────────────────────────────────────────
# Decode (dùng cho debug / reconstruct)
# ──────────────────────────────────────────────

def decode_state(key: int, original_state=None):
    """
    Decode integer key → state dict.
    Lưu ý: do normalize, thứ tự freecell và cascade có thể khác original.
    Chỉ dùng để debug.
    """
    fnd = {}
    for i, suit in enumerate(SUITS):
        val = (key >> (OFFSET_FOUNDATION + i * BITS_FOUNDATION)) & 0xF
        fnd[suit] = val

    fc = []
    for i in range(4):
        cid = (key >> (OFFSET_FREECELLS + i * BITS_FREECELL)) & 0x3F
        fc.append(None if cid == EMPTY_CARD else id_to_card(cid))

    cascades = []
    for col_idx in range(8):
        length = (key >> (OFFSET_COL_LENS + col_idx * BITS_COL_LEN)) & 0x7
        col = []
        for row in range(length):
            bit_pos = OFFSET_CARDS + (col_idx * MAX_CARDS_PER_COL + row) * BITS_PER_CARD
            cid = (key >> bit_pos) & 0x3F
            col.append(id_to_card(cid))
        cascades.append(col)

    return {"foundations": fnd, "freecells": fc, "cascades": cascades}


# ──────────────────────────────────────────────
# Pruning: Auto-move to foundation (safe)
# ──────────────────────────────────────────────

def _is_safe_to_auto_move(card, foundations) -> bool:
    """
    Một lá bài an toàn để tự động đẩy lên foundation nếu:
    Tất cả các lá bài có thể cần "đặt lên" nó đã ở trên foundation rồi.
    """
    suit, rank = card
    if rank == 1:
        return True  # Ace luôn an toàn

    # Các lá màu khác có rank = rank - 1 cần phải đã lên foundation
    RED = {"H", "D"}
    BLACK = {"C", "S"}
    opposite = BLACK if suit in RED else RED

    min_opposite_on_foundation = min(foundations[s] for s in opposite)
    # An toàn nếu tất cả lá khác màu rank-1 đã lên foundation
    return min_opposite_on_foundation >= rank - 1


def apply_safe_auto_moves(state_parent) -> tuple:
    """
    Áp dụng tất cả safe auto-moves (cascade/freecell → foundation) liên tục
    cho đến khi không còn nước nào.

    Return: (new_state, list_of_auto_moves)
    """
    state = {
        "cascades": [col[:] for col in state_parent["cascades"]],
        "freecells": state_parent["freecells"][:],
        "foundations": state_parent["foundations"].copy(),
    }
    auto_moves = []
    changed = True
    while changed:
        changed = False

        # Cascade → Foundation
        for i, col in enumerate(state["cascades"]):
            if not col:
                continue
            card = col[-1]
            suit, rank = card
            if state["foundations"][suit] == rank - 1:
                if _is_safe_to_auto_move(card, state["foundations"]):
                    col.pop()
                    state["foundations"][suit] += 1
                    auto_moves.append(("cascade_to_foundation", i))
                    changed = True

        # Freecell → Foundation
        for i, card in enumerate(state["freecells"]):
            if card is None:
                continue
            suit, rank = card
            if state["foundations"][suit] == rank - 1:
                if _is_safe_to_auto_move(card, state["foundations"]):
                    state["freecells"][i] = None
                    state["foundations"][suit] += 1
                    auto_moves.append(("freecell_to_foundation", i))
                    changed = True

    return state, auto_moves


# ──────────────────────────────────────────────
# Pruning: Dominance filter cho moves
# ──────────────────────────────────────────────

def filter_dominated_moves(moves, state) -> list:
    freecells   = state["freecells"]
    cascades    = state["cascades"]
    foundations = state["foundations"]
 
    # ── [R1] Safe foundation priority ────────────────────────────────────────
    safe_fnd = []
    for m in moves:
        if "foundation" not in m[0]:
            continue
        card = cascades[m[1]][-1] if m[0] == "cascade_to_foundation" \
               else freecells[m[1]]
        if _is_safe_to_auto_move(card, foundations):
            safe_fnd.append(m)
    if safe_fnd:
        return safe_fnd
 
    # ── Precompute context ────────────────────────────────────────────────────
    first_empty_fc = next((i for i, c in enumerate(freecells) if c is None), None)
    empty_fc_count = sum(1 for c in freecells if c is None)
 
    empty_col_idxs  = [i for i, col in enumerate(cascades) if not col]
    first_empty_col = empty_col_idxs[0] if empty_col_idxs else None
 
    # Phân loại cascade→cascade moves
    cards_with_real_cascade = set()   # lá có dest non-empty (stack thật)
    cards_with_any_cascade  = set()   # lá có bất kỳ cascade→cascade nào
    for m in moves:
        if m[0] != "cascade_to_cascade":
            continue
        col = cascades[m[1]]
        if not col:
            continue
        card = col[-1]
        cards_with_any_cascade.add(card)
        if cascades[m[2]]:   # non-empty dest
            cards_with_real_cascade.add(card)
 
    # ── Filter loop ───────────────────────────────────────────────────────────
    filtered  = []
    seen_c2f  = set()    # source col idx đã sinh cascade→freecell
    seen_f2c  = set()    # (card, dst_col) đã sinh freecell→cascade non-empty
    seen_f2e  = False    # đã sinh freecell→empty move chưa
    seen_c2e  = set()    # source col đã sinh cascade→empty
 
    for move in moves:
        mtype = move[0]
 
        # ── cascade→freecell ─────────────────────────────────────────────────
        if mtype == "cascade_to_freecell":
            col_idx = move[1]
            col = cascades[col_idx]
            if not col or first_empty_fc is None:
                continue
            card = col[-1]
 
            # [R4] có stack thật → không cất freecell
            if card in cards_with_real_cascade:
                continue
 
            # [R2] dedup source col
            if col_idx in seen_c2f:
                continue
 
            # # [R8] freecell cạn + lá hoàn toàn vô dụng hiện tại → skip
            # if empty_fc_count == 1 and card not in cards_with_any_cascade:
            #     suit, rank = card
            #     steps_to_fnd = rank - foundations[suit]   # số bước để lên fnd
            #     if steps_to_fnd > 2:
            #         continue   # Lá này chiếm ô freecell cuối mà không có ích gì
 
            seen_c2f.add(col_idx)
            filtered.append(("cascade_to_freecell", col_idx, first_empty_fc))
            continue
 
        # ── freecell→cascade ─────────────────────────────────────────────────
        if mtype == "freecell_to_cascade":
            fc_idx  = move[1]
            dst_col = move[2]
            card    = freecells[fc_idx]
            if card is None:
                continue
 
            if not cascades[dst_col]:   # empty dest
                # [R5] chỉ giữ 1 move freecell→empty: lá rank cao nhất
                if seen_f2e:
                    continue
                best = max(
                    (c for c in freecells if c is not None),
                    key=lambda c: c[1]   # rank cao nhất
                )
                if card != best:
                    continue
                seen_f2e = True
                # Normalize dest → first empty col
                filtered.append(("freecell_to_cascade", fc_idx, first_empty_col))
                continue
            else:
                # [R3] dedup (card, dest) non-empty
                key = (card, dst_col)
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
            card = col[-1]
 
            if not cascades[dst_col]:   # empty dest
                # [R7] đã có stack thật → không waste empty slot
                if card in cards_with_real_cascade:
                    continue
 
                # [R6] dedup source col → normalize về first_empty_col
                if src_col in seen_c2e:
                    continue
                seen_c2e.add(src_col)
                filtered.append(("cascade_to_cascade", src_col, first_empty_col))
                continue
 
        filtered.append(move)
 
    return filtered if filtered else moves
