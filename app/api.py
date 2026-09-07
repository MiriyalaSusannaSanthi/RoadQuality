from flask import Flask, request, jsonify
from flask_cors import CORS

import time
import traceback
import requests
import math

import osmnx as ox
from shapely.geometry import LineString

from route_generator import generate_routes

from route_health import (
    load_databases,
    calculate_route_health
)

from route_recommender import recommend_routes


# ============================================================
# ROADQUALITY API SERVER
# ============================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*"
        }
    },
    methods=[
        "GET",
        "POST",
        "OPTIONS"
    ],
    allow_headers=[
        "Content-Type",
        "Authorization"
    ]
)

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return "", 204


# ============================================================
# OSMnx SETTINGS
# ============================================================

try:

    ox.settings.requests_timeout = 60

    ox.settings.use_cache = True

except Exception:

    pass


# ============================================================
# IN-MEMORY OSM GRAPH CACHE
# ============================================================

GRAPH_CACHE = {}

MAX_GRAPH_CACHE_SIZE = 3


# ============================================================
# ROAD CONDITION DATABASE CACHE
# ============================================================

AI_SEGMENTS_CACHE = None

OSM_SEGMENTS_CACHE = None

AI_POINTS_CACHE = None


# ============================================================
# HELPER - TIMING
# ============================================================

def print_step(
    request_id,
    request_start,
    message
):

    elapsed = (
        time.perf_counter()
        - request_start
    )

    print(

        f"[{request_id}] "
        f"[{elapsed:8.2f}s] "
        f"{message}",

        flush=True

    )


# ============================================================
# HELPER - GRAPH CACHE KEY
# ============================================================

def make_graph_cache_key(
    source_lat,
    source_lon,
    destination_lat,
    destination_lon,
    buffer_km
):
    return (
        round(float(source_lat), 4),
        round(float(source_lon), 4),
        round(float(destination_lat), 4),
        round(float(destination_lon), 4),
        round(float(buffer_km), 1)
    )


# ============================================================
# HELPER - STRAIGHT-LINE DISTANCE
# ============================================================

def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0

    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))

    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dlon / 2) ** 2
    )

    return radius * 2 * math.asin(
        math.sqrt(max(0.0, min(1.0, a)))
    )


# ============================================================
# HELPER - DYNAMIC OSM ROAD CORRIDOR
# ============================================================

