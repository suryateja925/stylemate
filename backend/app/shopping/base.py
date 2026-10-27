from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote_plus


@dataclass(frozen=True)
class ShoppingLink:
    provider: str
    url: str
    query: str
    live_catalog: bool = False
    price: float | None = None
    delivery_estimate: str | None = None
    source_last_updated: datetime | None = None
    disclosure: str = "This is a platform search link. Live catalogue, price, stock, and delivery were not verified by StyleMate."


class ShoppingProvider:
    name = "provider"

    def search_link(self, query: str) -> ShoppingLink:
        raise NotImplementedError


class AmazonIndiaProvider(ShoppingProvider):
    name = "amazon"

    def search_link(self, query: str) -> ShoppingLink:
        return ShoppingLink(self.name, f"https://www.amazon.in/s?k={quote_plus(query)}", query)


class FlipkartProvider(ShoppingProvider):
    name = "flipkart"

    def search_link(self, query: str) -> ShoppingLink:
        return ShoppingLink(self.name, f"https://www.flipkart.com/search?q={quote_plus(query)}", query)


class MeeshoProvider(ShoppingProvider):
    name = "meesho"

    def search_link(self, query: str) -> ShoppingLink:
        return ShoppingLink(self.name, f"https://www.meesho.com/search?q={quote_plus(query)}", query)


PROVIDERS = {
    "amazon": AmazonIndiaProvider(),
    "flipkart": FlipkartProvider(),
    "meesho": MeeshoProvider(),
}
