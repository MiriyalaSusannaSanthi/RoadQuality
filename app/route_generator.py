import os
import osmnx as ox
import networkx as nx


# ============================================================
# ROADQUALITY - FAST REAL-WORLD ROUTE GENERATOR
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

DEFAULT_NUMBER_OF_ROUTES = 3


# ============================================================
# FIND NEAREST OSM NODE
# ============================================================

def get_nearest_nodes(G, latitude, longitude):

    return ox.distance.nearest_nodes(
        G,
        X=longitude,
        Y=latitude
    )


# ============================================================
# GET BEST EDGE KEY
# ============================================================

def get_edge_key(G, u, v):

    edge_data = G.get_edge_data(u, v)

    if edge_data is None:
        return None

    if isinstance(G, nx.MultiDiGraph):

        best_key = None
        best_length = float("inf")

        for key, data in edge_data.items():

            length = float(
                data.get(
                    "length",
                    float("inf")
                )
            )

            if length < best_length:

                best_length = length
                best_key = key

        return best_key

    return 0


# ============================================================
# CONVERT NODE PATH TO OSM EDGES
# ============================================================

def nodes_to_edges(G, route_nodes):

    edges = []

    for i in range(len(route_nodes) - 1):

        u = route_nodes[i]
        v = route_nodes[i + 1]

        key = get_edge_key(
            G,
            u,
            v
        )

        if key is not None:

            edges.append(
                (u, v, key)
            )

    return edges


# ============================================================
# GET ROUTE GPS COORDINATES
# ============================================================

def get_route_coordinates(G, route_nodes):

    coordinates = []

    for node in route_nodes:

        data = G.nodes[node]

        latitude = data.get("y")
        longitude = data.get("x")

        if latitude is not None and longitude is not None:

            coordinates.append(
                (
                    float(latitude),
                    float(longitude)
                )
            )

    return coordinates


# ============================================================
# CALCULATE ROUTE DISTANCE
# ============================================================

def calculate_route_distance(
    G,
    route_edges
):

    total_distance = 0.0

    for u, v, key in route_edges:

        data = G.get_edge_data(
            u,
            v,
            key
        )

        if data:

            total_distance += float(
                data.get(
                    "length",
                    0.0
                )
            )

    return round(
        total_distance / 1000.0,
        2
    )


# ============================================================
# CALCULATE TRAVEL TIME
# ============================================================

def calculate_travel_time(
    G,
    route_edges
):

    total_time_seconds = 0.0

    for u, v, key in route_edges:

        data = G.get_edge_data(
            u,
            v,
            key
        )

        if not data:
            continue

        # Preferred OSMnx travel_time
        if "travel_time" in data:

            try:

                total_time_seconds += float(
                    data["travel_time"]
                )

                continue

            except Exception:
                pass

        # Fallback estimation
        length = float(
            data.get(
                "length",
                0.0
            )
        )

        speed_kmh = float(
            data.get(
                "speed_kph",
                40.0
            )
        )

        if speed_kmh <= 0:

            speed_kmh = 40.0

        total_time_seconds += (
            length /
            (speed_kmh * 1000.0 / 3600.0)
        )

    return round(
        total_time_seconds / 60.0,
        2
    )


# ============================================================
# BUILD FAST SIMPLE DIRECTED GRAPH
# ============================================================

def build_simple_graph(G):

    H = nx.DiGraph()

    for u, v, key, data in G.edges(
        keys=True,
        data=True
    ):

        length = float(
            data.get(
                "length",
                1.0
            )
        )

        # Keep shortest parallel edge
        if H.has_edge(u, v):

            existing_length = float(
                H[u][v].get(
                    "length",
                    float("inf")
                )
            )

            if existing_length <= length:
                continue

        H.add_edge(
            u,
            v,
            length=length
        )

    return H


# ============================================================
# FAST ROUTE PATH
# ============================================================

def shortest_path(
    H,
    source_node,
    destination_node,
    weight="length"
):

    try:

        return nx.shortest_path(
            H,
            source=source_node,
            target=destination_node,
            weight=weight,
            method="dijkstra"
        )

    except nx.NetworkXNoPath:

        return None


# ============================================================
# CREATE ALTERNATIVE ROUTE
# ============================================================

def create_alternative_graph(
    H,
    previous_paths,
    penalty=2.5
):
    alternative = H.copy()

    used_edges = set()

    for path in previous_paths:
        for u, v in zip(path[:-1], path[1:]):
            used_edges.add((u, v))

    for u, v in alternative.edges():

        if (u, v) in used_edges:

            original_length = float(
                alternative[u][v].get(
                    "length",
                    1.0
                )
            )

            alternative[u][v]["length"] = (
                original_length * penalty
            )

    return alternative

# ============================================================
# GENERATE CANDIDATE ROUTES
# ============================================================