def get_road_network(
    source_lat,
    source_lon,
    destination_lat,
    destination_lon,
    request_id,
    request_start
):
    """
    Download only a corridor around the requested route instead
    of downloading a large rectangular bounding box.

    This dramatically reduces OSM download size for long routes.
    """

    straight_distance_km = haversine_km(
        source_lat,
        source_lon,
        destination_lat,
        destination_lon
    )

    # Adaptive corridor width.
    #
    # Short routes: about 2 km
    # Medium routes: about 3-6 km
    # Long routes: capped at 10 km
    #
    # This is deliberately a corridor, not a giant rectangle.
    buffer_km = max(
        2.0,
        min(
            10.0,
            straight_distance_km * 0.05
        )
    )

    cache_key = make_graph_cache_key(
        source_lat,
        source_lon,
        destination_lat,
        destination_lon,
        buffer_km
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if cache_key in GRAPH_CACHE:

        print_step(
            request_id,
            request_start,
            "STEP 5A - Using cached OSM road corridor"
        )

        return GRAPH_CACHE[cache_key]

    print_step(
        request_id,
        request_start,
        "STEP 5A - Downloading dynamic OSM road corridor"
    )

    print(
        f"\nStraight-line distance: {straight_distance_km:.2f} km",
        flush=True
    )

    print(
        f"OSM corridor buffer: {buffer_km:.2f} km",
        flush=True
    )

    network_start = time.perf_counter()

    # --------------------------------------------------------
    # Convert approximate km buffer to degrees.
    #
    # This is suitable for a route corridor at the geographic
    # scale used by RoadQuality.
    # --------------------------------------------------------

    buffer_lat = buffer_km / 111.0

    mean_lat = (
        float(source_lat)
        + float(destination_lat)
    ) / 2.0

    cos_lat = max(
        0.20,
        abs(math.cos(math.radians(mean_lat)))
    )

    buffer_lon = buffer_km / (
        111.0 * cos_lat
    )

    # --------------------------------------------------------
    # Build straight source -> destination corridor.
    # --------------------------------------------------------

    route_line = LineString(
        [
            (
                float(source_lon),
                float(source_lat)
            ),
            (
                float(destination_lon),
                float(destination_lat)
            )
        ]
    )

    # Use the larger geographic buffer so both latitude and
    # longitude directions have enough room.
    buffer_degrees = max(
        buffer_lat,
        buffer_lon
    )

    corridor_polygon = route_line.buffer(
        buffer_degrees
    )

    print(
        "Downloading OSM network inside route corridor...",
        flush=True
    )

    try:

        G = ox.graph_from_polygon(
            corridor_polygon,
            network_type="drive",
            simplify=True
        )

    except Exception as first_error:

        print(
            "\nCorridor OSM download failed:",
            str(first_error),
            flush=True
        )

        # ----------------------------------------------------
        # Fallback: rectangular bbox.
        # Kept only as a safety net for unusual OSM areas.
        # ----------------------------------------------------

        fallback_padding = min(
            0.05,
            max(
                0.015,
                buffer_degrees
            )
        )

        north = (
            max(
                float(source_lat),
                float(destination_lat)
            )
            + fallback_padding
        )

        south = (
            min(
                float(source_lat),
                float(destination_lat)
            )
            - fallback_padding
        )

        east = (
            max(
                float(source_lon),
                float(destination_lon)
            )
            + fallback_padding
        )

        west = (
            min(
                float(source_lon),
                float(destination_lon)
            )
            - fallback_padding
        )

        print(
            "Trying compact bbox fallback...",
            flush=True
        )

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

    network_time = (
        time.perf_counter()
        - network_start
    )

    print(
        f"\nOSM road network ready in "
        f"{network_time:.2f} seconds",
        flush=True
    )

    print(
        "Nodes:",
        len(G.nodes),
        flush=True
    )

    print(
        "Edges:",
        len(G.edges),
        flush=True
    )

    if len(G.nodes) == 0:

        raise RuntimeError(
            "OSM returned an empty road network."
        )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if len(GRAPH_CACHE) >= MAX_GRAPH_CACHE_SIZE:

        oldest_key = next(
            iter(GRAPH_CACHE)
        )

        del GRAPH_CACHE[oldest_key]

    GRAPH_CACHE[cache_key] = G

    print(
        "OSM graph stored in memory cache.",
        flush=True
    )

    return G


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({

        "status":
            "success",

        "message":
            "RoadQuality API is running",

        "service":
            "AI + OSM Road Condition Route Engine",

        "version":
            "2.0",

        "graph_cache":
            len(GRAPH_CACHE)

    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return jsonify({

        "status":
            "ok",

        "message":
            "RoadQuality Flask server is running",

        "service":
            "AI + OSM Road Condition Route Engine",

        "graph_cache":
            len(GRAPH_CACHE),

        "database_cache":
            (
                AI_SEGMENTS_CACHE is not None
                and
                OSM_SEGMENTS_CACHE is not None
                and
                AI_POINTS_CACHE is not None
            )

    })


# ============================================================
# LOCATION AUTOCOMPLETE
# ============================================================

@app.get("/suggest")
def suggest_locations():

    query = request.args.get(
        "q",
        ""
    ).strip()


    # --------------------------------------------------------
    # Minimum query length
    # --------------------------------------------------------

    if len(query) < 2:

        return jsonify({

            "suggestions":
                []

        })


    try:

        # ----------------------------------------------------
        # QUERY NOMINATIM
        # ----------------------------------------------------

        response = requests.get(

            "https://nominatim.openstreetmap.org/search",

            params={

                "q":
                    query,

                "format":
                    "json",

                "addressdetails":
                    1,

                "limit":
                    8,

                "countrycodes":
                    "in"

            },

            headers={

                "User-Agent":
                    "RoadQuality/1.0 (route recommendation project)"

            },

            timeout=8

        )


        response.raise_for_status()


        results = response.json()


        suggestions = []


        # ----------------------------------------------------
        # FORMAT RESULTS
        # ----------------------------------------------------

        for place in results:

            try:

                latitude = float(

                    place["lat"]

                )

                longitude = float(

                    place["lon"]

                )

            except (

                ValueError,

                TypeError,

                KeyError

            ):

                continue


            display_name = (

                place.get(

                    "display_name",

                    ""

                )

                .strip()

            )


            if not display_name:

                continue


            suggestions.append({

                "display_name":
                    display_name,

                "latitude":
                    latitude,

                "longitude":
                    longitude

            })


        return jsonify({

            "status":
                "success",

            "suggestions":
                suggestions

        })


    except Exception as e:

        print(

            "Suggestion error:",

            str(e),

            flush=True

        )


        return jsonify({

            "status":
                "success",

            "suggestions":
                []

        })


# ============================================================
# CURRENT LOCATION REVERSE GEOCODING
# ============================================================

@app.get("/reverse")
def reverse_location():

    latitude = request.args.get(

        "lat",

        type=float

    )


    longitude = request.args.get(

        "lon",

        type=float

    )


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if (

        latitude is None

        or

        longitude is None

    ):

        return jsonify({

            "status":
                "error",

            "message":
                "Latitude and longitude are required."

        }), 400


    # --------------------------------------------------------
    # VALID LATITUDE / LONGITUDE RANGE
    # --------------------------------------------------------

    if not (

        -90 <= latitude <= 90

        and

        -180 <= longitude <= 180

    ):

        return jsonify({

            "status":
                "error",

            "message":
                "Invalid latitude or longitude."

        }), 400


    try:

        # ----------------------------------------------------
        # REVERSE GEOCODING
        # ----------------------------------------------------

        response = requests.get(

            "https://nominatim.openstreetmap.org/reverse",

            params={

                "lat":
                    latitude,

                "lon":
                    longitude,

                "format":
                    "json",

                "addressdetails":
                    1,

                "zoom":
                    18

            },

            headers={

                "User-Agent":
                    "RoadQuality/1.0 (route recommendation project)"

            },

            timeout=8

        )


        response.raise_for_status()


        result = response.json()


        display_name = (

            result.get(

                "display_name",

                ""

            )

            .strip()

        )


        return jsonify({

            "status":
                "success",

            "display_name":
                display_name,

            "latitude":
                latitude,

            "longitude":
                longitude

        })


    except Exception as e:

        print(

            "Reverse geocoding error:",

            str(e),

            flush=True

        )


        return jsonify({

            "status":
                "error",

            "message":
                "Could not determine current location.",

            "details":
                str(e)

        }), 500


# ============================================================
# ROUTE ANALYSIS
# ============================================================

@app.route(
    "/analyze",
    methods=["POST"]
)
def analyze_route():

    request_start = time.perf_counter()


    request_id = (

        f"RQ-"
        f"{int(time.time() * 1000) % 1000000}"

    )


    try:

        # ====================================================
        # STEP 1 - REQUEST RECEIVED
        # ====================================================

        print_step(

            request_id,

            request_start,

            "STEP 1 - /analyze request received"

        )


        # ====================================================
        # STEP 2 - READ JSON
        # ====================================================

        data = request.get_json(

            silent=True

        )


        print_step(

            request_id,

            request_start,

            "STEP 2 - JSON request body read"

        )


        if not data:

            return jsonify({

                "status":
                    "error",

                "message":
                    "Request body is required.",

                "request_id":
                    request_id

            }), 400


        # ====================================================
        # READ INPUTS
        # ====================================================

        source_place = str(

            data.get(

                "source",

                ""

            )

        ).strip()


        destination_place = str(

            data.get(

                "destination",

                ""

            )

        ).strip()


        preference = str(

            data.get(

                "preference",

                "balanced"

            )

        ).strip().lower()


        # ====================================================
        # VALIDATION
        # ====================================================

        if not source_place:

            return jsonify({

                "status":
                    "error",

                "message":
                    "Source location is required.",

                "request_id":
                    request_id

            }), 400


        if not destination_place:

            return jsonify({

                "status":
                    "error",

                "message":
                    "Destination location is required.",

                "request_id":
                    request_id

            }), 400


        valid_preferences = [

            "balanced",

            "road_condition",

            "fastest"

        ]


        if preference not in valid_preferences:

            preference = "balanced"


        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "ROADQUALITY API REQUEST",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        print(

            "Request ID:",

            request_id,

            flush=True

        )


        print(

            "Source:",

            source_place,

            flush=True

        )


        print(

            "Destination:",

            destination_place,

            flush=True

        )


        print(

            "Preference:",

            preference,

            flush=True

        )


        print_step(

            request_id,

            request_start,

            "STEP 3 - Request validated"

        )


        # ====================================================
        # STEP 4 - GEOCODING
        # ====================================================

        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "GEOCODING",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        # ----------------------------------------------------
        # SOURCE
        # ----------------------------------------------------

        print(

            "\nLocating source...",

            flush=True

        )


        source_geo_start = time.perf_counter()


        try:

            source_lat, source_lon = ox.geocode(

                source_place

            )


        except Exception as e:

            print(

                "SOURCE GEOCODING ERROR:",

                str(e),

                flush=True

            )


            return jsonify({

                "status":
                    "error",

                "message":
                    "Could not locate source.",

                "details":
                    str(e),

                "request_id":
                    request_id

            }), 400


        source_geo_time = (

            time.perf_counter()

            - source_geo_start

        )


        print(

            f"Source geocoding completed "

            f"in {source_geo_time:.2f} seconds",

            flush=True

        )


        # ----------------------------------------------------
        # DESTINATION
        # ----------------------------------------------------

        print(

            "\nLocating destination...",

            flush=True

        )


        destination_geo_start = (

            time.perf_counter()

        )


        try:

            destination_lat, destination_lon = (

                ox.geocode(

                    destination_place

                )

            )


        except Exception as e:

            print(

                "DESTINATION GEOCODING ERROR:",

                str(e),

                flush=True

            )


            return jsonify({

                "status":
                    "error",

                "message":
                    "Could not locate destination.",

                "details":
                    str(e),

                "request_id":
                    request_id

            }), 400


        destination_geo_time = (

            time.perf_counter()

            - destination_geo_start

        )


        print(

            f"Destination geocoding completed "

            f"in {destination_geo_time:.2f} seconds",

            flush=True

        )


        print(

            f"\nSource coordinates: "

            f"{source_lat:.6f}, "

            f"{source_lon:.6f}",

            flush=True

        )


        print(

            f"Destination coordinates: "

            f"{destination_lat:.6f}, "

            f"{destination_lon:.6f}",

            flush=True

        )


        print_step(

            request_id,

            request_start,

            "STEP 4 - Geocoding completed"

        )


        # ====================================================
        # STEP 5 - DYNAMIC OSM ROAD CORRIDOR
        # ====================================================

        print(
            "\n" + "=" * 70,
            flush=True
        )

        print(
            "GETTING DYNAMIC ROAD NETWORK",
            flush=True
        )

        print(
            "=" * 70,
            flush=True
        )

        try:

            G = get_road_network(
                source_lat,
                source_lon,
                destination_lat,
                destination_lon,
                request_id,
                request_start
            )

        except Exception as e:

            traceback.print_exc()

            return jsonify({
                "status":
                    "error",

                "message":
                    "Could not load road network.",

                "details":
                    str(e),

                "request_id":
                    request_id

            }), 500

# ====================================================
        # STEP 6 - LOAD ROAD CONDITION DATABASES
        # ====================================================

        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "LOADING ROAD CONDITION DATABASE",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        global AI_SEGMENTS_CACHE

        global OSM_SEGMENTS_CACHE

        global AI_POINTS_CACHE


        database_start = time.perf_counter()


        if (

            AI_SEGMENTS_CACHE is not None

            and

            OSM_SEGMENTS_CACHE is not None

            and

            AI_POINTS_CACHE is not None

        ):

            ai_segments = AI_SEGMENTS_CACHE

            osm_segments = OSM_SEGMENTS_CACHE

            ai_points = AI_POINTS_CACHE


            print(

                "Using cached road condition databases.",

                flush=True

            )


        else:

            database_result = load_databases()

            # New route_health.py returns:
            #   AI edge records
            #   OSM records
            #   geographic AI observations
            #
            # Keep a compatibility fallback for older versions.

            if isinstance(database_result, tuple) and len(database_result) >= 3:

                ai_segments = database_result[0]

                osm_segments = database_result[1]

                ai_points = database_result[2]

            else:

                ai_segments = database_result[0]

                osm_segments = database_result[1]

                ai_points = []


            AI_SEGMENTS_CACHE = ai_segments

            OSM_SEGMENTS_CACHE = osm_segments

            AI_POINTS_CACHE = ai_points


            print(

                "Road condition databases loaded "

                "and cached.",

                flush=True

            )


        database_time = (

            time.perf_counter()

            - database_start

        )


        print(

            f"Database operation completed "

            f"in {database_time:.2f} seconds",

            flush=True

        )


        print(

            "\nAI road-condition segments:",

            len(ai_segments),

            flush=True

        )


        print(

            "OSM baseline segments:",

            len(osm_segments),

            flush=True

        )


        print(

            "AI geographic observations:",

            len(ai_points),

            flush=True

        )


        print_step(

            request_id,

            request_start,

            "STEP 6 - Road condition databases ready"

        )


        # ====================================================
        # STEP 7 - GENERATE CANDIDATE ROUTES
        # ====================================================

        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "GENERATING CANDIDATE ROUTES",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        route_generation_start = (

            time.perf_counter()

        )


        try:

            routes = generate_routes(

                G,

                source_lat,

                source_lon,

                destination_lat,

                destination_lon,

                number_of_routes=3

            )


        except Exception as e:

            print(

                "\nROUTE GENERATION ERROR:",

                str(e),

                flush=True

            )


            traceback.print_exc()


            return jsonify({

                "status":
                    "error",

                "message":
                    "Could not generate candidate routes.",

                "details":
                    str(e),

                "request_id":
                    request_id

            }), 500


        route_generation_time = (

            time.perf_counter()

            - route_generation_start

        )


        if not routes:

            return jsonify({

                "status":
                    "error",

                "message":
                    "No routes could be generated.",

                "request_id":
                    request_id

            }), 404


        print(

            f"\nCandidate route generation completed "

            f"in {route_generation_time:.2f} seconds",

            flush=True

        )


        print(

            "Candidate routes:",

            len(routes),

            flush=True

        )


        for route in routes:

            print(

                f"  {route.get('name', 'Route')} | "

                f"{float(route.get('distance', 0)):.2f} km | "

                f"{float(route.get('travel_time', 0)):.2f} min",

                flush=True

            )


        print_step(

            request_id,

            request_start,

            "STEP 7 - Candidate routes generated"

        )


        # ====================================================
        # STEP 8 - ASSESS ROAD CONDITION
        # ====================================================

        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "ASSESSING ROAD CONDITION",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        evaluated_routes = []


        health_start = time.perf_counter()


        for route in routes:

            route_name = route.get(

                "name",

                "Route"

            )


            print(

                f"\nAssessing {route_name}...",

                flush=True

            )


            route_edges = route.get(

                "osm_edges",

                []

            )


            print(

                f"OSM edges: {len(route_edges)}",

                flush=True

            )


            try:

                health_result = calculate_route_health(

                    route_edges,

                    ai_segments=ai_segments,

                    osm_segments=osm_segments,

                    graph=G,

                    ai_points=ai_points

                )


            except Exception as e:

                print(

                    f"ROAD HEALTH ERROR for "

                    f"{route_name}: {e}",

                    flush=True

                )


                traceback.print_exc()


                health_result = {

                    "health":
                        None,

                    "condition":
                        "Insufficient Data",

                    "matched_observations":
                        0,

                    "observation_count":
                        0,

                    "ai_segment_count":
                        0,

                    "osm_segment_count":
                        0,

                    "unavailable_segment_count":
                        len(route_edges),

                    "ai_coverage":
                        0.0,

                    "coverage":
                        0.0,

                    "confidence":
                        0.0,

                    "ai_matches":
                        [],

                    "osm_matches":
                        [],

                    "observations":
                        []

                }


            health = health_result.get(

                "health"

            )


            condition = health_result.get(

                "condition",

                "Unknown"

            )


            if health is None:

                health_value = None

                condition = "Insufficient Data"

            else:

                try:

                    health_value = round(

                        float(health),

                        2

                    )

                except (

                    ValueError,

                    TypeError

                ):

                    health_value = None

                    condition = "Insufficient Data"


            ai_coverage = health_result.get(

                "ai_coverage",

                0.0

            )


            overall_coverage = health_result.get(

                "coverage",

                0.0

            )


            try:

                ai_coverage = float(

                    ai_coverage

                )

            except (

                ValueError,

                TypeError

            ):

                ai_coverage = 0.0


            try:

                overall_coverage = float(

                    overall_coverage

                )

            except (

                ValueError,

                TypeError

            ):

                overall_coverage = 0.0


            confidence = health_result.get(

                "confidence",

                overall_coverage

            )


            try:

                confidence = float(

                    confidence

                )

            except (

                ValueError,

                TypeError

            ):

                confidence = overall_coverage


            confidence = max(

                0.0,

                min(

                    100.0,

                    confidence

                )

            )


            ai_matches_result = health_result.get(
                "ai_matches",
                []
            )

            osm_matches_result = health_result.get(
                "osm_matches",
                []
            )

            # ``route_health.py`` may return either a detailed match list
            # or a numeric match count depending on the installed version.
            # Normalize both forms here so the API never crashes on len(int).
            def _match_count(value):
                if value is None:
                    return 0
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                try:
                    return len(value)
                except TypeError:
                    return 0

            ai_match_count = _match_count(ai_matches_result)
            osm_match_count = _match_count(osm_matches_result)
            matched_count = ai_match_count + osm_match_count

            evaluated_route = {

                **route,

                "road_health":
                    health_value,

                "condition":
                    condition,

                "matched_observations":
                    matched_count,

                "observation_count":
                    matched_count,

                "ai_segment_count":
                    ai_match_count,

                "osm_segment_count":
                    osm_match_count,

                "unavailable_segment_count":
                    int(
                        health_result.get(
                            "unavailable_segments",
                            health_result.get(
                                "unavailable_segment_count",
                                0
                            )
                        )
                    ),

                "ai_coverage":
                    round(
                        ai_coverage,
                        2
                    ),

                "coverage":
                    round(
                        overall_coverage,
                        2
                    ),

                "confidence":
                    round(
                        confidence,
                        2
                    ),

                "ai_matches":
                    ai_matches_result,

                "osm_matches":
                    osm_matches_result,

                "health_observations":
                    (
                        ai_matches_result
                        + osm_matches_result
                        if isinstance(ai_matches_result, list)
                        and isinstance(osm_matches_result, list)
                        else matched_count
                    ),

                "data_status":
                    health_result.get(
                        "data_status",
                        "Insufficient Data"
                    )
            }


            evaluated_routes.append(

                evaluated_route

            )


            if health_value is None:

                print(

                    f"{route_name} | "

                    f"Health: Insufficient Data | "

                    f"Coverage: "

                    f"{overall_coverage:.2f}%",

                    flush=True

                )

            else:

                print(

                    f"{route_name} | "

                    f"Health: "

                    f"{health_value:.2f} | "

                    f"Condition: "

                    f"{condition} | "

                    f"Coverage: "

                    f"{overall_coverage:.2f}%",

                    flush=True

                )


        health_time = (

            time.perf_counter()

            - health_start

        )


        print(

            f"\nRoad condition assessment completed "

            f"in {health_time:.2f} seconds",

            flush=True

        )


        print_step(

            request_id,

            request_start,

            "STEP 8 - All candidate routes evaluated"

        )


        # ====================================================
        # STEP 9 - RECOMMEND ROUTES
        # ====================================================

        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "RECOMMENDING BEST ROUTE",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        recommendation_start = (

            time.perf_counter()

        )


        try:

            ranked_routes = recommend_routes(

                evaluated_routes,

                preference

            )


        except Exception as e:

            print(

                "\nROUTE RECOMMENDATION ERROR:",

                str(e),

                flush=True

            )


            traceback.print_exc()


            return jsonify({

                "status":
                    "error",

                "message":
                    "Could not rank routes.",

                "details":
                    str(e),

                "request_id":
                    request_id

            }), 500


        recommendation_time = (

            time.perf_counter()

            - recommendation_start

        )


        if not ranked_routes:

            return jsonify({

                "status":
                    "error",

                "message":
                    "Could not rank routes.",

                "request_id":
                    request_id

            }), 500


        print(

            f"Route recommendation completed "

            f"in {recommendation_time:.2f} seconds",

            flush=True

        )


        print_step(

            request_id,

            request_start,

            "STEP 9 - Routes ranked by preference"

        )


        # ====================================================
        # PRINT ROUTE SCORES
        # ====================================================

        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "ROUTE SCORES",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        for route in ranked_routes:

            health_display = (

                "N/A"

                if route.get("road_health") is None

                else
                f"{float(route.get('road_health', 0)):.2f}"

            )


            print(

                f"{route.get('name', 'Route')} | "

                f"Health: "

                f"{health_display} | "

                f"Distance: "

                f"{float(route.get('distance', 0)):.2f} km | "

                f"Time: "

                f"{float(route.get('travel_time', 0)):.2f} min | "

                f"Score: "

                f"{float(route.get('final_score', 0)):.2f}",

                flush=True

            )


        print(

            "=" * 70,

            flush=True

        )


        # ====================================================
        # RECOMMENDED ROUTE
        # ====================================================

        recommended = ranked_routes[0]


        print(

            "\nRecommended route:",

            recommended.get(

                "name",

                ""

            ),

            flush=True

        )


        # ====================================================
        # FIND ORIGINAL ROUTE INDEX
        # ====================================================

        recommended_index = 0


        for i, route in enumerate(routes):

            if (

                route.get("name")

                ==

                recommended.get("name")

            ):

                recommended_index = i

                break


        # ====================================================
        # PREPARE ROUTES FOR WEB / MOBILE
        # ====================================================

        route_results = []


        MAX_ROUTE_POINTS = 250


        for route in ranked_routes:

            coordinates = route.get(

                "coordinates",

                []

            )


            # ------------------------------------------------
            # CLEAN COORDINATES
            # ------------------------------------------------

            route_coordinates = []


            for point in coordinates:

                try:

                    if (

                        not isinstance(

                            point,

                            (list, tuple)

                        )

                        or

                        len(point) < 2

                    ):

                        continue


                    lat = float(

                        point[0]

                    )


                    lon = float(

                        point[1]

                    )


                    route_coordinates.append([

                        lat,

                        lon

                    ])


                except (

                    ValueError,

                    TypeError,

                    IndexError

                ):

                    continue


            # ------------------------------------------------
            # LIMIT POINTS
            # ------------------------------------------------

            if (

                len(route_coordinates)

                >

                MAX_ROUTE_POINTS

            ):

                last_index = (

                    len(route_coordinates)

                    - 1

                )


                sampled_coordinates = []


                for i in range(

                    MAX_ROUTE_POINTS

                ):

                    index = round(

                        i

                        *

                        last_index

                        /

                        (

                            MAX_ROUTE_POINTS

                            - 1

                        )

                    )


                    sampled_coordinates.append(

                        route_coordinates[index]

                    )


                route_coordinates = (

                    sampled_coordinates

                )


            # ------------------------------------------------
            # HEALTH
            # ------------------------------------------------

            route_health = route.get(

                "road_health"

            )


            if route_health is not None:

                try:

                    route_health = round(

                        float(route_health),

                        2

                    )

                except (

                    ValueError,

                    TypeError

                ):

                    route_health = None


            # ------------------------------------------------
            # SCORE
            # ------------------------------------------------

            final_score = route.get(

                "final_score",

                route.get(

                    "score",

                    0

                )

            )


            try:

                final_score = float(

                    final_score

                )

            except (

                ValueError,

                TypeError

            ):

                final_score = 0.0


            # ------------------------------------------------
            # CONFIDENCE
            # ------------------------------------------------

            confidence = route.get(

                "confidence",

                route.get(

                    "coverage",

                    0

                )

            )


            try:

                confidence = float(

                    confidence

                )

            except (

                ValueError,

                TypeError

            ):

                confidence = 0.0


            # ------------------------------------------------
            # SCORE BREAKDOWN
            # ------------------------------------------------

            score_breakdown = route.get(

                "score_breakdown",

                {}

            )


            if not isinstance(

                score_breakdown,

                dict

            ):

                score_breakdown = {}


            # ------------------------------------------------
            # FINAL ROUTE OBJECT
            # ------------------------------------------------

            route_results.append({

                "name":
                    route.get(

                        "name",

                        ""

                    ),


                "rank":
                    int(

                        route.get(

                            "rank",

                            0

                        )

                    ),


                "distance":
                    float(

                        route.get(

                            "distance",

                            0

                        )

                    ),


                "travel_time":
                    float(

                        route.get(

                            "travel_time",

                            0

                        )

                    ),


                "road_health":
                    route_health,


                "condition":
                    route.get(

                        "condition",

                        "Unknown"

                    ),


                "score":
                    final_score,


                "final_score":
                    final_score,


                # ==================================================
                # SCORING DETAILS
                # ==================================================

                "distance_score":
                    float(

                        route.get(

                            "distance_score",

                            0

                        )

                    ),


                "time_score":
                    float(

                        route.get(

                            "time_score",

                            0

                        )

                    ),


                "coverage_score":
                    float(

                        route.get(

                            "coverage_score",

                            route.get(

                                "coverage",

                                0

                            )

                        )

                    ),


                "score_breakdown":
                    score_breakdown,


                "recommendation_reason":
                    route.get(

                        "recommendation_reason",

                        ""

                    ),


                # ==================================================
                # ROAD CONDITION DATA
                # ==================================================

                "matched_observations":
                    int(

                        route.get(

                            "matched_observations",

                            0

                        )

                    ),


                "observation_count":
                    int(

                        route.get(

                            "observation_count",

                            0

                        )

                    ),


                "ai_segment_count":
                    int(

                        route.get(

                            "ai_segment_count",

                            0

                        )

                    ),


                "osm_segment_count":
                    int(

                        route.get(

                            "osm_segment_count",

                            0

                        )

                    ),


                "unavailable_segment_count":
                    int(

                        route.get(

                            "unavailable_segment_count",

                            0

                        )

                    ),


                "ai_coverage":
                    float(

                        route.get(

                            "ai_coverage",

                            0

                        )

                    ),


                "coverage":
                    float(

                        route.get(

                            "coverage",

                            0

                        )

                    ),


                "confidence":
                    confidence,


                # ==================================================
                # ROUTE COORDINATES
                # ==================================================

                "coordinates":
                    route_coordinates

            })


        # ====================================================
        # RECOMMENDED ROUTE DATA
        # ====================================================

        recommended_health = (

            recommended.get(

                "road_health"

            )

        )


        if recommended_health is not None:

            try:

                recommended_health = float(

                    recommended_health

                )

            except (

                ValueError,

                TypeError

            ):

                recommended_health = None


        recommended_confidence = (

            recommended.get(

                "confidence",

                recommended.get(

                    "coverage",

                    0

                )

            )

        )


        try:

            recommended_confidence = float(

                recommended_confidence

            )

        except (

            ValueError,

            TypeError

        ):

            recommended_confidence = 0.0


        recommended_score = (

            recommended.get(

                "final_score",

                recommended.get(

                    "score",

                    0

                )

            )

        )


        try:

            recommended_score = float(

                recommended_score

            )

        except (

            ValueError,

            TypeError

        ):

            recommended_score = 0.0


        # ====================================================
        # FINAL RESPONSE
        # ====================================================

        total_processing_time = (

            time.perf_counter()

            - request_start

        )


        response = {

            "status":
                "success",


            # ==================================================
            # SOURCE
            # ==================================================

            "source": {

                "name":
                    source_place,

                "latitude":
                    float(source_lat),

                "longitude":
                    float(source_lon)

            },


            # ==================================================
            # DESTINATION
            # ==================================================

            "destination": {

                "name":
                    destination_place,

                "latitude":
                    float(destination_lat),

                "longitude":
                    float(destination_lon)

            },


            # ==================================================
            # USER PREFERENCE
            # ==================================================

            "preference":
                preference,


            # ==================================================
            # RECOMMENDED ROUTE
            # ==================================================

            "recommended_route":
                recommended.get(

                    "name",

                    ""

                ),


            "recommended_route_index":
                recommended_index,


            # ==================================================
            # ROAD HEALTH
            # ==================================================

            "road_health":
                recommended_health,


            "condition":
                recommended.get(

                    "condition",

                    "Unknown"

                ),


            # ==================================================
            # ROUTE METRICS
            # ==================================================

            "distance":
                float(

                    recommended.get(

                        "distance",

                        0

                    )

                ),


            "travel_time":
                float(

                    recommended.get(

                        "travel_time",

                        0

                    )

                ),


            # ==================================================
            # RECOMMENDATION SCORE
            # ==================================================

            "score":
                recommended_score,


            # ==================================================
            # CONFIDENCE / DATA COVERAGE
            # ==================================================

            "confidence":
                recommended_confidence,


            "ai_segments":
                int(

                    recommended.get(

                        "ai_segment_count",

                        0

                    )

                ),


            "osm_segments":
                int(

                    recommended.get(

                        "osm_segment_count",

                        0

                    )

                ),


            "unavailable_segments":
                int(

                    recommended.get(

                        "unavailable_segment_count",

                        0

                    )

                ),


            "ai_coverage":
                float(

                    recommended.get(

                        "ai_coverage",

                        0

                    )

                ),


            "overall_coverage":
                float(

                    recommended.get(

                        "coverage",

                        0

                    )

                ),


            # ==================================================
            # WHY THIS ROUTE WAS SELECTED
            # ==================================================

            "recommendation_reason":
                recommended.get(

                    "recommendation_reason",

                    ""

                ),


            "score_breakdown":
                recommended.get(

                    "score_breakdown",

                    {}

                ),


            # ==================================================
            # ALL ROUTES
            # ==================================================

            "routes":
                route_results,


            # ==================================================
            # DEBUG / PERFORMANCE
            # ==================================================

            "processing_time_seconds":
                round(

                    total_processing_time,

                    2

                ),


            "request_id":
                request_id

        }


        # ====================================================
        # FINAL LOG
        # ====================================================

        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "ROADQUALITY API RESPONSE",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        print(

            "Request ID:",

            request_id,

            flush=True

        )


        print(

            "Recommended:",

            response["recommended_route"],

            flush=True

        )


        print(

            "Health:",

            (

                "Insufficient Data"

                if response["road_health"] is None

                else response["road_health"]

            ),

            flush=True

        )


        print(

            "Condition:",

            response["condition"],

            flush=True

        )


        print(

            "Distance:",

            response["distance"],

            "km",

            flush=True

        )


        print(

            "Time:",

            response["travel_time"],

            "min",

            flush=True

        )


        print(

            "Score:",

            response["score"],

            flush=True

        )


        print(

            "Confidence:",

            response["confidence"],

            flush=True

        )


        print(

            "Routes returned:",

            len(response["routes"]),

            flush=True

        )


        print(

            "Processing time:",

            response[

                "processing_time_seconds"

            ],

            "seconds",

            flush=True

        )


        # ====================================================
        # PRINT ROUTE DETAILS
        # ====================================================

        for route in response["routes"]:

            route_health_display = (

                "Insufficient Data"

                if route["road_health"] is None

                else
                f"{route['road_health']:.2f}"

            )


            print(

                f"Route: {route['name']} | "

                f"Rank: {route['rank']} | "

                f"Health: "

                f"{route_health_display} | "

                f"Distance: "

                f"{route['distance']:.2f} km | "

                f"Time: "

                f"{route['travel_time']:.2f} min | "

                f"Score: "

                f"{route['final_score']:.2f} | "

                f"Coverage: "

                f"{route['coverage']:.2f}% | "

                f"GPS points: "

                f"{len(route['coordinates'])}",

                flush=True

            )


        print(

            "=" * 70,

            flush=True

        )


        print(

            f"\nSUCCESS - /analyze completed "

            f"in {total_processing_time:.2f} seconds",

            flush=True

        )


        # ====================================================
        # RETURN JSON
        # ====================================================

        return jsonify(

            response

        )


    # ========================================================
    # GLOBAL ERROR HANDLER
    # ========================================================

    except Exception as e:

        total_processing_time = (

            time.perf_counter()

            - request_start

        )


        print(

            "\n" + "=" * 70,

            flush=True

        )


        print(

            "ROADQUALITY API ERROR",

            flush=True

        )


        print(

            "=" * 70,

            flush=True

        )


        print(

            "Request ID:",

            request_id,

            flush=True

        )


        print(

            f"Failed after "

            f"{total_processing_time:.2f} seconds",

            flush=True

        )


        print(

            "Error:",

            str(e),

            flush=True

        )


        traceback.print_exc()


        print(

            "=" * 70,

            flush=True

        )


        return jsonify({

            "status":
                "error",

            "message":
                "RoadQuality analysis failed.",

            "details":
                str(e),

            "request_id":
                request_id,

            "processing_time_seconds":
                round(

                    total_processing_time,

                    2

                )

        }), 500


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print(

        "=" * 70

    )


    print(

        "ROADQUALITY API SERVER"

    )


    print(

        "=" * 70

    )


    print(

        "\nServer starting..."

    )


    print(

        "\nDesktop / Browser:"

    )


    print(

        "http://127.0.0.1:5000"

    )


    print(

        "\nAndroid Emulator:"

    )


    print(

        "http://10.0.2.2:5000"

    )


    print(

        "\nHealth:"

    )


    print(

        "http://127.0.0.1:5000/health"

    )


    print(

        "\nAutocomplete:"

    )


    print(

        "http://127.0.0.1:5000/suggest?q=Vijay"

    )


    print(

        "\nReverse Geocoding:"

    )


    print(

        "http://127.0.0.1:5000/reverse?lat=16.5062&lon=80.6480"

    )


    print(

        "=" * 70

    )


    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False,

        threaded=True

    )