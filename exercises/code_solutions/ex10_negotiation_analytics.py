def generate_analytics_report(history: list[dict], listing_price: float) -> None:
    buyer_offers = [(e["round"], e["price"]) for e in history if e.get("agent") == "buyer" and e.get("price")]
    seller_counters = [(e["round"], e["price"]) for e in history if e.get("agent") == "seller" and e.get("price")]

    all_prices = [price for _, price in buyer_offers + seller_counters]
    if not all_prices:
        print("No price history available")
        return

    min_price = min(all_prices)
    max_price = max(all_prices + [listing_price])

    print("NEGOTIATION ANALYTICS")
    print("=" * 32)
    print("CONVERGENCE CHART")
    print(f"Listing: ${listing_price:,.0f}")

    for round_num in sorted({r for r, _ in buyer_offers + seller_counters}):
        buyer_price = next((p for r, p in buyer_offers if r == round_num), None)
        seller_price = next((p for r, p in seller_counters if r == round_num), None)
        print(f"Round {round_num}: buyer={buyer_price} seller={seller_price}")

    print(f"Range: ${min_price:,.0f} to ${max_price:,.0f}")


if __name__ == "__main__":
    sample_history = [
        {"round": 1, "agent": "buyer", "price": 425000},
        {"round": 1, "agent": "seller", "price": 477000},
        {"round": 2, "agent": "buyer", "price": 438000},
        {"round": 2, "agent": "seller", "price": 465000},
        {"round": 3, "agent": "buyer", "price": 449000},
        {"round": 3, "agent": "seller", "price": 449000},
    ]
    generate_analytics_report(sample_history, listing_price=485000)