def generate_routes(
    G,
    source_lat,
    source_lon,
    destination_lat,
    destination_lon,
    number_of_routes=DEFAULT_NUMBER_OF_ROUTES
):

    if G is None:

        return []

    if number_of_routes <= 0:

        return []


    # --------------------------------------------------------
    # FIND SOURCE / DESTINATION NODES
    # --------------------------------------------------------

    source_node = get_nearest_nodes(
        G,
        source_lat,
        source_lon
    )

    destination_node = get_nearest_nodes(
        G,
        destination_lat,
        destination_lon
    )

    print(
        f"\nSource OSM node: {source_node}"
    )

    print(
        f"Destination OSM node: {destination_node}"
    )


    # --------------------------------------------------------
    # ADD TRAVEL TIME
    # --------------------------------------------------------

    try:

        missing_travel_time = not all(
            "travel_time" in data
            for _, _, _, data
            in G.edges(
                keys=True,
                data=True
            )
        )

        if missing_travel_time:

            G = ox.add_edge_speeds(G)

            G = ox.add_edge_travel_times(G)

    except Exception as e:

        print(
            "Travel-time preparation warning:",
            e
        )


    # --------------------------------------------------------
    # BUILD SIMPLE GRAPH
    # --------------------------------------------------------

    H = build_simple_graph(G)

    print(
        f"Routing graph: "
        f"{len(H.nodes)} nodes, "
        f"{len(H.edges)} edges"
    )


    # --------------------------------------------------------
    # GENERATE ROUTES
    # --------------------------------------------------------

    candidate_node_routes = []

    try:

        # ====================================================
        # ROUTE 1 - TRUE SHORTEST DISTANCE
        # ====================================================

        route1 = shortest_path(
            H,
            source_node,
            destination_node,
            weight="length"
        )

        if route1 is None:

            print(
                "\nERROR: No road path exists."
            )

            return []

        candidate_node_routes.append(
            route1
        )


        # ====================================================
        # ROUTE 2 - AVOID ROUTE 1
        # ====================================================

        if number_of_routes >= 2:

            H2 = create_alternative_graph(
                H,
                [route1],
                penalty=2.5
            )

            route2 = shortest_path(
                H2,
                source_node,
                destination_node,
                weight="length"
            )

            if (
                route2 is not None
                and route2 != route1
            ):

                candidate_node_routes.append(
                    route2
                )


        # ====================================================
        # ROUTE 3 - AVOID ROUTES 1 AND 2
        # ====================================================

        if number_of_routes >= 3:

            H3 = create_alternative_graph(
                H,
                candidate_node_routes,
                penalty=3.0
            )

            route3 = shortest_path(
                H3,
                source_node,
                destination_node,
                weight="length"
            )

            if (
                route3 is not None
                and route3 not in candidate_node_routes
            ):

                candidate_node_routes.append(
                    route3
                )


        # ====================================================
        # SAFETY FALLBACK
        # ====================================================

        if len(candidate_node_routes) < number_of_routes:

            print(
                "Could not find all requested "
                "distinct alternatives."
            )

    except Exception as e:

        print(
            "\nERROR while generating routes:"
        )

        print(e)

        return []


    # --------------------------------------------------------
    # CONVERT ROUTES INTO COMPLETE OBJECTS
    # --------------------------------------------------------

    routes = []

    for index, route_nodes in enumerate(
        candidate_node_routes,
        start=1
    ):

        route_edges = nodes_to_edges(
            G,
            route_nodes
        )

        coordinates = get_route_coordinates(
            G,
            route_nodes
        )

        distance = calculate_route_distance(
            G,
            route_edges
        )

        travel_time = calculate_travel_time(
            G,
            route_edges
        )

        route = {

            "name":
                f"Route {index}",

            "nodes":
                route_nodes,

            "coordinates":
                coordinates,

            "osm_edges":
                route_edges,

            "distance":
                distance,

            "travel_time":
                travel_time
        }

        routes.append(
            route
        )


    return routes


# ============================================================
# DISPLAY ROUTES
# ============================================================

def print_routes(routes):

    print(
        "\n" + "=" * 70
    )

    print(
        "CANDIDATE ROUTES"
    )

    print(
        "=" * 70
    )

    for route in routes:

        print(
            f"{route['name']} | "
            f"Distance: "
            f"{route['distance']} km | "
            f"Time: "
            f"{route['travel_time']} min | "
            f"Nodes: "
            f"{len(route['nodes'])} | "
            f"GPS points: "
            f"{len(route['coordinates'])} | "
            f"OSM edges: "
            f"{len(route['osm_edges'])}"
        )


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print(
        "=" * 70
    )

    print(
        "ROADQUALITY FAST ROUTE GENERATOR"
    )

    print(
        "=" * 70
    )

    print(
        "This module is intended to be "
        "called by api.py."
    )