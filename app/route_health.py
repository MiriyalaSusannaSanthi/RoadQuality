"""
RoadQuality - Dynamic Route Health Engine

Features:
- Exact OSM edge matching when available
- Coordinate-based AI observation matching
- Supports road_condition_data.csv observations
- Works with arbitrary source/destination routes
- Avoids treating missing data as health = 0
- Calculates AI / OSM / overall coverage
- Uses AI + OSM weighted scoring when both are available
"""

from pathlib import Path
import csv
import math
from typing import Dict, List, Tuple, Optional, Any


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

AI_DATABASE = BASE_DIR / "ai_osm_segment_scores.csv"
OSM_DATABASE = BASE_DIR / "road_segment_scores.csv"
OBSERVATION_DATABASE = BASE_DIR / "data" / "road_condition_data.csv"


# ============================================================
# CONFIGURATION
# ============================================================

AI_WEIGHT = 0.70
OSM_WEIGHT = 0.30

# Maximum distance for matching an AI observation to a route edge.
# 150 meters prevents observations from completely unrelated roads
# being used for a route.
AI_MATCH_RADIUS_METERS = 150.0


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_edge(u: Any, v: Any, key: Any = 0):
    """
    Normalize an OSM edge so direction does not matter.

    Example:
        (100, 200, 0)
        (200, 100, 0)

    become the same physical edge.
    """

    try:
        u = int(u)
        v = int(v)
    except Exception:
        pass

    try:
        key = int(key)
    except Exception:
        pass

    if u <= v:
        return (u, v, key)

    return (v, u, key)


def safe_float(value, default=None):
    """Safely convert a value to float."""

    try:
        if value is None:
            return default

        text = str(value).strip()

        if text == "":
            return default

        return float(text)

    except Exception:
        return default


def safe_int(value, default=0):
    """Safely convert a value to int."""

    try:
        return int(float(value))
    except Exception:
        return default


def clean_condition(condition, health):
    """
    Return a meaningful condition.

    If condition is missing, derive it from health score.
    """

    if condition:
        condition = str(condition).strip()

        if condition.lower() not in {
            "",
            "unknown",
            "none",
            "null",
            "nan"
        }:
            return condition

    if health is None:
        return "Insufficient Data"

    if health >= 80:
        return "Good"

    if health >= 60:
        return "Moderate"

    if health >= 40:
        return "Poor"

    return "Critical"


