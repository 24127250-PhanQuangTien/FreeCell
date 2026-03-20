#file test truong hop easy 

from game import create_initial_state
from solver import bfs, dfs, ucs, astar
from optimized import bfs_optimized, ucs_optimized, dfs_optimized, astar_optimized

def create_easy_state():
    return {
        "cascades": [
            [("H", 13)],
            [("D", 13)],
            [("C", 13)],
            [("S", 13)],
            [], [], [], []
        ],
        "freecells": [None]*4,
        "foundations": {"H": 12, "D": 12, "C": 12, "S": 12}
    }


if __name__ == "__main__":
    state = create_easy_state()

    print("Initial:", state)

    result = astar_optimized(state)

    print("\nResult:")
    print("Time:", result["time"])
    print("Expanded:", result["expanded_nodes"])
    print("Length:", result["length"])
    print("Solution:", result["solution"])