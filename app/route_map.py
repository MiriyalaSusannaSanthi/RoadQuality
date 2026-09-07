import os
import folium


# ============================================================
# ROADQUALITY - ROUTE MAP GENERATOR V2
# ============================================================


def _condition_from_health(health):
    """
    Convert numerical road health into a readable condition.
    """

    if health is None:
        return "Unknown"

    try:
        health = float(health)
    except (TypeError, ValueError):
        return "Unknown"

    if health >= 80:
        return "Good"
    elif health >= 60:
        return "Moderate"
    elif health >= 40:
        return "Poor"
    else:
        return "Very Poor"


def _condition_color(condition):
    """
    Return map color based on road condition.
    """

    condition = str(condition).lower()

    if "good" in condition:
        return "green"

    if "moderate" in condition:
        return "orange"

    if "poor" in condition:
        return "red"

    return "gray"


def _safe_float(value, default=None):
    """
    Safely convert a value to float.
    """

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_segment_lookup(
    ai_segments=None,
    osm_segments=None
):
    """
    Build a lookup table for:

        (u, v, key)

    -> road information
    """

    lookup = {}

    # --------------------------------------------------------
    # AI SEGMENTS
    # --------------------------------------------------------

    if ai_segments:

        if isinstance(ai_segments, dict):

            iterator = ai_segments.items()

            for edge, data in iterator:

                if not isinstance(edge, tuple):
                    continue

                if len(edge) == 2:
                    u, v = edge
                    key = 0
                else:
                    u, v, key = edge

                if not isinstance(data, dict):
                    data = {
                        "health_score": data
                    }

                health = _safe_float(
                    data.get(
                        "health_score",
                        data.get(
                            "road_health_score"
                        )
                    )
                )

                condition = data.get(
                    "condition",
                    _condition_from_health(health)
                )

                lookup[
                    (str(u), str(v), str(key))
                ] = {
                    "health": health,
                    "condition": condition,
                    "source": "AI",
                    "image": data.get("image"),
                    "confidence": data.get(
                        "confidence"
                    )
                }

        else:

            for item in ai_segments:

                if not isinstance(item, dict):
                    continue

                u = item.get("u")
                v = item.get("v")
                key = item.get("key", 0)

                if u is None or v is None:
                    continue

                health = _safe_float(
                    item.get(
                        "health_score",
                        item.get(
                            "road_health_score"
                        )
                    )
                )

                condition = item.get(
                    "condition",
                    _condition_from_health(health)
                )

                lookup[
                    (str(u), str(v), str(key))
                ] = {
                    "health": health,
                    "condition": condition,
                    "source": "AI",
                    "image": item.get("image"),
                    "confidence": item.get(
                        "confidence"
                    )
                }

    # --------------------------------------------------------
    # OSM BASELINE SEGMENTS
    # --------------------------------------------------------

    if osm_segments:

        if isinstance(osm_segments, dict):

            iterator = osm_segments.items()

            for edge, data in iterator:

                if not isinstance(edge, tuple):
                    continue

                if len(edge) == 2:
                    u, v = edge
                    key = 0
                else:
                    u, v, key = edge

                if not isinstance(data, dict):
                    data = {
                        "health_score": data
                    }

                health = _safe_float(
                    data.get(
                        "health_score",
                        data.get(
                            "road_health_score"
                        )
                    )
                )

                condition = data.get(
                    "condition",
                    _condition_from_health(health)
                )

                edge_key = (
                    str(u),
                    str(v),
                    str(key)
                )

                # AI data gets priority over OSM baseline.
                if edge_key not in lookup:

                    lookup[edge_key] = {
                        "health": health,
                        "condition": condition,
                        "source": "OSM Baseline",
                        "image": None,
                        "confidence": None
                    }

        else:

            for item in osm_segments:

                if not isinstance(item, dict):
                    continue

                u = item.get("u")
                v = item.get("v")
                key = item.get("key", 0)

                if u is None or v is None:
                    continue

                health = _safe_float(
                    item.get(
                        "health_score",
                        item.get(
                            "road_health_score"
                        )
                    )
                )

                condition = item.get(
                    "condition",
                    _condition_from_health(health)
                )

                edge_key = (
                    str(u),
                    str(v),
                    str(key)
                )

                if edge_key not in lookup:

                    lookup[edge_key] = {
                        "health": health,
                        "condition": condition,
                        "source": "OSM Baseline",
                        "image": None,
                        "confidence": None
                    }

    return lookup


