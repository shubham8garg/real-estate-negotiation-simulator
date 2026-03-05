LISTING_PRICE = 485_000
MINIMUM_PRICE = 445_000


def anchoring_counter(round_num: int) -> int:
    schedule = {
        1: 495_000,
        2: 482_000,
        3: 470_000,
        4: 458_000,
        5: 449_000,
    }
    return max(MINIMUM_PRICE, schedule.get(round_num, MINIMUM_PRICE))


if __name__ == "__main__":
    print("Anchoring strategy counters by round:")
    for round_num in range(1, 6):
        counter = anchoring_counter(round_num)
        print(f"Round {round_num}: ${counter:,.0f}")
    print(f"\nListing price: ${LISTING_PRICE:,.0f}")
    print(f"Absolute floor: ${MINIMUM_PRICE:,.0f}")
