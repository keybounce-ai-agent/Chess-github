# Achronal Chess

A Python rules-engine prototype for the design described in `achronal-chess-design-v0.2.md`.

## Structure

- `src/achronal_chess/` — engine package
- `tests/` — smoke tests for the public API

## Install

```bash
python -m pip install -e .
```

## Example

```python
from achronal_chess import Game, BalanceConfig

config = BalanceConfig()
game = Game(config)
print(game.current_player)
print(game.players["white"].energy)
```