def _edge_lookup(
    edge_lookup,
    u,
    v,
    key=0
):
    """
    Find an edge in the database.

    Handles both directions because OSM routing
    can contain directed edges.
    """

    candidates = [
        (str(u), str(v), str(key)),
        (str(v), str(u), str(key)),
        (str(u), str(v), "0"),
        (str(v), str(u), "0")
    ]

    for candidate in candidates:

        if candidate in edge_lookup:
            return edge_lookup[candidate]

    return None


def _get_route_edges(route):
    """
    Extract OSM edges from a route.

    Supports several possible field names so that
    this map remains compatible with the existing
    route generator.
    """

    for field in [
        "osm_edges",
        "edges",
        "route_edges"
    ]:

        edges = route.get(field)

        if edges:
            return edges

    return []


def _edge_coordinates(
    route,
    edge_index,
    total_edges
):
    """
    Determine approximate coordinates for an edge.

    If detailed edge coordinates are unavailable,
    use neighboring route GPS points.
    """

    coordinates = route.get(
        "coordinates",
        route.get(
            "gps_points",
            []
        )
    )

    if not coordinates:
        return []

    if total_edges <= 0:
        return coordinates

    if len(coordinates) < 2:
        return coordinates

    # Normally there is one GPS point per OSM node.
    if edge_index + 1 < len(coordinates):

        return [
            coordinates[edge_index],
            coordinates[edge_index + 1]
        ]

    return []


def _popup_html(
    route_name,
    segment_number,
    data
):
    """
    Create popup for an individual road segment.
    """

    if data is None:

        return f"""
        <div style="font-size:14px">
            <h4>{route_name}</h4>

            <b>Road Segment:</b>
            {segment_number}

            <br><br>

            <b>Condition:</b>
            Unknown

            <br>

            <b>Health:</b>
            No available data

            <br><br>

            <span style="color:#777">
            No AI or OSM road-condition data
            is available for this segment.
            </span>
        </div>
        """

    health = data.get(
        "health"
    )

    condition = data.get(
        "condition",
        "Unknown"
    )

    source = data.get(
        "source",
        "Unknown"
    )

    image = data.get(
        "image"
    )

    confidence = data.get(
        "confidence"
    )

    if health is None:
        health_text = "N/A"
    else:
        health_text = f"{health:.2f} / 100"

    html = f"""
    <div style="font-size:14px">

        <h4>{route_name}</h4>

        <b>Road Segment:</b>
        {segment_number}

        <br><br>

        <b>Road Health:</b>
        {health_text}

        <br>

        <b>Condition:</b>
        {condition}

        <br>

        <b>Data Source:</b>
        {source}
    """

    if confidence is not None:

        try:
            confidence_value = (
                float(confidence) * 100
            )

            html += f"""
            <br>
            <b>AI Confidence:</b>
            {confidence_value:.1f}%
            """

        except (TypeError, ValueError):
            pass

    if image:

        html += f"""
        <br>
        <b>AI Image:</b>
        {image}
        """

    html += """
        <br><br>

        <span style="color:#666">
        RoadQuality road-condition analysis
        </span>

    </div>
    """

    return html


