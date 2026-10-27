"""Randomized match generator.

Builds rounds of foursomes (two partner pairs facing each other) spread
across the configured courts. Guarantees:

- Every player ends up with EXACTLY `matches_per_player` matches, no more,
  no less.
- A player never appears in two matches in the same round (so nobody is
  double-booked on two courts at once).
- Two players listed as an exception are never partnered together; repeat
  partnerships are minimized on a best-effort basis otherwise.

Raises ValueError if the request is infeasible (not enough players/courts,
or achieving the exact match count would need more rounds than allowed).
"""
import random


def generate_match_schedule(player_ids, num_courts, matches_per_player, exception_pairs, max_attempts=500, max_rounds=None):
    """Return a list of rounds; each round is a list of up to `num_courts`
    foursomes, where a foursome is
    ((team1_player1, team1_player2), (team2_player1, team2_player2))."""
    num_players = len(player_ids)
    if num_players < 4:
        raise ValueError("Need at least 4 players to schedule any matches.")
    if (num_players * matches_per_player) % 4 != 0:
        raise ValueError(
            f"{num_players} players x {matches_per_player} matches each does not split evenly "
            "into groups of 4. Adjust matches per player, or the number of players."
        )

    round_capacity = min(num_courts, num_players // 4)  # matches per round
    if round_capacity < 1:
        raise ValueError("Not enough courts for the number of players.")

    exceptions = {frozenset(pair) for pair in exception_pairs}
    history = {pid: set() for pid in player_ids}
    remaining = {pid: matches_per_player for pid in player_ids}

    schedule = []
    safety_cap = matches_per_player + num_players  # generous, finite bound
    while sum(remaining.values()) > 0:
        if max_rounds is not None and len(schedule) >= max_rounds:
            raise ValueError(
                f"Giving every player {matches_per_player} matches needs more than {max_rounds} "
                f"rounds with {num_courts} court(s). Add more courts or reduce matches per player."
            )
        if len(schedule) >= safety_cap:
            raise ValueError("Could not complete the schedule with these settings.")

        foursomes = _build_round(player_ids, round_capacity, remaining, history, exceptions, max_attempts)
        schedule.append(foursomes)
        for team1, team2 in foursomes:
            for pid in (*team1, *team2):
                remaining[pid] -= 1
            a, b = team1
            history[a].add(b)
            history[b].add(a)
            c, d = team2
            history[c].add(d)
            history[d].add(c)

    return schedule


def _build_round(player_ids, round_capacity, remaining, history, exceptions, max_attempts):
    # Players who still need matches, most-needy first (random tiebreak) so
    # nobody is permanently left behind and everyone finishes together.
    needing = [pid for pid in player_ids if remaining[pid] > 0]
    needing.sort(key=lambda pid: (-remaining[pid], random.random()))
    active_count = min(round_capacity * 4, (len(needing) // 4) * 4)
    active = needing[:active_count]

    for _ in range(max_attempts):
        pairs = _pair_players(active, history, exceptions, allow_repeat=False)
        if pairs is not None:
            break
    else:
        # Fall back to allowing repeat partners so a schedule is always
        # produced; exceptions are still respected.
        pairs = _pair_players(active, history, exceptions, allow_repeat=True)
        if pairs is None:
            raise ValueError("Could not build a round that satisfies the exceptions.")

    random.shuffle(pairs)
    return [(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2)]


def _pair_players(pool, history, exceptions, allow_repeat):
    """Backtracking search that partners every player in `pool` into pairs."""
    if not pool:
        return []

    first, rest = pool[0], pool[1:]
    random.shuffle(rest)
    for i, candidate in enumerate(rest):
        if frozenset((first, candidate)) in exceptions:
            continue
        if not allow_repeat and candidate in history[first]:
            continue
        remaining = rest[:i] + rest[i + 1:]
        sub = _pair_players(remaining, history, exceptions, allow_repeat)
        if sub is not None:
            return [(first, candidate)] + sub
    return None
