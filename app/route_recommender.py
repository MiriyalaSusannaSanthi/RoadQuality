# ============================================================
# ROADQUALITY - SMART ROUTE RECOMMENDATION ENGINE
# ============================================================
#
# Purpose:
#   Rank candidate routes according to user preference.
#
# Preferences:
#   1. balanced
#   2. road_condition
#   3. fastest
#
# The engine considers:
#   - Road health
#   - Travel time
#   - Distance
#   - Road-condition data coverage
#   - Data confidence
#
# ============================================================

from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "results"


# ============================================================
# PREFERENCE WEIGHTS
# ============================================================

PREFERENCE_WEIGHTS = {

    # --------------------------------------------------------
    # Balanced:
    # Best overall compromise between quality, time and
    # distance while also considering data availability.
    # --------------------------------------------------------

    "balanced": {
        "health": 0.40,
        "time": 0.30,
        "distance": 0.20,
        "coverage": 0.10
    },

    # --------------------------------------------------------
    # Road Condition:
    # Strongly prioritizes road health and reliable data.
    # --------------------------------------------------------

    "road_condition": {
        "health": 0.70,
        "coverage": 0.20,
        "time": 0.05,
        "distance": 0.05
    },

    # --------------------------------------------------------
    # Fastest:
    # Strongly prioritizes travel time.
    # --------------------------------------------------------

    "fastest": {
        "time": 0.70,
        "distance": 0.20,
        "health": 0.10,
        "coverage": 0.00
    }
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_higher_better(value):
    """
    Convert a higher-is-better value to a 0-100 range.

    Examples:
        Road health = 85 -> 85
        Coverage = 70 -> 70
        Invalid/None -> 0
    """

    if value is None:
        return 0.0

    try:
        value = float(value)

    except (TypeError, ValueError):
        return 0.0

    return max(
        0.0,
        min(
            100.0,
            value
        )
    )


# ============================================================
# LOWER-IS-BETTER NORMALIZATION
# ============================================================

def normalize_lower_better(
    value,
    minimum,
    maximum
):
    """
    Convert distance/time into a 0-100 score.

    Smaller value = higher score.

    Example:

        Minimum time = 20 min
        Maximum time = 40 min

        Route time = 20 -> 100
        Route time = 30 -> 50
        Route time = 40 -> 0
    """

    if value is None:
        return 0.0

    try:
        value = float(value)

    except (TypeError, ValueError):
        return 0.0

    try:
        minimum = float(minimum)
        maximum = float(maximum)

    except (TypeError, ValueError):
        return 0.0

    value_range = maximum - minimum

    # All routes have the same value.
    if value_range <= 0:
        return 100.0

    score = (
        (maximum - value)
        /
        value_range
    ) * 100.0

    return max(
        0.0,
        min(
            100.0,
            score
        )
    )


# ============================================================
# SAFE NUMERIC VALUE
# ============================================================

def safe_float(
    value,
    default=0.0
):
    """
    Safely convert a value to float.
    """

    if value is None:
        return default

    try:
        return float(value)

    except (TypeError, ValueError):
        return default


# ============================================================
# CALCULATE ROUTE SCORE
# ============================================================

def calculate_score(
    route,
    routes,
    preference="balanced"
):
    """
    Calculate the final recommendation score.

    Final score:

        health_score    * health weight
      + time_score      * time weight
      + distance_score  * distance weight
      + coverage_score  * coverage weight

    Result is between 0 and 100.
    """

    # --------------------------------------------------------
    # Validate preference
    # --------------------------------------------------------

    if preference not in PREFERENCE_WEIGHTS:
        preference = "balanced"

    weights = PREFERENCE_WEIGHTS[
        preference
    ]

    # --------------------------------------------------------
    # DISTANCE SCORES
    # --------------------------------------------------------

    distances = [

        safe_float(
            route_item.get(
                "distance",
                0.0
            )
        )

        for route_item in routes
    ]

    if distances:

        min_distance = min(
            distances
        )

        max_distance = max(
            distances
        )

    else:

        min_distance = 0.0
        max_distance = 0.0

    distance_score = normalize_lower_better(

        route.get(
            "distance",
            0.0
        ),

        min_distance,
        max_distance
    )

    # --------------------------------------------------------
    # TRAVEL TIME SCORES
    # --------------------------------------------------------

    times = [

        safe_float(
            route_item.get(
                "travel_time",
                0.0
            )
        )

        for route_item in routes
    ]

    if times:

        min_time = min(
            times
        )

        max_time = max(
            times
        )

    else:

        min_time = 0.0
        max_time = 0.0

    time_score = normalize_lower_better(

        route.get(
            "travel_time",
            0.0
        ),

        min_time,
        max_time
    )

    # --------------------------------------------------------
    # ROAD HEALTH
    # --------------------------------------------------------

    health_score = normalize_higher_better(

        route.get(
            "road_health"
        )
    )

    # --------------------------------------------------------
    # COVERAGE
    #
    # Coverage is expected to be 0-100.
    # --------------------------------------------------------

    coverage = route.get(
        "coverage"
    )

    if coverage is None:

        coverage = route.get(
            "overall_coverage",
            0.0
        )

    coverage_score = normalize_higher_better(
        coverage
    )

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    final_score = (

        weights["health"]
        *
        health_score

        +

        weights["time"]
        *
        time_score

        +

        weights["distance"]
        *
        distance_score

        +

        weights["coverage"]
        *
        coverage_score

    )

    return (

        round(
            final_score,
            2
        ),

        round(
            distance_score,
            2
        ),

        round(
            time_score,
            2
        ),

        round(
            coverage_score,
            2
        )
    )


# ============================================================
# GENERATE RECOMMENDATION REASON
# ============================================================

def generate_reason(
    route,
    preference
):
    """
    Generate a human-readable explanation for the
    recommended route.
    """

    health_raw = route.get(
        "road_health"
    )

    distance = safe_float(
        route.get(
            "distance",
            0.0
        )
    )

    travel_time = safe_float(
        route.get(
            "travel_time",
            0.0
        )
    )

    coverage = route.get(
        "coverage"
    )

    if coverage is None:

        coverage = route.get(
            "overall_coverage",
            0.0
        )

    coverage = safe_float(
        coverage
    )

    condition = route.get(
        "condition",
        "Unknown"
    )

    # --------------------------------------------------------
    # ROAD CONDITION
    # --------------------------------------------------------

    if preference == "road_condition":

        if health_raw is None:

            return (
                "Selected for road-condition preference, "
                "but sufficient road-health data is not "
                "available for this route."
            )

        health = safe_float(
            health_raw
        )

        return (
            f"Selected because it provides "
            f"{condition.lower()} road quality "
            f"with a health score of "
            f"{health:.0f}/100 and "
            f"{coverage:.0f}% road-data coverage."
        )

    # --------------------------------------------------------
    # FASTEST
    # --------------------------------------------------------

    if preference == "fastest":

        if health_raw is None:

            return (
                f"Selected because it provides the "
                f"fastest estimated travel time of "
                f"{travel_time:.1f} minutes."
            )

        health = safe_float(
            health_raw
        )

        return (
            f"Selected because it provides an estimated "
            f"travel time of {travel_time:.1f} minutes "
            f"while maintaining a road-health score "
            f"of {health:.0f}/100."
        )

    # --------------------------------------------------------
    # BALANCED
    # --------------------------------------------------------

    if health_raw is None:

        return (
            f"Selected as the best overall route "
            f"based on distance ({distance:.1f} km) "
            f"and travel time "
            f"({travel_time:.1f} min). "
            f"Road-condition data is insufficient."
        )

    health = safe_float(
        health_raw
    )

    return (
        f"Selected as the best overall balance of "
        f"road quality ({health:.0f}/100), "
        f"distance ({distance:.1f} km), "
        f"and travel time ({travel_time:.1f} min)."
    )


# ============================================================
# RECOMMEND ROUTES
# ============================================================

def recommend_routes(
    routes,
    preference="balanced"
):
    """
    Rank all candidate routes.

    Returns:
        List of routes sorted by final score.
    """

    if not routes:
        return []

    # --------------------------------------------------------
    # Validate preference
    # --------------------------------------------------------

    if preference not in PREFERENCE_WEIGHTS:

        preference = "balanced"

    scored = []

    # --------------------------------------------------------
    # Score every route
    # --------------------------------------------------------

    for route in routes:

        (
            final_score,
            distance_score,
            time_score,
            coverage_score
        ) = calculate_score(

            route,
            routes,
            preference
        )

        scored_route = {

            **route,

            "distance_score":
                distance_score,

            "time_score":
                time_score,

            "coverage_score":
                coverage_score,

            "final_score":
                final_score
        }

        scored.append(
            scored_route
        )

    # --------------------------------------------------------
    # Sort highest score first
    # --------------------------------------------------------

    scored.sort(

        key=lambda route:
            route.get(
                "final_score",
                0.0
            ),

        reverse=True
    )

    # --------------------------------------------------------
    # Assign ranks
    # --------------------------------------------------------

    for index, route in enumerate(
        scored,
        start=1
    ):

        route["rank"] = index

    # --------------------------------------------------------
    # Recommendation reason
    #
    # Only the best route needs the main reason.
    # Other routes receive their own explanation as well.
    # --------------------------------------------------------

    for route in scored:

        route["recommendation_reason"] = ""

    if scored:

        best_route = scored[0]

        best_route[
            "recommendation_reason"
        ] = generate_reason(

            best_route,
            preference
        )

    # --------------------------------------------------------
    # SCORE BREAKDOWN
    # --------------------------------------------------------

    weights = PREFERENCE_WEIGHTS[
        preference
    ]

    for route in scored:

        health_value = route.get(
            "road_health"
        )

        route["score_breakdown"] = {

            "road_health":
                health_value,

            "health_score":
                normalize_higher_better(
                    health_value
                ),

            "health_weight":
                weights["health"],

            "distance_score":
                route[
                    "distance_score"
                ],

            "distance_weight":
                weights["distance"],

            "time_score":
                route[
                    "time_score"
                ],

            "time_weight":
                weights["time"],

            "coverage_score":
                route[
                    "coverage_score"
                ],

            "coverage_weight":
                weights["coverage"],

            "final_score":
                route[
                    "final_score"
                ]
        }

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

    return scored


# ============================================================
# PRINT RECOMMENDATION
# ============================================================

def print_recommendation(
    routes,
    preference
):
    """
    Print recommendation results in terminal.
    """

    print(
        "\n"
        +
        "=" * 80
    )

    print(
        "ROADQUALITY SMART ROUTE RECOMMENDATION"
    )

    print(
        "=" * 80
    )

    print(
        f"\nPreference: {preference}"
    )

    # --------------------------------------------------------
    # No routes
    # --------------------------------------------------------

    if not routes:

        print(
            "\nNo routes available."
        )

        return

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    print(
        "\nROUTE RANKING"
    )

    print(
        "-" * 80
    )

    for route in routes:

        health = route.get(
            "road_health"
        )

        if health is None:

            health_text = (
                "Insufficient Data"
            )

        else:

            health_text = (
                f"{safe_float(health):.1f}/100"
            )

        coverage = safe_float(
            route.get(
                "coverage",
                route.get(
                    "overall_coverage",
                    0.0
                )
            )
        )

        print(

            f"{route.get('rank', '-')}. "

            f"{route.get('name', 'Route')} | "

            f"Health: {health_text} | "

            f"Condition: "
            f"{route.get('condition', 'Unknown')} | "

            f"Time: "
            f"{safe_float(route.get('travel_time')):.1f} min | "

            f"Distance: "
            f"{safe_float(route.get('distance')):.1f} km | "

            f"Coverage: "
            f"{coverage:.1f}% | "

            f"Score: "
            f"{route.get('final_score', 0.0):.2f}"
        )

    # --------------------------------------------------------
    # Best route
    # --------------------------------------------------------

    best = routes[0]

    print(
        "\n"
        +
        "=" * 80
    )

    print(
        "RECOMMENDED ROUTE"
    )

    print(
        "=" * 80
    )

    print(
        f"\nRoute: "
        f"{best.get('name', 'Route')}"
    )

    health = best.get(
        "road_health"
    )

    if health is None:

        print(
            "Road Health: "
            "Insufficient Data"
        )

    else:

        print(
            f"Road Health: "
            f"{safe_float(health):.1f} / 100"
        )

    print(
        f"Condition: "
        f"{best.get('condition', 'Unknown')}"
    )

    print(
        f"Distance: "
        f"{safe_float(best.get('distance')):.2f} km"
    )

    print(
        f"Travel Time: "
        f"{safe_float(best.get('travel_time')):.2f} min"
    )

    print(
        f"Coverage: "
        f"{safe_float(best.get('coverage', 0.0)):.1f}%"
    )

    print(
        f"Final Score: "
        f"{best.get('final_score', 0.0):.2f}"
    )

    print(
        f"Reason: "
        f"{best.get('recommendation_reason', '')}"
    )

    print(
        "\n"
        +
        "=" * 80
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # TEST ROUTES
    # --------------------------------------------------------

    test_routes = [

        {
            "name":
                "Route 1",

            "distance":
                20.0,

            "travel_time":
                30.0,

            "road_health":
                65.0,

            "condition":
                "Moderate",

            "coverage":
                90.0
        },

        {
            "name":
                "Route 2",

            "distance":
                24.0,

            "travel_time":
                42.0,

            "road_health":
                92.0,

            "condition":
                "Good",

            "coverage":
                95.0
        },

        {
            "name":
                "Route 3",

            "distance":
                28.0,

            "travel_time":
                27.0,

            "road_health":
                72.0,

            "condition":
                "Moderate",

            "coverage":
                80.0
        }
    ]

    # --------------------------------------------------------
    # TEST ALL PREFERENCES
    # --------------------------------------------------------

    for preference in [

        "balanced",

        "road_condition",

        "fastest"

    ]:

        print(
            "\n\n"
            +
            "#" * 80
        )

        print(
            f"TESTING PREFERENCE: "
            f"{preference.upper()}"
        )

        print(
            "#" * 80
        )

        ranked_routes = recommend_routes(

            test_routes,

            preference
        )

        print_recommendation(

            ranked_routes,

            preference
        )