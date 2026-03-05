def check_negotiation_deadlock(
    buyer_offer: float,
    seller_counter: float,
    rounds_elapsed: int,
    max_rounds: int,
    buyer_budget: float,
) -> dict:
    gap = seller_counter - buyer_offer
    rounds_remaining = max_rounds - rounds_elapsed
    gap_percent = (gap / seller_counter * 100) if seller_counter else 0.0

    if gap <= 0:
        risk = "low"
        recommendation = "Agreement zone reached — consider accepting"
        action = "continue"
    elif seller_counter > buyer_budget:
        gap_to_budget = seller_counter - buyer_budget
        if gap_to_budget > 20_000 and rounds_remaining <= 1:
            risk = "certain"
            recommendation = "Seller unlikely to reach your budget in remaining rounds"
            action = "walk_away"
        elif gap_to_budget > 10_000:
            risk = "high"
            recommendation = f"Need ${gap_to_budget:,.0f} movement in {rounds_remaining} rounds"
            action = "make_concession" if rounds_remaining > 1 else "walk_away"
        else:
            risk = "medium"
            recommendation = "Close to budget range — one more round may resolve this"
            action = "continue"
    elif rounds_remaining <= 0:
        risk = "certain"
        recommendation = "No rounds remaining"
        action = "walk_away" if gap > 5000 else "continue"
    elif gap < 5_000:
        risk = "low"
        recommendation = "Gap is small — consider splitting the difference"
        action = "make_concession"
    elif gap < 15_000 and rounds_remaining >= 2:
        risk = "low"
        recommendation = "Normal negotiation gap — continue"
        action = "continue"
    else:
        risk = "medium"
        recommendation = f"${gap:,.0f} gap with {rounds_remaining} rounds left"
        action = "continue" if rounds_remaining > 1 else "make_concession"

    return {
        "deadlock_risk": risk,
        "gap_amount": gap,
        "gap_percent": round(gap_percent, 1),
        "rounds_remaining": rounds_remaining,
        "recommendation": recommendation,
        "suggested_action": action,
    }


if __name__ == "__main__":
    result = check_negotiation_deadlock(
        buyer_offer=440_000,
        seller_counter=470_000,
        rounds_elapsed=3,
        max_rounds=5,
        buyer_budget=460_000,
    )
    print(result)
