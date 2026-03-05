import json
from datetime import datetime
from pathlib import Path

MEMORY_FILE = Path(__file__).with_name("negotiation_memory.json")


def load_all_sessions() -> dict:
    if not MEMORY_FILE.exists():
        return {"sessions": []}
    return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))


def save_session(
    session_id: str,
    outcome: str,
    buyer_final: float,
    seller_final: float,
    agreed_price: float | None,
    rounds: int,
) -> None:
    memory = load_all_sessions()
    memory["sessions"].append(
        {
            "session_id": session_id,
            "date": datetime.now().isoformat(),
            "property": "742 Evergreen Terrace, Austin, TX 78701",
            "outcome": outcome,
            "buyer_final_offer": buyer_final,
            "seller_final_counter": seller_final,
            "agreed_price": agreed_price,
            "rounds": rounds,
        }
    )
    MEMORY_FILE.write_text(json.dumps(memory, indent=2), encoding="utf-8")


def get_buyer_memory_context() -> str:
    sessions = load_all_sessions().get("sessions", [])
    if not sessions:
        return "No previous negotiation history for this property."
    lines = ["NEGOTIATION HISTORY FOR THIS PROPERTY:"]
    for item in sessions[-3:]:
        lines.append(
            f"  {item['date'][:10]}: {item['outcome']} | Buyer offered ${item['buyer_final_offer']:,.0f} | Seller final ${item['seller_final_counter']:,.0f}"
        )
    return "\n".join(lines)


def get_seller_memory_context() -> str:
    sessions = load_all_sessions().get("sessions", [])
    if not sessions:
        return "No previous negotiation history."
    lines = ["PREVIOUS BUYER INTERACTIONS:"]
    for item in sessions[-3:]:
        lines.append(f"  {item['date'][:10]}: Buyer's highest offer was ${item['buyer_final_offer']:,.0f}")
    return "\n".join(lines)


if __name__ == "__main__":
    save_session("neg_demo_001", "deadlocked", 448000, 458000, None, 5)
    print(get_buyer_memory_context())
    print()
    print(get_seller_memory_context())
