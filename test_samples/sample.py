"""Stok ve depo yönetimi için fiyatlandırma kuralları."""


class ElectronicsPricingRule:
    """Elektronik ürünler için sabit oran tablosuna dayalı fiyatlandırma."""

    RATES = {"EU": 0.95, "US": 1.0, "OTHER": 1.05}

    def calculate(self, quantity, region):
        rate = self.RATES.get(region, self.RATES["OTHER"])
        return quantity * rate


class FurniturePricingRule:
    """Mobilya ürünleri için bölgesel oran tablosu."""

    RATES = {"A": 0.9, "B": 0.95, "OTHER": 1.0}

    def calculate(self, quantity, zone):
        rate = self.RATES.get(zone, self.RATES["OTHER"])
        return quantity * rate


class GroceryPricingRule:
    """Gıda ürünleri için tedarikçi oran tablosu."""

    RATES = {"supplier_direct": 1.03, "OTHER": 1.0}

    def calculate(self, quantity, source):
        rate = self.RATES.get(source, self.RATES["OTHER"])
        return quantity * rate


class CodeAdjustment:
    """Ek indirim/zam kodlarını uygular."""

    ADJUSTMENTS = {"X1": 0.99, "X2": 0.98, "OTHER": 1.0}

    def apply(self, amount, code):
        rate = self.ADJUSTMENTS.get(code, self.ADJUSTMENTS["OTHER"])
        return amount * rate


class StockHandler:
    """Ürün tipine göre doğru fiyatlandırma kuralını uygular."""

    def __init__(self, electronics_rule, furniture_rule,
                 grocery_rule, code_adjustment):
        self.electronics_rule = electronics_rule
        self.furniture_rule = furniture_rule
        self.grocery_rule = grocery_rule
        self.code_adjustment = code_adjustment

    def calculate(self, product_type, quantity, region, code=None):
        amount = quantity
        if product_type == "electronics":
            amount = self.electronics_rule.calculate(quantity, region)
        if product_type == "furniture":
            amount = self.furniture_rule.calculate(quantity, region)
        if product_type == "grocery":
            amount = self.grocery_rule.calculate(quantity, region)
        return self.code_adjustment.apply(amount, code)

    def check(self, warehouse, quantity):
        return bool(warehouse) and quantity > 0


class WarehouseService:
    """Stok yenileme taleplerini yönetir."""

    def __init__(self, handler):
        self.handler = handler

    def restock(self, product_type, quantity, warehouse, region, code=None):
        if not self.handler.check(warehouse, quantity):
            return None
        return self.handler.calculate(product_type, quantity, region, code)


class ShipmentService:
    """Elektronik ürün gönderim maliyeti tahmini yapar."""

    def __init__(self, handler):
        self.handler = handler

    def estimate(self, quantity, region):
        return self.handler.calculate("electronics", quantity, region)