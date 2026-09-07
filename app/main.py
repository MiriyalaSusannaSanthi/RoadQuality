import os
import osmnx as ox

from route_map import generate_route_map
from route_generator import generate_routes

from route_health import (
    load_databases,
    calculate_route_health
)

from route_recommender import (
    recommend_routes,
    print_recommendation
)


# ============================================================
# ROADQUALITY
# ============================================================

print("=" * 70)

print(
    "ROADQUALITY - AI + OSM "
    "ROAD CONDITION ROUTE RECOMMENDATION"
)

print("=" * 70)


# ============================================================
# USER INPUT
# ============================================================

source_place = input(
    "\nEnter SOURCE location: "
).strip()

destination_place = input(
    "Enter DESTINATION location: "
).strip()


if not source_place or not destination_place:

    print(
        "\nERROR: Source and destination are required."
    )

    raise SystemExit


# ============================================================
# ROUTING PREFERENCE
# ============================================================

print(
    "\nSelect routing preference:"
)

print(
    "1. Balanced"
)

print(
    "2. Best Road Condition"
)

print(
    "3. Fastest"
)


choice = input(
    "\nEnter choice (1-3): "
).strip()


if choice == "2":

    preference = "road_condition"

elif choice == "3":

    preference = "fastest"

else:

    preference = "balanced"


# ============================================================
# GEOCODING
# ============================================================

print("\n" + "=" * 70)
print("GEOCODING")
print("=" * 70)


print(
    "\nSource:",
    source_place
)


try:

    source_lat, source_lon = (
        ox.geocode(
            source_place
        )
    )

except Exception as e:

    print(
        "\nERROR: Could not locate source."
    )

    print(e)

    raise SystemExit


print(
    f"Coordinates: "
    f"{source_lat:.6f}, "
    f"{source_lon:.6f}"
)


print(
    "\nDestination:",
    destination_place
)


try:

    destination_lat, destination_lon = (
        ox.geocode(
            destination_place
        )
    )

except Exception as e:

    print(
        "\nERROR: Could not locate destination."
    )

    print(e)

    raise SystemExit


print(
    f"Coordinates: "
    f"{destination_lat:.6f}, "
    f"{destination_lon:.6f}"
)


# ============================================================
# ROAD NETWORK
# ============================================================

print("\n" + "=" * 70)
print("GETTING ROAD NETWORK")
print("=" * 70)


north = (
    max(
        source_lat,
        destination_lat
    )
    + 0.05
)

south = (
    min(
        source_lat,
        destination_lat
    )
    - 0.05
)

east = (
    max(
        source_lon,
        destination_lon
    )
    + 0.05
)

west = (
    min(
        source_lon,
        destination_lon
    )
    - 0.05
)


print(
    "\nDownloading/loading road network..."
)


try:

    G = ox.graph_from_bbox(
        bbox=(
            west,
            south,
            east,
            north
        ),
        network_type="drive",
        simplify=True
    )

except Exception as e:

    print(
        "\nERROR: Could not load road network."
    )

    print(e)

    raise SystemExit


print(
    "\nRoad network ready!"
)

print(
    "Nodes:",
    len(G.nodes)
)

print(
    "Edges:",
    len(G.edges)
)


# ============================================================
# LOAD ROAD CONDITION DATABASE
# ============================================================

print("\n" + "=" * 70)

print(
    "LOADING ROAD CONDITION DATABASE"
)

print("=" * 70)


ai_segments, osm_segments = (
    load_databases()
)


print(
    "\nAI road-condition segments:",
    len(ai_segments)
)

print(
    "OSM baseline segments:",
    len(osm_segments)
)


overlap = (
    set(ai_segments.keys())
    &
    set(osm_segments.keys())
)


print(
    "AI/OSM overlapping physical segments:",
    len(overlap)
)


# ============================================================
# GENERATE CANDIDATE ROUTES
# ============================================================

print("\n" + "=" * 70)

print(
    "GENERATING CANDIDATE ROUTES"
)

print("=" * 70)


routes = generate_routes(
    G,
    source_lat,
    source_lon,
    destination_lat,
    destination_lon,
    number_of_routes=3
)


if not routes:

    print(
        "\nNo routes could be generated."
    )

    raise SystemExit


print(
    "\nCandidate routes generated:",
    len(routes)
)


# ============================================================
# DISPLAY CANDIDATE ROUTES
# ============================================================

print("\n" + "=" * 70)
print("CANDIDATE ROUTES")
print("=" * 70)


for route in routes:

    print(
        f"{route['name']} | "
        f"Distance: "
        f"{route['distance']} km | "
        f"Time: "
        f"{route['travel_time']} min | "
        f"Nodes: "
        f"{len(route.get('nodes', []))} | "
        f"GPS points: "
        f"{len(route.get('coordinates', []))} | "
        f"OSM edges: "
        f"{len(route.get('osm_edges', []))}"
    )


