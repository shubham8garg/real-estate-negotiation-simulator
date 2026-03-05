import random


def get_property_inspection_report(property_id: str, inspection_type: str = "standard") -> dict:
    if property_id == "742-evergreen-austin-78701":
        return {
            "property_id": property_id,
            "inspection_type": inspection_type,
            "inspection_date": "2025-01-10",
            "inspector": "Austin Home Inspections LLC",
            "foundation_rating": "excellent",
            "roof_age_years": 3,
            "hvac_age_years": 4,
            "estimated_repair_costs": {
                "immediate": 0,
                "within_1_year": 500,
                "within_5_years": 2000,
                "total_estimated": 2500,
            },
            "overall_recommendation": "proceed",
        }

    roof_age = random.randint(2, 25)
    hvac_age = random.randint(1, 20)
    repair_total = max(0, (roof_age - 10) * 500 + (hvac_age - 10) * 300)

    if repair_total < 5000:
        recommendation = "proceed"
    elif repair_total < 20000:
        recommendation = "negotiate_repairs"
    else:
        recommendation = "walk_away"

    return {
        "property_id": property_id,
        "inspection_type": inspection_type,
        "foundation_rating": random.choice(["excellent", "good", "fair"]),
        "roof_age_years": roof_age,
        "hvac_age_years": hvac_age,
        "estimated_repair_costs": {
            "total_estimated": repair_total,
        },
        "overall_recommendation": recommendation,
    }


if __name__ == "__main__":
    known = get_property_inspection_report("742-evergreen-austin-78701")
    unknown = get_property_inspection_report("demo-property-123", "full")
    print("Known property report:")
    print(known)
    print("\nUnknown property report:")
    print(unknown)
