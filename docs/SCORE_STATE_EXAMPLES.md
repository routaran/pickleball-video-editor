# ScoreState Examples and Usage

This document provides examples of using the `ScoreState` class for pickleball scoring.

## Basic Initialization

### Singles Game
```python
from core import ScoreState

player_names = {
    "team1": ["Alice"],
    "team2": ["Bob"]
}

state = ScoreState("singles", "11", player_names)
print(state.get_score_string())  # "0-0"
```

### Doubles Game
```python
player_names = {
    "team1": ["Alice", "Charlie"],
    "team2": ["Bob", "Diana"]
}

state = ScoreState("doubles", "11", player_names)
print(state.get_score_string())  # "0-0-2" (starts with Server 2)
```

## Marking Rally Outcomes

### Server Wins
```python
# Server's team scores a point, server continues serving
state.server_wins()
print(state.get_score_string())  # Score increases by 1
```

### Receiver Wins

**Singles:**
```python
# Side-out: receiver becomes server, scores unchanged
state.receiver_wins()
server_info = state.get_server_info()
print(f"New server: {server_info.player_name}")
```

**Doubles:**
```python
# Server 1 loses → Switch to Server 2 (same team)
# Server 2 loses → Side-out to other team's Server 1
state.receiver_wins()
print(state.get_score_string())  # Shows new server number
```

## Score Progression Examples

### Singles Example: Rally-by-Rally

```python
state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})

# Rally 1: Alice serves, Alice wins
state.server_wins()
# Score: 1-0, Server: Alice

# Rally 2: Alice serves, Alice wins
state.server_wins()
# Score: 2-0, Server: Alice

# Rally 3: Alice serves, Bob wins (side-out)
state.receiver_wins()
# Score: 0-2, Server: Bob

# Rally 4: Bob serves, Bob wins
state.server_wins()
# Score: 1-2, Server: Bob
```

### Doubles Example: Rally-by-Rally

```python
state = ScoreState("doubles", "11", {
    "team1": ["Alice", "Charlie"],
    "team2": ["Bob", "Diana"]
})

# Start: 0-0-2, Server: Team 1, Server 2 (Charlie)

# Rally 1: Charlie serves, Receiver wins (immediate side-out at 0-0-2)
state.receiver_wins()
# Score: 0-0-1, Server: Team 2, Server 1 (Bob)

# Rally 2: Bob serves, Bob wins
state.server_wins()
# Score: 1-0-1, Server: Team 2, Server 1 (Bob)

# Rally 3: Bob serves, Bob wins again
state.server_wins()
# Score: 2-0-1, Server: Team 2, Server 1 (Bob)

# Rally 4: Bob serves, Receiver wins (switch to Server 2)
state.receiver_wins()
# Score: 2-0-2, Server: Team 2, Server 2 (Diana)

# Rally 5: Diana serves, Receiver wins (side-out)
state.receiver_wins()
# Score: 0-2-1, Server: Team 1, Server 1 (Alice)
```

## Win Condition Checking

```python
# Standard game (must win by 2)
is_over, winner = state.is_game_over()

if is_over:
    winner_name = player_names[f"team{winner + 1}"]
    print(f"Game over! Winner: {winner_name}")
```

## Manual Interventions

### Edit Score
```python
# Manually correct an incorrect score
state.set_score("7-5-1")  # Doubles
state.set_score("7-5")    # Singles
```

### Force Side-Out
```python
# Force a side-out without changing score
state.force_side_out()
```

## Undo Functionality

```python
# Save state before a rally
snapshot = state.save_snapshot()

# Mark some rallies
state.server_wins()
state.receiver_wins()

# Undo by restoring snapshot
state.restore_snapshot(snapshot)
```

## Session Persistence

```python
# Save current state
state_data = state.to_dict()

# Later: restore from saved data
restored_state = ScoreState.from_dict(state_data)
```

## Getting Server Information

```python
server_info = state.get_server_info()

print(f"Serving Team: {server_info.serving_team}")  # 0 or 1
print(f"Server Number: {server_info.server_number}")  # 1 or 2 (doubles), None (singles)
print(f"Player Name: {server_info.player_name}")
```

## Special Cases

### Doubles Game Start (0-0-2)

The first rally in doubles is special:
- Starts at 0-0-2 (Team 1, Server 2)
- First fault causes **immediate side-out** (no Server 1 attempt)
- This is the only time this happens

```python
state = ScoreState("doubles", "11", player_names)
print(state.get_score_string())  # "0-0-2"

state.receiver_wins()  # First fault
print(state.get_score_string())  # "0-0-1" (immediate side-out)
```

### Timed Games

```python
state = ScoreState("singles", "timed", player_names)

# Timed games never auto-detect game over
is_over, winner = state.is_game_over()
# Always returns (False, None)

# User must manually trigger game end via UI
```

## Error Handling

```python
# Invalid score format
try:
    state.set_score("invalid")
except ValueError as e:
    print(f"Error: {e}")

# Invalid server number
try:
    state.set_score("7-5-3")  # Server 3 doesn't exist
except ValueError as e:
    print(f"Error: {e}")
```

## Integration with Rally Manager

```python
from core import ScoreState, RallyManager

# Initialize both
state = ScoreState("doubles", "11", player_names)
rally_mgr = RallyManager(fps=60.0)

# Start rally
rally_mgr.start_rally(frame=1000)

# Get current score before ending rally
current_score = state.get_score_string()

# End rally (server wins)
rally = rally_mgr.end_rally(frame=2000, score=current_score, winner="server")

# Update score state
state.server_wins()

# Get new score for display
new_score = state.get_score_string()
print(f"Rally ended. Score: {new_score}")
```
