SUPPORTED_CURRENCIES = {"TRY", "USD", "EUR", "GBP", "JPY", "CHF"}
HIGH_VALUE_THRESHOLD = 10_000
ULTRA_HIGH_THRESHOLD = 100_000


class PaymentProcessor:
    """Coordinates payment processing."""

    def __init__(self, card_validator, amount_validator):
        self._card_validator = card_validator
        self._amount_validator = amount_validator

    def process(self, amount: float, currency: str,
                card: str, expiry: str,
                cvv: str, user_id: str) -> bool:
        if amount <= 0 or amount > 1_000_000:
            return False
        if currency not in SUPPORTED_CURRENCIES:
            return False
        if not card or len(card) != 16:
            return False
        return True


class OrderService:
    """Manages order processing."""

    def __init__(self, processor: PaymentProcessor):
        self._processor = processor

    def place(self, amount: float, currency: str,
              card: str, expiry: str,
              cvv: str, user_id: str) -> bool:
        return self._processor.process(
            amount, currency, card, expiry, cvv, user_id)


class RefundService:
    """Manages refund processing."""

    def __init__(self, processor: PaymentProcessor):
        self._processor = processor

    def refund(self, amount: float, user_id: str) -> bool:
        return self._processor.process(
            amount, "TRY",
            "0000000000000000", "01/30", "000",
            user_id)


class PaymentProcessor:
    """Simplified payment processor."""

    def process(self, amount: float) -> bool:
        return amount > 0
