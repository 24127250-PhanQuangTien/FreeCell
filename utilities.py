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
    """
    Encode toàn bộ game state thành 1 Python big integer.
    Đây là hàm thay thế cho state_to_tuple() cũ.

    Ưu điểm:
      - Hashing O(length_in_digits) nhưng thực tế rất nhanh
      - Tốn ~56 bytes/entry trong set thay vì 200-400 bytes của nested tuple
    """
    key = 0

    # --- foundations (16 bits) ---
    fnd = state["foundations"]
    for i, suit in enumerate(SUITS):
        key |= (fnd[suit] & 0xF) << (OFFSET_FOUNDATION + i * BITS_FOUNDATION)

    # --- freecells (24 bits) ---
    # Normalize: sort freecells để {A,None,B,None} ≡ {B,None,A,None}
    # Dùng canonical form: None → 63, cards sort ascending
    fc = state["freecells"]
    fc_ids = sorted(
        card_to_id(c) if c is not None else EMPTY_CARD
        for c in fc
    )
    for i, cid in enumerate(fc_ids):
        key |= (cid & 0x3F) << (OFFSET_FREECELLS + i * BITS_FREECELL)

    # --- cascade lengths + cards (24 + 624 bits) ---
    # Normalize: các cột rỗng là equivalent → đặt cuối
    cascades = state["cascades"]
    # Sort: non-empty trước, empty sau; non-empty sort by content để canonical
    nonempty = [col for col in cascades if col]
    empty_count = 8 - len(nonempty)
    # Sort non-empty cascades để đổi chỗ 2 cột rỗng không tạo state mới
    nonempty_sorted = sorted(nonempty, key=lambda col: tuple(card_to_id(c) for c in col))
    cols_normalized = nonempty_sorted + [[]] * empty_count

    for col_idx, col in enumerate(cols_normalized):
        length = len(col)
        key |= (length & 0x7) << (OFFSET_COL_LENS + col_idx * BITS_COL_LEN)

        for row, card in enumerate(col):
            cid = card_to_id(card)
            bit_pos = OFFSET_CARDS + (col_idx * MAX_CARDS_PER_COL + row) * BITS_PER_CARD
            key |= (cid & 0x3F) << bit_pos

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
    """
    Loại bỏ các moves bị dominated

    1. Nếu đã có move cascade/freecell → foundation an toàn, bỏ tất cả move
    2. cascade_to_freecell: xem tất cả ô freecell rỗng là TƯƠNG ĐƯƠNG nhau.
    3. freecell_to_cascade: tương tự, mỗi lá trong freecell chỉ cần 1 move
       per cột đích (không trùng lặp do slot khác nhau).
    5. Không cho cascade→freecell nếu có cascade→cascade hợp lệ cho lá đó
       (ưu tiên sắp xếp hơn là cất vào freecell).
    """
    # Rule 1: foundation moves
    foundation_moves = [m for m in moves if "foundation" in m[0]]
    
    safe_foundation_moves = []
    for m in foundation_moves:
        if m[0] == "cascade_to_foundation":
            card = state["cascades"][m[1]][-1]
        else:  # freecell_to_foundation
            card = state["freecells"][m[1]]
        if _is_safe_to_auto_move(card, state["foundations"]):
            safe_foundation_moves.append(m)
    
    # Chỉ chặn khi có SAFE foundation move
    if safe_foundation_moves:
        return safe_foundation_moves

    freecells = state["freecells"]
    cascades  = state["cascades"]

    # Tìm ô freecell rỗng đầu tiên (đại diện cho tất cả ô rỗng)
    first_empty_fc = next((i for i, c in enumerate(freecells) if c is None), None)

    # Các lá cascade có move cascade→cascade hợp lệ
    cards_with_cascade_move = set()
    for m in moves:
        if m[0] == "cascade_to_cascade":
            col = cascades[m[1]]
            if col:
                cards_with_cascade_move.add(col[-1])

    filtered = []
    seen_cascade_to_freecell = set()   # set of (col_idx) đã thêm
    seen_freecell_to_cascade  = set()   # set of (fc_card, dest_col) đã thêm

    for move in moves:
        mtype = move[0]

        if mtype == "cascade_to_freecell":
            col_idx = move[1]
            col = cascades[col_idx]
            if not col:
                continue
            card = col[-1]
            # Rule 5: nếu lá này có thể đi cascade→cascade, đừng cất vào freecell
            if card in cards_with_cascade_move:
                continue
            # Rule 2: mỗi cột cascade chỉ sinh 1 move duy nhất vào freecell
            if col_idx in seen_cascade_to_freecell:
                continue
            if first_empty_fc is None:
                continue
            # Normalize: luôn dùng first_empty_fc làm slot đích
            seen_cascade_to_freecell.add(col_idx)
            filtered.append(("cascade_to_freecell", col_idx, first_empty_fc))
            continue

        if mtype == "freecell_to_cascade":
            fc_idx  = move[1]
            dst_col = move[2]
            card    = freecells[fc_idx]
            if card is None:
                continue
            # Rule 3: dedup (card, dest) — bất kể slot freecell nào
            key = (card, dst_col)
            if key in seen_freecell_to_cascade:
                continue
            seen_freecell_to_cascade.add(key)

        filtered.append(move)

    return filtered if filtered else moves