# ============================================================
# GEO HELPERS
# ============================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two geographic points in meters.
    """

    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except Exception:
        return float("inf")

    radius = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(d_lambda / 2) ** 2
    )

    a = max(0.0, min(1.0, a))

    return 2 * radius * math.asin(math.sqrt(a))


def get_coordinate_fields(row):
    """
    Detect latitude / longitude columns from different CSV formats.
    """

    lat_names = [
        "latitude",
        "lat",
        "y",
        "mid_lat",
        "center_lat",
        "start_lat",
        "from_lat"
    ]

    lon_names = [
        "longitude",
        "lon",
        "lng",
        "x",
        "mid_lon",
        "center_lon",
        "start_lon",
        "from_lon"
    ]

    lat = None
    lon = None

    for name in lat_names:
        if name in row:
            lat = safe_float(row.get(name))
            if lat is not None:
                break

    for name in lon_names:
        if name in row:
            lon = safe_float(row.get(name))
            if lon is not None:
                break

    return lat, lon


# ============================================================
# AI DATABASE
# ============================================================

def load_ai_osm_segments():
    """
    Load AI road-condition observations indexed by OSM edge.

    Supports the existing:
        u, v, key, health_score, condition, image

    format.

    If latitude / longitude are also available, they are preserved
    for spatial matching.
    """

    segments = {}

    if not AI_DATABASE.exists():
        print(f"[RouteHealth] AI database not found: {AI_DATABASE}")
        return segments

    try:
        with open(
            AI_DATABASE,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                if not row:
                    continue

                u = row.get("u")
                v = row.get("v")

                if u is None or v is None:
                    continue

                key = row.get("key", 0)

                edge = normalize_edge(u, v, key)

                health = safe_float(
                    row.get("health_score")
                )

                condition = clean_condition(
                    row.get("condition"),
                    health
                )

                lat, lon = get_coordinate_fields(row)

                segments[edge] = {
                    "u": edge[0],
                    "v": edge[1],
                    "key": edge[2],
                    "health_score": health,
                    "condition": condition,
                    "image": row.get("image", ""),
                    "latitude": lat,
                    "longitude": lon
                }

    except Exception as exc:
        print(
            f"[RouteHealth] Failed to load AI database: {exc}"
        )

    print(
        f"[RouteHealth] Loaded {len(segments)} AI OSM segments"
    )

    return segments


# ============================================================
# AI POINT OBSERVATIONS
# ============================================================

def load_ai_point_observations():
    """
    Load geographic AI observations from road_condition_data.csv.

    Expected fields include:

        segment_id
        latitude
        longitude
        health_score
        condition
        detections

    This allows AI observations to be matched geographically
    instead of depending only on OSM IDs.
    """

    observations = []

    if not OBSERVATION_DATABASE.exists():
        print(
            "[RouteHealth] Coordinate observation database not found:"
            f" {OBSERVATION_DATABASE}"
        )
        return observations

    try:

        with open(
            OBSERVATION_DATABASE,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                if not row:
                    continue

                lat = safe_float(
                    row.get("latitude")
                )

                lon = safe_float(
                    row.get("longitude")
                )

                health = safe_float(
                    row.get("health_score")
                )

                if lat is None or lon is None:
                    continue

                if health is None:
                    continue

                observations.append(
                    {
                        "segment_id": row.get(
                            "segment_id",
                            ""
                        ),
                        "latitude": lat,
                        "longitude": lon,
                        "health_score": max(
                            0.0,
                            min(100.0, health)
                        ),
                        "condition": clean_condition(
                            row.get("condition"),
                            health
                        ),
                        "detections": row.get(
                            "detections",
                            ""
                        )
                    }
                )

    except Exception as exc:

        print(
            "[RouteHealth] Failed to load coordinate "
            f"observations: {exc}"
        )

    print(
        "[RouteHealth] Loaded "
        f"{len(observations)} coordinate AI observations"
    )

    return observations


# ============================================================
# OSM DATABASE
# ============================================================

def load_osm_segments():
    """
    Load existing OSM baseline scores.
    """

    segments = {}

    if not OSM_DATABASE.exists():
        print(
            f"[RouteHealth] OSM database not found: {OSM_DATABASE}"
        )
        return segments

    try:

        with open(
            OSM_DATABASE,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                if not row:
                    continue

                u = row.get("u")
                v = row.get("v")

                if u is None or v is None:
                    continue

                key = row.get("key", 0)

                edge = normalize_edge(
                    u,
                    v,
                    key
                )

                health = safe_float(
                    row.get("health_score")
                )

                if health is None:
                    continue

                segments[edge] = {
                    "u": edge[0],
                    "v": edge[1],
                    "key": edge[2],
                    "health_score": max(
                        0.0,
                        min(100.0, health)
                    )
                }

    except Exception as exc:

        print(
            f"[RouteHealth] Failed to load OSM database: {exc}"
        )

    print(
        f"[RouteHealth] Loaded {len(segments)} OSM segments"
    )

    return segments


# ============================================================
# DATABASE SUMMARY
# ============================================================

def load_databases():

    ai_segments = load_ai_osm_segments()

    osm_segments = load_osm_segments()

    ai_points = load_ai_point_observations()

    exact_overlap = len(
        set(ai_segments.keys())
        & set(osm_segments.keys())
    )

    print(
        "[RouteHealth] Database summary:"
    )

    print(
        f"  AI edge observations : {len(ai_segments)}"
    )

    print(
        f"  AI coordinate points : {len(ai_points)}"
    )

    print(
        f"  OSM observations     : {len(osm_segments)}"
    )

    print(
        f"  Exact overlap        : {exact_overlap}"
    )

    return (
        ai_segments,
        osm_segments,
        ai_points
    )


# ============================================================
# GRAPH EDGE COORDINATES
# ============================================================

def get_edge_midpoint(graph, u, v):
    """
    Get the geographic midpoint of an OSM edge.

    OSMnx graphs normally store:

        x = longitude
        y = latitude
    """

    if graph is None:
        return None

    try:

        node_u = graph.nodes[u]
        node_v = graph.nodes[v]

        lat1 = safe_float(node_u.get("y"))
        lon1 = safe_float(node_u.get("x"))

        lat2 = safe_float(node_v.get("y"))
        lon2 = safe_float(node_v.get("x"))

        if (
            lat1 is None
            or lon1 is None
            or lat2 is None
            or lon2 is None
        ):
            return None

        return (
            (lat1 + lat2) / 2.0,
            (lon1 + lon2) / 2.0
        )

    except Exception:
        return None


# ============================================================
# SPATIAL AI MATCHING
# ============================================================

def find_nearest_ai_observation(
    latitude,
    longitude,
    observations,
    used_indices=None,
    max_distance=AI_MATCH_RADIUS_METERS
):
    """
    Find the nearest geographic AI observation.

    A maximum radius prevents unrelated roads from being
    incorrectly assigned.
    """

    if not observations:
        return None, None

    if used_indices is None:
        used_indices = set()

    best_index = None
    best_distance = float("inf")

    for index, observation in enumerate(observations):

        if index in used_indices:
            continue

        distance = haversine_distance(
            latitude,
            longitude,
            observation["latitude"],
            observation["longitude"]
        )

        if distance < best_distance:
            best_distance = distance
            best_index = index

    if (
        best_index is None
        or best_distance > max_distance
    ):
        return None, None

    return (
        observations[best_index],
        best_distance
    )


# ============================================================
# ROUTE HEALTH
# ============================================================

def calculate_route_health(
    route_edges,
    ai_segments=None,
    osm_segments=None,
    graph=None,
    ai_points=None
):
    """
    Calculate road health for a route.

    Parameters
    ----------
    route_edges:
        List of (u, v, key) OSM edges.

    ai_segments:
        Exact OSM-edge AI observations.

    osm_segments:
        Exact OSM-edge baseline observations.

    graph:
        Optional current OSMnx graph.

        When provided, coordinate AI observations can be
        matched to the current route dynamically.

    ai_points:
        Optional geographic AI observations.

    Returns
    -------
    dict
        Complete route health information.
    """

    if route_edges is None:
        route_edges = []

    if ai_segments is None:
        ai_segments = {}

    if osm_segments is None:
        osm_segments = {}

    if ai_points is None:
        ai_points = []

    # --------------------------------------------------------
    # Remove duplicate route edges
    # --------------------------------------------------------

    unique_edges = []

    seen_edges = set()

    for edge in route_edges:

        if edge is None:
            continue

        try:

            if len(edge) >= 3:
                u, v, key = edge[0], edge[1], edge[2]

            elif len(edge) == 2:
                u, v = edge
                key = 0

            else:
                continue

            normalized = normalize_edge(
                u,
                v,
                key
            )

            if normalized in seen_edges:
                continue

            seen_edges.add(normalized)

            unique_edges.append(normalized)

        except Exception:
            continue

    total_segments = len(unique_edges)

    # --------------------------------------------------------
    # Empty route
    # --------------------------------------------------------

    if total_segments == 0:

        return {
            "health": None,
            "condition": "Insufficient Data",
            "confidence": 0.0,

            "ai_matches": 0,
            "osm_matches": 0,

            "ai_coverage": 0.0,
            "coverage": 0.0,
            "overall_coverage": 0.0,

            "total_segments": 0,
            "unavailable_segments": 0,

            "ai_health": None,
            "osm_health": None,

            "data_status": "No route segments"
        }

    # --------------------------------------------------------
    # Match route segments
    # --------------------------------------------------------

    ai_matches = []
    osm_matches = []

    unavailable_segments = []

    used_ai_points = set()

    # --------------------------------------------------------
    # Process each route edge
    # --------------------------------------------------------

    for edge in unique_edges:

        matched = False

        # ====================================================
        # 1. EXACT AI OSM MATCH
        # ====================================================

        if edge in ai_segments:

            observation = ai_segments[edge]

            health = safe_float(
                observation.get("health_score")
            )

            if health is not None:

                ai_matches.append(
                    {
                        "edge": edge,
                        "health_score": health,
                        "condition": clean_condition(
                            observation.get("condition"),
                            health
                        ),
                        "source": "AI-exact"
                    }
                )

                matched = True

        # ====================================================
        # 2. EXACT OSM MATCH
        # ====================================================

        if not matched and edge in osm_segments:

            observation = osm_segments[edge]

            health = safe_float(
                observation.get("health_score")
            )

            if health is not None:

                osm_matches.append(
                    {
                        "edge": edge,
                        "health_score": health,
                        "source": "OSM-exact"
                    }
                )

                matched = True

        # ====================================================
        # 3. SPATIAL AI MATCH
        # ====================================================

        if not matched and graph is not None:

            midpoint = get_edge_midpoint(
                graph,
                edge[0],
                edge[1]
            )

            if midpoint is not None:

                latitude, longitude = midpoint

                observation, distance = (
                    find_nearest_ai_observation(
                        latitude,
                        longitude,
                        ai_points,
                        used_ai_points
                    )
                )

                if observation is not None:

                    try:
                        index = ai_points.index(
                            observation
                        )

                        used_ai_points.add(index)

                    except Exception:
                        pass

                    health = safe_float(
                        observation.get("health_score")
                    )

                    if health is not None:

                        ai_matches.append(
                            {
                                "edge": edge,
                                "health_score": health,
                                "condition": clean_condition(
                                    observation.get(
                                        "condition"
                                    ),
                                    health
                                ),
                                "source": "AI-spatial",
                                "distance_m": round(
                                    distance,
                                    2
                                )
                            }
                        )

                        matched = True

        # ====================================================
        # 4. UNAVAILABLE
        # ====================================================

        if not matched:

            unavailable_segments.append(
                edge
            )

    # --------------------------------------------------------
    # Counts
    # --------------------------------------------------------

    ai_count = len(ai_matches)

    osm_count = len(osm_matches)

    unavailable_count = len(
        unavailable_segments
    )

    # --------------------------------------------------------
    # Individual source health
    # --------------------------------------------------------

    ai_health = None

    osm_health = None

    if ai_count > 0:

        ai_health = sum(
            item["health_score"]
            for item in ai_matches
        ) / ai_count

    if osm_count > 0:

        osm_health = sum(
            item["health_score"]
            for item in osm_matches
        ) / osm_count

    # --------------------------------------------------------
    # Combined health
    # --------------------------------------------------------

    health = None

    if ai_health is not None and osm_health is not None:

        health = (
            ai_health * AI_WEIGHT
            + osm_health * OSM_WEIGHT
        )

    elif ai_health is not None:

        health = ai_health

    elif osm_health is not None:

        health = osm_health

    # --------------------------------------------------------
    # Clamp health
    # --------------------------------------------------------

    if health is not None:

        health = max(
            0.0,
            min(100.0, health)
        )

    # --------------------------------------------------------
    # Condition
    # --------------------------------------------------------

    condition = clean_condition(
        None,
        health
    )

    # --------------------------------------------------------
    # Coverage
    # --------------------------------------------------------

    ai_coverage = (
        ai_count
        / total_segments
        * 100.0
    )

    overall_coverage = (
        (ai_count + osm_count)
        / total_segments
        * 100.0
    )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence = overall_coverage

    # AI observations are more reliable than baseline OSM data.
    if ai_count > 0:
        confidence = min(
            100.0,
            confidence + 10.0
        )

    # --------------------------------------------------------
    # Data status
    # --------------------------------------------------------

    if ai_count == 0 and osm_count == 0:

        data_status = "Insufficient Data"

    elif overall_coverage < 25:

        data_status = "Limited Data"

    elif overall_coverage < 75:

        data_status = "Partial Data"

    else:

        data_status = "Good Coverage"

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    result = {
        "health": (
            round(health, 2)
            if health is not None
            else None
        ),

        "condition": condition,

        "confidence": round(
            confidence,
            2
        ),

        "ai_matches": ai_count,

        "osm_matches": osm_count,

        "ai_coverage": round(
            ai_coverage,
            2
        ),

        "coverage": round(
            overall_coverage,
            2
        ),

        "overall_coverage": round(
            overall_coverage,
            2
        ),

        "total_segments": total_segments,

        "unavailable_segments": unavailable_count,

        "ai_health": (
            round(ai_health, 2)
            if ai_health is not None
            else None
        ),

        "osm_health": (
            round(osm_health, 2)
            if osm_health is not None
            else None
        ),

        "data_status": data_status,

        "ai_match_details": ai_matches,

        "osm_match_details": osm_matches,

        "unavailable_edges": unavailable_segments
    }

    return result


# ============================================================
# ROUTE HEALTH FROM ROUTE OBJECT
# ============================================================

def calculate_route_health_from_route(
    route,
    graph=None,
    ai_segments=None,
    osm_segments=None,
    ai_points=None
):
    """
    Convenience function for callers that already have a route
    dictionary produced by route_generator.py.
    """

    if route is None:
        return calculate_route_health(
            [],
            ai_segments,
            osm_segments,
            graph,
            ai_points
        )

    route_edges = route.get(
        "osm_edges",
        []
    )

    return calculate_route_health(
        route_edges,
        ai_segments,
        osm_segments,
        graph,
        ai_points
    )


# ============================================================
# ROUTE HEALTH SUMMARY
# ============================================================

def summarize_route_health(
    health_result
):
    """
    Produce a compact summary for API/frontend use.
    """

    if not health_result:

        return {
            "health": None,
            "condition": "Insufficient Data",
            "coverage": 0.0,
            "status": "Insufficient Data"
        }

    return {
        "health": health_result.get(
            "health"
        ),

        "condition": health_result.get(
            "condition",
            "Insufficient Data"
        ),

        "coverage": health_result.get(
            "coverage",
            0.0
        ),

        "ai_coverage": health_result.get(
            "ai_coverage",
            0.0
        ),

        "confidence": health_result.get(
            "confidence",
            0.0
        ),

        "status": health_result.get(
            "data_status",
            "Insufficient Data"
        )
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("RoadQuality Route Health Engine")
    print("=" * 60)

    ai_segments, osm_segments, ai_points = (
        load_databases()
    )

    print()
    print("Database loading completed.")
    print(
        f"AI edge records      : {len(ai_segments)}"
    )
    print(
        f"AI coordinate records: {len(ai_points)}"
    )
    print(
        f"OSM records          : {len(osm_segments)}"
    )

    print()
    print(
        "Dynamic spatial matching:"
    )
    print(
        f"Enabled radius: {AI_MATCH_RADIUS_METERS} meters"
    )

    print("=" * 60)