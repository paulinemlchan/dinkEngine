"""Randomized match generator.

Builds, round by round, foursomes of players (two partner pairs facing each
other) spread across the configured courts, so that over the requested
number of rounds each player partners with as few repeat partners as
possible, while never pairing two players listed as an exception. Players
beyond what the courts can hold in a round sit out (byes), rotated fairly.
"""
import random


def generate_match_schedule(player_ids, num_courts, rounds, exception_pairs, max_attempts=500):
    """Return a list of `rounds` rounds; each round is a list of up to
    `num_courts` foursomes, where a foursome is
    ((team1_player1, team1_player2), (team2_player1, team2_player2))."""
    exceptions = {frozenset(pair) for pair in exception_pairs}
    history = {pid: set() for pid in player_ids}
    bye_count = {pid: 0 for pid in player_ids}

    schedule = []
    for _ in range(rounds):
        foursomes = _build_round(player_ids, num_courts, history, exceptions, bye_count, max_attempts)
        schedule.append(foursomes)
        for team1, team2 in foursomes:
            a, b = team1
            history[a].add(b)
            history[b].add(a)
            c, d = team2
            history[c].add(d)
            history[d].add(c)
    return schedule


def _build_round(player_ids, num_courts, history, exceptions, bye_count, max_attempts):
    capacity = num_courts * 4
    target = min(len(player_ids), capacity)
    target -= target % 4  # only full foursomes are scheduled

    for _ in range(max_attempts):
        foursomes = _attempt_round(player_ids, target, history, exceptions, bye_count, allow_repeat=False)
        if foursomes is not None:
            return foursomes
    # Fall back to allowing repeat partners so a schedule is always produced;
    # exceptions are still respected.
    foursomes = _attempt_round(player_ids, target, history, exceptions, bye_count, allow_repeat=True)
    if foursomes is None:
        raise ValueError("Could not build a round that satisfies the exceptions.")
    return foursomes


def _attempt_round(player_ids, target, history, exceptions, bye_count, allow_repeat):
    pool = list(player_ids)
    random.shuffle(pool)

    byes_needed = len(pool) - target
    byes = []
    for _ in range(byes_needed):
        min_byes = min(bye_count[p] for p in pool)
        candidates = [p for p in pool if bye_count[p] == min_byes]
        chosen = random.choice(candidates)
        byes.append(chosen)
        pool.remove(chosen)

    pairs = _pair_players(pool, history, exceptions, allow_repeat)
    if pairs is None:
        return None

    for p in byes:
        bye_count[p] += 1

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
