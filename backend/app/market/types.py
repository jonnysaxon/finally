from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Quote:
    """The latest known state of one ticker. The unit pushed over SSE.

    Immutable: the cache replaces the whole Quote on every update rather than
    mutating fields, so a reader always sees a consistent snapshot.
    """

    ticker: str
    price: float
    prev_price: float
    open_price: float     # session-open baseline, set once on first tick (PLAN §13.2)
    timestamp: float      # epoch seconds

    @property
    def change(self) -> float:
        return self.price - self.open_price

    @property
    def change_pct(self) -> float:
        return (self.price - self.open_price) / self.open_price if self.open_price else 0.0

    @property
    def direction(self) -> str:
        """'up' | 'down' | 'flat' — drives the green/red flash animation."""
        if self.price > self.prev_price:
            return "up"
        if self.price < self.prev_price:
            return "down"
        return "flat"

    def to_event(self) -> dict:
        """JSON-serializable payload for an SSE `price` event."""
        return {
            "ticker": self.ticker,
            "price": round(self.price, 4),
            "prev_price": round(self.prev_price, 4),
            "open_price": round(self.open_price, 4),
            "change": round(self.change, 4),
            "change_pct": round(self.change_pct, 6),
            "direction": self.direction,
            "timestamp": self.timestamp,
        }