# ============================================================
# ROAD DATABASE CHECK
# ============================================================

print("\n" + "=" * 70)
print("ROAD DATABASE CHECK")
print("=" * 70)


for route in routes:

    route_edges = route.get(
        "osm_edges",
        []
    )

    seen_edges = set()

    ai_match_count = 0
    osm_match_count = 0
    unavailable_count = 0


    for edge in route_edges:

        if not edge or len(edge) != 3:
            continue


        try:

            u = int(edge[0])
            v = int(edge[1])
            key = int(edge[2])

        except (
            ValueError,
            TypeError
        ):

            continue


        if u <= v:

            physical_edge = (
                u,
                v,
                key
            )

        else:

            physical_edge = (
                v,
                u,
                key
            )


        if physical_edge in seen_edges:
            continue


        seen_edges.add(
            physical_edge
        )


        # AI takes priority

        if physical_edge in ai_segments:

            ai_match_count += 1


        # Otherwise OSM

        elif physical_edge in osm_segments:

            osm_match_count += 1


        else:

            unavailable_count += 1


    print()

    print(
        f"{route['name']}: "
        f"{len(seen_edges)} physical OSM edges"
    )

    print(
        f"  AI matches      : "
        f"{ai_match_count}"
    )

    print(
        f"  OSM matches     : "
        f"{osm_match_count}"
    )

    print(
        f"  Unavailable     : "
        f"{unavailable_count}"
    )

    print(
        f"  Total data      : "
        f"{ai_match_count + osm_match_count}"
    )


# ============================================================
# ASSESS ROAD CONDITION
# ============================================================

print("\n" + "=" * 70)

print(
    "ASSESSING ROAD CONDITION"
)

print("=" * 70)


evaluated_routes = []


for route in routes:

    print(
        "\n" + "-" * 70
    )

    print(
        "Evaluating:",
        route["name"]
    )


    route_edges = route.get(
        "osm_edges",
        []
    )


    print(
        "Route OSM edges:",
        len(route_edges)
    )


    # ========================================================
    # CALCULATE HEALTH
    # ========================================================

    health_result = calculate_route_health(
        route_edges,
        ai_segments=ai_segments,
        osm_segments=osm_segments
    )


    health = health_result.get(
        "health"
    )


    condition = health_result.get(
        "condition",
        "Unknown"
    )


    # ========================================================
    # FALLBACK
    # ========================================================

    if health is None:

        health = 70.0

        condition = "Unknown"


    # ========================================================
    # CREATE EVALUATED ROUTE
    # ========================================================

    evaluated_route = {

        **route,

        "road_health":
            round(
                float(health),
                2
            ),

        "condition":
            condition,


        "matched_observations":
            health_result.get(
                "matched_observations",
                0
            ),

        "observation_count":
            health_result.get(
                "observation_count",
                0
            ),


        "ai_segment_count":
            health_result.get(
                "ai_segment_count",
                0
            ),

        "osm_segment_count":
            health_result.get(
                "osm_segment_count",
                0
            ),

        "unavailable_segment_count":
            health_result.get(
                "unavailable_segment_count",
                0
            ),


        "ai_coverage":
            health_result.get(
                "ai_coverage",
                0.0
            ),

        "coverage":
            health_result.get(
                "coverage",
                0.0
            ),


        "ai_matches":
            health_result.get(
                "ai_matches",
                []
            ),

        "osm_matches":
            health_result.get(
                "osm_matches",
                []
            ),


        "health_observations":
            health_result.get(
                "observations",
                []
            )
    }


    evaluated_routes.append(
        evaluated_route
    )


    # ========================================================
    # DISPLAY HEALTH
    # ========================================================

    print(
        "\nRoad Health:",
        evaluated_route[
            "road_health"
        ],
        "/ 100"
    )


    print(
        "Condition:",
        evaluated_route[
            "condition"
        ]
    )


    print(
        "AI matched segments:",
        evaluated_route[
            "ai_segment_count"
        ]
    )


    print(
        "OSM baseline segments:",
        evaluated_route[
            "osm_segment_count"
        ]
    )


    print(
        "Unavailable segments:",
        evaluated_route[
            "unavailable_segment_count"
        ]
    )


    print(
        "AI Coverage:",
        evaluated_route[
            "ai_coverage"
        ],
        "%"
    )


    print(
        "Overall Data Coverage:",
        evaluated_route[
            "coverage"
        ],
        "%"
    )


    # ========================================================
    # SHOW AI MATCHES
    # ========================================================

    ai_matches = evaluated_route[
        "ai_matches"
    ]


    if ai_matches:

        print(
            "\nAI matched road segments:"
        )


        for item in ai_matches:

            print(
                f"  {item['edge']} | "
                f"Health: "
                f"{item['health_score']} | "
                f"Image: "
                f"{item.get('image', '')}"
            )


    # ========================================================
    # SHOW OSM MATCHES
    # ========================================================

    osm_matches = evaluated_route[
        "osm_matches"
    ]


    if osm_matches:

        print(
            "\nOSM baseline road segments:"
        )


        for item in osm_matches[:10]:

            print(
                f"  {item['edge']} | "
                f"Health: "
                f"{item['health_score']}"
            )


        if len(osm_matches) > 10:

            print(
                f"  ... "
                f"{len(osm_matches) - 10} "
                f"more OSM segments"
            )


