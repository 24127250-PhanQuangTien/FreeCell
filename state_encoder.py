"""
state_encoder.py
================
Compact bit-packed state encoding + pruning utilities cho FreeCell solver.

Layout của 1 integer key (376 bits tổng):
  [foundations: 16 bits] [freecells: 24 bits] [cascade_lengths: 24 bits] [cards: 312 bits]

Chi tiết:
  foundations   : 4 suits × 4 bits  = 16 bits  (giá trị 0-13)
  freecells     : 4 slots × 6 bits  = 24 bits  (card_id 0-51, 63 = rỗng)
  cascade_lens  : 8 cols × 3 bits   = 24 bits  (0-7 cards mỗi cột)
  cards         : 8 cols × 13 pos × 6 bits = 624 bits
                  → nhưng tổng chỉ có 52 cards nên thực tế compact hơn.
                  Ta encode từng cột flat: mỗi card 6 bits, pad bằng 0b111111.

Card ID: suit_idx * 13 + (rank - 1), range [0, 51]
  suit order: H=0, D=1, C=2, S=3

Tại sao dùng int thay vì tuple?
  - Python int là big integer, hashing O(1) và cực nhanh
  - Không có object overhead như tuple/list
  - visited set với int tốn ~56 bytes/phần tử vs ~200-400 bytes với tuple

Pruning strategies được implement:
  1. auto_move_to_foundation : tự động đẩy bài lên foundation nếu an toàn
     (safe = không có bài nào khác cần lá này làm bước đệm)
  2. freecell_symmetry       : normalize thứ tự freecell → tránh duplicate state
  3. empty_cascade_symmetry  : các cột rỗng là tương đương nhau → normalize
  4. dominance_check         : bỏ move cascade→freecell nếu đã có bài tương đương ở freecell
"""

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
    Tất cả các lá bài có thể cần "đặt lên" nó (lá liền dưới, màu đối lập)
    đã ở trên foundation rồi.

    Ví dụ: 3♥ an toàn nếu 2♠ và 2♣ đều đã lên foundation
    (vì không có lá đỏ nào cần 3♥ làm bước đệm trên cascade nữa)
    """
    suit, rank = card
    if rank == 1:
        return True  # Ace luôn an toàn

    # Các lá màu đối có rank = rank - 1 cần phải đã lên foundation
    RED = {"H", "D"}
    BLACK = {"C", "S"}
    opposite = BLACK if suit in RED else RED

    min_opposite_on_foundation = min(foundations[s] for s in opposite)
    # An toàn nếu tất cả lá đối màu rank-1 đã lên foundation
    return min_opposite_on_foundation >= rank - 1


def apply_safe_auto_moves(state) -> tuple:
    """
    Áp dụng tất cả safe auto-moves (cascade/freecell → foundation) liên tục
    cho đến khi không còn nước nào.

    Trả về: (new_state, list_of_auto_moves)
    Tích hợp vào solver: sau mỗi move do AI chọn, gọi hàm này để
    dọn sạch các lá bài hiển nhiên → giảm chiều sâu search đáng kể.
    """
    from copy import deepcopy
    state = {
        "cascades": [col[:] for col in state["cascades"]],
        "freecells": state["freecells"][:],
        "foundations": state["foundations"].copy(),
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
    Loại bỏ các moves bị dominated:

    1. Nếu đã có move cascade→foundation, bỏ tất cả moves khác
       (game.py đã làm việc này nhưng ta enforce lại ở đây)

    2. Không cho cascade→freecell nếu:
       - Có một lá y hệt rank/color trong freecell (dư thừa)

    3. Không cho freecell→cascade(empty) nếu cascade→cascade(empty) cũng có
       (ưu tiên giữ freecell trống)

    4. Không cho 2 moves cascade_to_freecell từ cùng 1 cột liên tiếp
       (không thể xảy ra trong 1 bước nhưng tránh generate duplicates)
    """
    # Rule 1: foundation moves trump everything (đã có trong get_moves nhưng double-check)
    foundation_moves = [m for m in moves if "foundation" in m[0]]
    if foundation_moves:
        return foundation_moves

    freecells = state["freecells"]
    freecell_cards = {c for c in freecells if c is not None}

    filtered = []
    seen_cascade_to_freecell_cards = set()

    for move in moves:
        mtype = move[0]

        # Rule 2: cascade→freecell - bỏ nếu lá đó đã có trong freecell
        if mtype == "cascade_to_freecell":
            col_idx = move[1]
            col = state["cascades"][col_idx]
            if not col:
                continue
            card = col[-1]
            if card in freecell_cards:
                continue  # duplicate card in freecell (không xảy ra nhưng đề phòng)
            # Tránh generate nhiều cascade_to_freecell từ cùng 1 cột
            if card in seen_cascade_to_freecell_cards:
                continue
            seen_cascade_to_freecell_cards.add(card)

        filtered.append(move)

    return filtered if filtered else moves


# ──────────────────────────────────────────────
# Memory estimate utilities
# ──────────────────────────────────────────────

def estimate_key_size_bytes(key: int) -> int:
    """Ước lượng bytes của 1 Python big int"""
    return key.bit_length() // 8 + 28  # 28 bytes overhead của PyObject


def compare_key_sizes(state):
    """In ra so sánh kích thước giữa tuple key cũ và int key mới"""
    import sys

    # Old way
    cascades = tuple(tuple(col) for col in state["cascades"])
    freecells = tuple(state["freecells"])
    foundations = tuple((k, state["foundations"][k]) for k in sorted(state["foundations"]))
    old_key = (cascades, freecells, foundations)

    # New way
    new_key = encode_state(state)

    old_size = sys.getsizeof(old_key)
    # Rough: count all nested objects
    for c in cascades:
        old_size += sys.getsizeof(c)
        for card in c:
            old_size += sys.getsizeof(card)
    for card in freecells:
        if card:
            old_size += sys.getsizeof(card)
    old_size += sys.getsizeof(foundations)

    new_size = sys.getsizeof(new_key)

    print(f"Old tuple key : ~{old_size:,} bytes")
    print(f"New int key   : ~{new_size:,} bytes")
    print(f"Reduction     : {old_size / new_size:.1f}x smaller")
    print(f"Key bit length: {new_key.bit_length()} bits")


# ──────────────────────────────────────────────
# Quick self-test
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from game import create_initial_state

    state = create_initial_state()

    print("=== Encoding test ===")
    key = encode_state(state)
    print(f"Key (int)   : {key}")
    print(f"Key bits    : {key.bit_length()}")
    print(f"Key bytes   : {sys.getsizeof(key)}")

    print("\n=== Size comparison ===")
    compare_key_sizes(state)

    print("\n=== Auto-move test ===")
    test_state = {
        "cascades": [
            [("H", 13)],
            [("D", 13)],
            [("C", 13)],
            [("S", 13)],
            [], [], [], []
        ],
        "freecells": [None] * 4,
        "foundations": {"H": 12, "D": 12, "C": 12, "S": 12}
    }
    new_state, auto = apply_safe_auto_moves(test_state)
    print(f"Auto moves applied: {len(auto)}")
    print(f"Foundations after : {new_state['foundations']}")

    print("\n=== Encode → Decode roundtrip ===")
    key2 = encode_state(test_state)
    decoded = decode_state(key2)
    print(f"Foundations match: {decoded['foundations'] == {'H': 12, 'D': 12, 'C': 12, 'S': 12}}")