def generate_route_map(
    routes,
    source_lat,
    source_lon,
    destination_lat,
    destination_lon,
    output_file,
    recommended_route_index=0,
    ai_segments=None,
    osm_segments=None
):
    """
    Generate RoadQuality interactive map V2.

    Features:

    - Source marker
    - Destination marker
    - Candidate routes
    - Recommended route
    - Segment-level road condition
    - AI road-condition segments
    - OSM baseline segments
    - Unknown segments
    - Clickable segment information
    - Route summary
    - Legend
    """

    if not routes:

        raise ValueError(
            "No routes available for map generation."
        )

    # ========================================================
    # BUILD DATABASE LOOKUP
    # ========================================================

    segment_lookup = _build_segment_lookup(
        ai_segments=ai_segments,
        osm_segments=osm_segments
    )

    # ========================================================
    # MAP CENTER
    # ========================================================

    center_lat = (
        source_lat + destination_lat
    ) / 2

    center_lon = (
        source_lon + destination_lon
    ) / 2

    road_map = folium.Map(
        location=[
            center_lat,
            center_lon
        ],
        zoom_start=11,
        control_scale=True
    )

    # ========================================================
    # SOURCE
    # ========================================================

    folium.Marker(
        location=[
            source_lat,
            source_lon
        ],
        popup="<b>Source</b>",
        tooltip="Source",
        icon=folium.Icon(
            color="green",
            icon="play"
        )
    ).add_to(road_map)

    # ========================================================
    # DESTINATION
    # ========================================================

    folium.Marker(
        location=[
            destination_lat,
            destination_lon
        ],
        popup="<b>Destination</b>",
        tooltip="Destination",
        icon=folium.Icon(
            color="red",
            icon="flag"
        )
    ).add_to(road_map)

    # ========================================================
    # ROUTE COLORS
    # ========================================================

    candidate_colors = [
        "blue",
        "purple",
        "darkred",
        "darkblue",
        "black"
    ]

    # ========================================================
    # ROUTE LAYERS
    # ========================================================

    for route_index, route in enumerate(routes):

        route_name = route.get(
            "name",
            f"Route {route_index + 1}"
        )

        is_recommended = (
            route_index ==
            recommended_route_index
        )

        coordinates = route.get(
            "coordinates",
            route.get(
                "gps_points",
                []
            )
        )

        if not coordinates:
            continue

        # ----------------------------------------------------
        # Route information
        # ----------------------------------------------------

        distance = route.get(
            "distance",
            "N/A"
        )

        travel_time = route.get(
            "travel_time",
            route.get(
                "time",
                "N/A"
            )
        )

        health = route.get(
            "road_health",
            route.get(
                "health",
                "N/A"
            )
        )

        condition = route.get(
            "condition",
            "Unknown"
        )

        coverage = route.get(
            "coverage",
            route.get(
                "overall_coverage",
                "N/A"
            )
        )

        # ----------------------------------------------------
        # Candidate route base line
        #
        # Keep a thin route line underneath the
        # condition segments.
        # ----------------------------------------------------

        if is_recommended:

            base_color = "green"

        else:

            base_color = candidate_colors[
                route_index %
                len(candidate_colors)
            ]

        folium.PolyLine(
            locations=coordinates,
            color=base_color,
            weight=2,
            opacity=0.35,
            tooltip=route_name
        ).add_to(road_map)

        # ----------------------------------------------------
        # OSM EDGES
        # ----------------------------------------------------

        route_edges = _get_route_edges(
            route
        )

        # ----------------------------------------------------
        # Draw individual segments
        # ----------------------------------------------------

        if route_edges:

            for edge_index, edge in enumerate(
                route_edges
            ):

                # --------------------------------------------
                # Read edge
                # --------------------------------------------

                if isinstance(edge, dict):

                    u = edge.get("u")
                    v = edge.get("v")
                    key = edge.get(
                        "key",
                        0
                    )

                elif isinstance(edge, (list, tuple)):

                    if len(edge) >= 3:

                        u = edge[0]
                        v = edge[1]
                        key = edge[2]

                    elif len(edge) == 2:

                        u = edge[0]
                        v = edge[1]
                        key = 0

                    else:
                        continue

                else:

                    continue

                if u is None or v is None:
                    continue

                # --------------------------------------------
                # Find database information
                # --------------------------------------------

                data = _edge_lookup(
                    segment_lookup,
                    u,
                    v,
                    key
                )

                # --------------------------------------------
                # Determine coordinates
                # --------------------------------------------

                segment_coordinates = (
                    _edge_coordinates(
                        route,
                        edge_index,
                        len(route_edges)
                    )
                )

                if len(segment_coordinates) < 2:
                    continue

                # --------------------------------------------
                # Determine color
                # --------------------------------------------

                if data is None:

                    line_color = "gray"
                    line_weight = 5
                    line_opacity = 0.55

                else:

                    line_color = _condition_color(
                        data.get(
                            "condition",
                            "Unknown"
                        )
                    )

                    if data.get(
                        "source"
                    ) == "AI":

                        line_weight = 7
                        line_opacity = 0.95

                    else:

                        line_weight = 6
                        line_opacity = 0.80

                # --------------------------------------------
                # Popup
                # --------------------------------------------

                popup = folium.Popup(
                    _popup_html(
                        route_name,
                        edge_index + 1,
                        data
                    ),
                    max_width=380
                )

                # --------------------------------------------
                # Segment line
                # --------------------------------------------

                folium.PolyLine(
                    locations=segment_coordinates,
                    color=line_color,
                    weight=line_weight,
                    opacity=line_opacity,
                    popup=popup,
                    tooltip=(
                        f"{route_name} | "
                        f"Segment {edge_index + 1}"
                    )
                ).add_to(road_map)

        # ----------------------------------------------------
        # Route summary popup at start
        # ----------------------------------------------------

        summary_html = f"""
        <div style="font-size:14px">

            <h3>{route_name}</h3>

            <b>Distance:</b>
            {distance} km

            <br>

            <b>Travel Time:</b>
            {travel_time} min

            <br>

            <b>Road Health:</b>
            {health} / 100

            <br>

            <b>Condition:</b>
            {condition}

            <br>

            <b>Data Coverage:</b>
            {coverage}%
        """

        if is_recommended:

            summary_html += """
            <br><br>
            <b style="color:green">
            ⭐ RECOMMENDED ROUTE
            </b>
            """

        summary_html += """
        </div>
        """

        folium.CircleMarker(
            location=coordinates[0],
            radius=7,
            popup=folium.Popup(
                summary_html,
                max_width=350
            ),
            tooltip=route_name
        ).add_to(road_map)

    # ========================================================
    # LEGEND
    # ========================================================

    legend_html = """
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        width: 230px;
        z-index: 9999;
        background-color: white;
        border: 2px solid #555;
        border-radius: 8px;
        padding: 12px;
        font-size: 13px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    ">

        <h4 style="margin-top:0">
            RoadQuality
        </h4>

        <b>Road Condition</b>

        <br><br>

        <span style="
            display:inline-block;
            width:25px;
            height:5px;
            background:green;
            margin-right:8px;
        "></span>
        Good (80-100)

        <br><br>

        <span style="
            display:inline-block;
            width:25px;
            height:5px;
            background:orange;
            margin-right:8px;
        "></span>
        Moderate (60-79)

        <br><br>

        <span style="
            display:inline-block;
            width:25px;
            height:5px;
            background:red;
            margin-right:8px;
        "></span>
        Poor (40-59)

        <br><br>

        <span style="
            display:inline-block;
            width:25px;
            height:5px;
            background:gray;
            margin-right:8px;
        "></span>
        Unknown / No Data

        <br><br>

        <b>Line thickness</b>

        <br>

        Thick = AI data

        <br>

        Medium = OSM baseline

    </div>
    """

    road_map.get_root().html.add_child(
        folium.Element(
            legend_html
        )
    )

    # ========================================================
    # LAYER CONTROL
    # ========================================================

    folium.LayerControl().add_to(
        road_map
    )

    # ========================================================
    # FIT MAP TO ROUTES
    # ========================================================

    all_coordinates = []

    for route in routes:

        all_coordinates.extend(
            route.get(
                "coordinates",
                route.get(
                    "gps_points",
                    []
                )
            )
        )

    if all_coordinates:

        road_map.fit_bounds(
            all_coordinates
        )

    # ========================================================
    # OUTPUT DIRECTORY
    # ========================================================

    output_directory = os.path.dirname(
        output_file
    )

    if output_directory:

        os.makedirs(
            output_directory,
            exist_ok=True
        )

    # ========================================================
    # SAVE
    # ========================================================

    road_map.save(
        output_file
    )

    return output_file