# ============================================================
# ROUTE HEALTH SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("ROUTE HEALTH")
print("=" * 70)


for route in evaluated_routes:

    print(
        f"{route['name']} | "
        f"Distance: "
        f"{route['distance']} km | "
        f"Time: "
        f"{route['travel_time']} min | "
        f"Health: "
        f"{route['road_health']}/100 | "
        f"Condition: "
        f"{route['condition']}"
    )


    print(
        f"  AI segments: "
        f"{route['ai_segment_count']} | "
        f"OSM baseline: "
        f"{route['osm_segment_count']} | "
        f"Unavailable: "
        f"{route['unavailable_segment_count']}"
    )


    print(
        f"  AI Coverage: "
        f"{route['ai_coverage']}% | "
        f"Overall Data Coverage: "
        f"{route['coverage']}%"
    )


# ============================================================
# ROUTE RECOMMENDATION
# ============================================================

print("\n" + "=" * 70)

print(
    "GENERATING ROUTE RECOMMENDATION"
)

print("=" * 70)


ranked_routes = recommend_routes(
    evaluated_routes,
    preference
)


if not ranked_routes:

    print(
        "\nERROR: Could not rank routes."
    )

    raise SystemExit


# ============================================================
# PRINT RECOMMENDATION
# ============================================================

print_recommendation(
    ranked_routes,
    preference
)


recommended = ranked_routes[0]


# ============================================================
# FIND RECOMMENDED ROUTE INDEX
# ============================================================

recommended_index = 0


for i, route in enumerate(routes):

    if route["name"] == recommended["name"]:

        recommended_index = i

        break


# ============================================================
# INTERACTIVE MAP
# ============================================================

print("\n" + "=" * 70)

print(
    "GENERATING INTERACTIVE ROUTE MAP"
)

print("=" * 70)


map_output = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "results",
        "roadquality_route_map.html"
    )
)


os.makedirs(
    os.path.dirname(
        map_output
    ),
    exist_ok=True
)


try:

    generate_route_map(
        routes=routes,

        source_lat=source_lat,
        source_lon=source_lon,

        destination_lat=destination_lat,
        destination_lon=destination_lon,

        output_file=map_output,

        recommended_route_index=
            recommended_index,

        ai_segments=ai_segments,
        osm_segments=osm_segments
    )


    print(
        "\nInteractive map generated successfully!"
    )


    print(
        "Map:"
    )


    print(
        map_output
    )


except Exception as e:

    print(
        "\nWARNING: Could not generate map."
    )

    print(e)


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 70)

print(
    "ROADQUALITY ANALYSIS COMPLETED"
)

print("=" * 70)


print(
    "\nSource:"
)

print(
    source_place
)


print(
    "\nDestination:"
)

print(
    destination_place
)


print(
    "\nRouting preference:"
)

print(
    preference
)


print(
    "\nRecommended route:"
)

print(
    recommended["name"]
)


print(
    "\nRoad Health:"
)

print(
    recommended["road_health"],
    "/ 100"
)


print(
    "\nCondition:"
)

print(
    recommended["condition"]
)


print(
    "\nDistance:"
)

print(
    recommended["distance"],
    "km"
)


print(
    "\nTravel Time:"
)

print(
    recommended["travel_time"],
    "minutes"
)


print(
    "\nAI Road Segments:"
)

print(
    recommended[
        "ai_segment_count"
    ]
)


print(
    "\nOSM Baseline Segments:"
)

print(
    recommended[
        "osm_segment_count"
    ]
)


print(
    "\nUnavailable Segments:"
)

print(
    recommended[
        "unavailable_segment_count"
    ]
)


print(
    "\nAI Coverage:"
)

print(
    recommended[
        "ai_coverage"
    ],
    "%"
)


print(
    "\nOverall Road Data Coverage:"
)

print(
    recommended[
        "coverage"
    ],
    "%"
)


print(
    "\n" + "=" * 70
)