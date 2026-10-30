# Achronal Chess

A Python implementation of the Achronal Chess rules described in `achronal-chess-design-v0.2.md`.

This project is intentionally structured around the design document's architecture:

- `chess_core` for legal chess logic and board interpretation
- `timeline` for state history and wave mechanics
- `economy` for chrono-energy and transfer accounting
- `game` for turn order, freeze handling, and API surface

## Quick start

```bash
pip install -e .
python -m pytest
```

## Core objects

The engine exposes data classes aligned with the design document:

- `BalanceConfig`
- `Player`
- `BoardState`
- `Timeline`
- `Wave`
- `Mark`
- `ActionLog`
- `PresentMove`, `PastEdit`, `Respond`, `Pass`
- `Game`

The package is intentionally deterministic, JSON-serialisable, and operates with integer arithmetic in the economy layer.
