"""
RoadQuality - Road Condition Assessment

Converts YOLO road-defect detections into:
1. Damage severity
2. Road Health Score (0-100)
"""

# Base severity weights.
# Higher value = greater negative impact on road condition.

DEFECT_WEIGHTS = {
    "D00_Longitudinal_Crack": 8,
    "D10_Transverse_Crack": 10,
    "D20_Alligator_Crack": 15,
    "D40_Pothole": 20,
    "Repair": 4,
}


def calculate_road_health(detections):
    """
    Calculate Road Health Score from YOLO detections.

    Parameters
    ----------
    detections : list of dictionaries

        Example:
        [
            {
                "class": "D40_Pothole",
                "confidence": 0.82
            },
            {
                "class": "D00_Longitudinal_Crack",
                "confidence": 0.74
            }
        ]

    Returns
    -------
    dict
        Road condition information.
    """

    total_damage = 0.0
    counts = {}

    for detection in detections:

        defect_class = detection["class"]
        confidence = float(detection["confidence"])

        if defect_class not in DEFECT_WEIGHTS:
            continue

        weight = DEFECT_WEIGHTS[defect_class]

        # Confidence-weighted damage
        damage = weight * confidence

        total_damage += damage

        counts[defect_class] = counts.get(defect_class, 0) + 1

    # Keep score between 0 and 100.
    health_score = max(0.0, min(100.0, 100.0 - total_damage))

    # Convert numerical score into understandable condition.
    if health_score >= 80:
        condition = "Good"
    elif health_score >= 60:
        condition = "Moderate"
    elif health_score >= 40:
        condition = "Poor"
    else:
        condition = "Critical"

    return {
        "road_health_score": round(health_score, 2),
        "condition": condition,
        "defect_counts": counts,
        "total_detections": len(detections),
        "damage_score": round(total_damage, 2),
    }


if __name__ == "__main__":

    # Test example
    test_detections = [
        {
            "class": "D40_Pothole",
            "confidence": 0.82
        },
        {
            "class": "D00_Longitudinal_Crack",
            "confidence": 0.74
        },
    ]

    result = calculate_road_health(test_detections)

    print("=" * 70)
    print("ROADQUALITY ROAD CONDITION TEST")
    print("=" * 70)

    print("Road Health Score:", result["road_health_score"])
    print("Condition:", result["condition"])
    print("Total detections:", result["total_detections"])
    print("Damage score:", result["damage_score"])

    print("\nDefect counts:")
    for defect, count in result["defect_counts"].items():
        print(f"  {defect}: {count}")