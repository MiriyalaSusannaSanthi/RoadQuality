/* =========================================================
   ROADQUALITY - MAIN APPLICATION JAVASCRIPT
   ========================================================= */

const API_BASE = "https://roadquality-m23e.onrender.com";

const STORAGE_ANALYSIS = "roadqualityAnalysis";
const STORAGE_SELECTED_ROUTE = "roadqualitySelectedRoute";

let plannerMap = null;
let recommendationMap = null;

let recommendationLayers = [];

const routeColors = [
    "#39d98a",
    "#4da6ff",
    "#ffb84d"
];


/* =========================================================
   COMMON HELPERS
   ========================================================= */

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function numberValue(value, fallback = 0) {
    const n = Number(value);

    return Number.isFinite(n) ? n : fallback;
}


function formatDistance(distance) {

    const value = Number(distance);

    if (!Number.isFinite(value)) {
        return "--";
    }

    /*
     * Backend distance is in kilometres.
     */
    if (value < 1) {
        return `${Math.round(value * 1000)} m`;
    }

    return `${value.toFixed(1)} km`;
}


function formatTime(minutes) {

    const value = Number(minutes);

    if (!Number.isFinite(value)) {
        return "--";
    }

    if (value < 1) {
        return "< 1 min";
    }

    const hours = Math.floor(value / 60);
    const mins = Math.round(value % 60);

    if (hours > 0) {

        if (mins === 0) {
            return `${hours}h`;
        }

        return `${hours}h ${mins}m`;
    }

    return `${mins} min`;
}


function getHealthClass(value) {

    const health = Number(value);

    if (!Number.isFinite(health)) {
        return "";
    }

    if (health >= 75) {
        return "health-good";
    }

    if (health >= 50) {
        return "health-medium";
    }

    return "health-poor";
}


function getConditionLabel(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "Unknown";
    }

    return String(value)
        .replaceAll("_", " ")
        .replace(/\b\w/g, c => c.toUpperCase());
}


function setText(id, value) {

    const element =
        document.getElementById(id);

    if (!element) {
        return;
    }

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        element.textContent = "—";
    } else {
        element.textContent = value;
    }
}


/* =========================================================
   COORDINATE HELPERS
   ========================================================= */

function normalizeCoordinates(coords) {

    if (!Array.isArray(coords)) {
        return [];
    }

    return coords
        .map(point => {

            if (
                !Array.isArray(point) ||
                point.length < 2
            ) {
                return null;
            }

            const a = Number(point[0]);
            const b = Number(point[1]);

            if (
                !Number.isFinite(a) ||
                !Number.isFinite(b)
            ) {
                return null;
            }

            /*
             * RoadQuality backend normally returns:
             *
             * [latitude, longitude]
             *
             * But also support:
             *
             * [longitude, latitude]
             */

            if (
                Math.abs(a) <= 90 &&
                Math.abs(b) <= 180
            ) {
                return [a, b];
            }

            if (
                Math.abs(b) <= 90 &&
                Math.abs(a) <= 180
            ) {
                return [b, a];
            }

            return null;

        })
        .filter(Boolean);
}


function getRouteCoordinates(route) {

    if (!route) {
        return [];
    }

    let coordinates =
        route.coordinates ||
        route.route_coordinates ||
        route.coords ||
        route.geometry ||
        route.path ||
        route.polyline;


    /*
     * GeoJSON:
     *
     * {
     *   geometry: {
     *      coordinates: [...]
     *   }
     * }
     */

    if (
        coordinates &&
        typeof coordinates === "object" &&
        !Array.isArray(coordinates) &&
        Array.isArray(coordinates.coordinates)
    ) {
        coordinates =
            coordinates.coordinates;
    }


    /*
     * Another possible format:
     *
     * {
     *   geometry: {
     *      geometry: {
     *          coordinates: [...]
     *      }
     *   }
     * }
     */

    if (
        coordinates &&
        typeof coordinates === "object" &&
        !Array.isArray(coordinates) &&
        coordinates.geometry &&
        Array.isArray(
            coordinates.geometry.coordinates
        )
    ) {
        coordinates =
            coordinates.geometry.coordinates;
    }


    return normalizeCoordinates(
        coordinates
    );
}


/* =========================================================
   ANALYSIS / ROUTE EXTRACTION
   ========================================================= */

function getStoredAnalysis() {

    const raw =
        localStorage.getItem(
            STORAGE_ANALYSIS
        );

    if (!raw) {
        return null;
    }

    try {

        return JSON.parse(raw);

    } catch (error) {

        console.error(
            "RoadQuality stored analysis JSON error:",
            error
        );

        return null;
    }
}


function getRoutesFromAnalysis(data) {

    if (!data) {
        return [];
    }


    /*
     * Support every route key currently used
     * by different versions of the backend.
     */

    const possible =
        data.routes ??
        data.route_results ??
        data.candidate_routes ??
        data.candidates ??
        data.recommended_routes ??
        data.route_options ??
        [];


    /*
     * Sometimes an API wraps routes inside
     * another object.
     */

    if (
        possible &&
        !Array.isArray(possible) &&
        typeof possible === "object"
    ) {

        if (Array.isArray(possible.routes)) {
            return possible.routes;
        }

        if (
            Array.isArray(
                possible.route_results
            )
        ) {
            return possible.route_results;
        }

        if (
            Array.isArray(
                possible.candidates
            )
        ) {
            return possible.candidates;
        }
    }


    if (!Array.isArray(possible)) {
        return [];
    }


    return possible.filter(route => {

        return (
            route &&
            typeof route === "object"
        );
    });
}


/* =========================================================
   RECOMMENDED ROUTE
   ========================================================= */

function getRecommendedRoute(
    data,
    routes
) {

    if (!routes.length) {
        return null;
    }


    /*
     * First check explicit recommended route
     * object.
     */

    if (
        data.recommended_route &&
        typeof data.recommended_route === "object"
    ) {

        return data.recommended_route;
    }


    if (
        data.recommendedRoute &&
        typeof data.recommendedRoute === "object"
    ) {

        return data.recommendedRoute;
    }


    /*
     * Then check recommended route name.
     */

    const recommendedName =
        typeof data.recommended_route === "string"
            ? data.recommended_route
            : typeof data.recommendedRoute === "string"
                ? data.recommendedRoute
                : null;


    if (recommendedName) {

        const found =
            routes.find(route => {

                return (
                    route.name ===
                    recommendedName
                );

            });


        if (found) {
            return found;
        }
    }


    /*
     * Then check recommended index.
     */

    const rawIndex =
        data.recommended_route_index ??
        data.recommendedRouteIndex;


    const index =
        Number(rawIndex);


    if (
        Number.isInteger(index) &&
        index >= 0 &&
        index < routes.length
    ) {

        return routes[index];
    }


    /*
     * Finally fall back to first route.
     */

    return routes[0];
}


function getRecommendedIndex(
    data,
    routes,
    recommended
) {

    const rawIndex =
        data.recommended_route_index ??
        data.recommendedRouteIndex;


    const index =
        Number(rawIndex);


    if (
        Number.isInteger(index) &&
        index >= 0 &&
        index < routes.length
    ) {
        return index;
    }


    if (recommended) {

        const found =
            routes.indexOf(
                recommended
            );

        if (found >= 0) {
            return found;
        }


        if (recommended.name) {

            const namedIndex =
                routes.findIndex(
                    route =>
                        route.name ===
                        recommended.name
                );

            if (namedIndex >= 0) {
                return namedIndex;
            }
        }
    }


    return 0;
}


/* =========================================================
   ROUTE VALUES
   ========================================================= */

function getRouteHealth(route) {

    const value =
        route.road_health ??
        route.health ??
        route.health_score ??
        route.roadHealth ??
        route.healthScore;


    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return null;
    }


    const n = Number(value);

    return Number.isFinite(n)
        ? n
        : null;
}


function getRouteCondition(route) {

    return (
        route.condition ??
        route.road_condition ??
        route.roadCondition ??
        "Unknown"
    );
}


function getRouteScore(route) {

    return numberValue(
        route.final_score ??
        route.score ??
        route.route_score ??
        route.routeScore,
        0
    );
}


function getRouteDistance(route) {

    return numberValue(
        route.distance ??
        route.distance_km ??
        route.distanceKm,
        0
    );
}


function getRouteTime(route) {

    return numberValue(
        route.travel_time ??
        route.travel_time_minutes ??
        route.travelTime ??
        route.time,
        0
    );
}


function getRouteCoverage(
    route,
    data
) {

    const value =
        route.coverage ??
        route.ai_coverage ??
        route.overall_coverage ??
        data?.overall_coverage ??
        data?.coverage;


    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return null;
    }


    const n = Number(value);

    return Number.isFinite(n)
        ? n
        : null;
}


function getRouteSegments(
    route
) {

    const explicit =
        route.total_segments ??
        route.totalSegments ??
        route.segment_count ??
        route.segmentCount;


    if (
        explicit !== null &&
        explicit !== undefined &&
        explicit !== ""
    ) {

        return numberValue(
            explicit,
            0
        );
    }


    const ai =
        numberValue(
            route.ai_segments ??
            route.ai_segment_count ??
            route.aiSegments,
            0
        );


    const osm =
        numberValue(
            route.osm_segments ??
            route.osm_segment_count ??
            route.osmSegments,
            0
        );


    return ai + osm;
}


/* =========================================================
   LOCATION AUTOCOMPLETE
   ========================================================= */

function setupLocationAutocomplete(
    inputId
) {

    const input =
        document.getElementById(
            inputId
        );

    if (!input) {
        return;
    }


    const wrapper =
        input.parentElement;


    if (!wrapper) {
        return;
    }


    wrapper.style.position =
        "relative";


    const dropdown =
        document.createElement(
            "div"
        );


    dropdown.className =
        "location-suggestions";


    wrapper.appendChild(
        dropdown
    );


    let timer = null;
    let controller = null;


    input.addEventListener(
        "input",
        () => {

            clearTimeout(timer);


            delete input.dataset.latitude;
            delete input.dataset.longitude;
            delete input.dataset.displayName;


            const query =
                input.value.trim();


            dropdown.innerHTML =
                "";


            dropdown.classList.remove(
                "show"
            );


            if (query.length < 2) {
                return;
            }


            timer =
                setTimeout(
                    async () => {

                        try {

                            if (controller) {
                                controller.abort();
                            }


                            controller =
                                new AbortController();


                            const response =
                                await fetch(
                                    `${API_BASE}/suggest?q=${encodeURIComponent(query)}`,
                                    {
                                        signal:
                                            controller.signal
                                    }
                                );


                            if (!response.ok) {

                                throw new Error(
                                    `Suggestion request failed: ${response.status}`
                                );
                            }


                            const data =
                                await response.json();


                            const suggestions =
                                Array.isArray(
                                    data.suggestions
                                )
                                    ? data.suggestions
                                    : [];


                            dropdown.innerHTML =
                                "";


                            if (!suggestions.length) {

                                dropdown.classList.remove(
                                    "show"
                                );

                                return;
                            }


                            suggestions.forEach(
                                place => {

                                    const item =
                                        document.createElement(
                                            "div"
                                        );


                                    item.className =
                                        "location-suggestion";


                                    const parts =
                                        String(
                                            place.display_name ||
                                            ""
                                        )
                                            .split(",");


                                    const title =
                                        parts[0]?.trim() ||
                                        place.display_name ||
                                        "Unknown location";


                                    const subtitle =
                                        parts
                                            .slice(1, 4)
                                            .map(
                                                x =>
                                                    x.trim()
                                            )
                                            .filter(
                                                Boolean
                                            )
                                            .join(", ");


                                    item.innerHTML = `
                                        <div class="suggestion-icon">
                                            <span>⌖</span>
                                        </div>

                                        <div class="suggestion-text">
                                            <strong>
                                                ${escapeHtml(title)}
                                            </strong>

                                            <span>
                                                ${escapeHtml(subtitle)}
                                            </span>
                                        </div>
                                    `;


                                    item.addEventListener(
                                        "mousedown",
                                        event => {
                                            event.preventDefault();
                                        }
                                    );


                                    item.addEventListener(
                                        "click",
                                        () => {

                                            input.value =
                                                place.display_name ||
                                                title;


                                            input.dataset.latitude =
                                                place.latitude;


                                            input.dataset.longitude =
                                                place.longitude;


                                            input.dataset.displayName =
                                                place.display_name ||
                                                title;


                                            dropdown.innerHTML =
                                                "";


                                            dropdown.classList.remove(
                                                "show"
                                            );
                                        }
                                    );


                                    dropdown.appendChild(
                                        item
                                    );
                                }
                            );


                            dropdown.classList.add(
                                "show"
                            );

                        } catch (error) {

                            if (
                                error.name !==
                                "AbortError"
                            ) {

                                console.error(
                                    "Location suggestion error:",
                                    error
                                );
                            }
                        }

                    },
                    350
                );
        }
    );


    input.addEventListener(
        "focus",
        () => {

            if (
                input.value.trim().length >= 2
            ) {

                input.dispatchEvent(
                    new Event("input")
                );
            }
        }
    );


    input.addEventListener(
        "keydown",
        event => {

            if (event.key === "Escape") {

                dropdown.classList.remove(
                    "show"
                );
            }
        }
    );


    document.addEventListener(
        "click",
        event => {

            if (
                !wrapper.contains(
                    event.target
                )
            ) {

                dropdown.classList.remove(
                    "show"
                );
            }
        }
    );
}


/* =========================================================
   CURRENT LOCATION
   ========================================================= */

function setupLocationButton() {

    const button =
        document.getElementById(
            "useLocationBtn"
        );


    const source =
        document.getElementById(
            "source"
        );


    if (!button || !source) {
        return;
    }


    button.addEventListener(
        "click",
        () => {

            if (!navigator.geolocation) {

                showError(
                    "Geolocation is not supported by this browser."
                );

                return;
            }


            button.disabled =
                true;


            const originalText =
                button.innerHTML;


            button.innerHTML =
                "Locating...";


            navigator.geolocation.getCurrentPosition(

                async position => {

                    const latitude =
                        position.coords.latitude;


                    const longitude =
                        position.coords.longitude;


                    source.dataset.latitude =
                        latitude;


                    source.dataset.longitude =
                        longitude;


                    try {

                        const response =
                            await fetch(
                                `${API_BASE}/suggest?q=${encodeURIComponent(
                                    `${latitude},${longitude}`
                                )}`
                            );


                        const data =
                            await response.json();


                        const first =
                            data.suggestions?.[0];


                        if (first) {

                            source.value =
                                first.display_name;


                            source.dataset.displayName =
                                first.display_name;

                        } else {

                            source.value =
                                `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
                        }

                    } catch {

                        source.value =
                            `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
                    }


                    button.disabled =
                        false;


                    button.innerHTML =
                        originalText;
                },


                error => {

                    console.error(error);


                    showError(
                        "Unable to get your current location. Please allow location access."
                    );


                    button.disabled =
                        false;


                    button.innerHTML =
                        originalText;
                },


                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 30000
                }
            );
        }
    );
}


/* =========================================================
   ERROR
   ========================================================= */

function showError(message) {

    const errorBox =
        document.getElementById(
            "errorBox"
        );


    if (!errorBox) {

        alert(message);

        return;
    }


    errorBox.textContent =
        message;


    errorBox.hidden =
        false;


    setTimeout(
        () => {

            errorBox.hidden =
                true;

        },
        6000
    );
}


/* =========================================================
   LOADING
   ========================================================= */

function showLoading(show) {

    const overlay =
        document.getElementById(
            "loadingOverlay"
        );


    if (!overlay) {
        return;
    }


    overlay.hidden =
        !show;
}


/* =========================================================
   PLANNER MAP
   ========================================================= */

function initializePlannerMap() {

    const element =
        document.getElementById(
            "plannerMap"
        );


    if (
        !element ||
        typeof L === "undefined"
    ) {
        return;
    }


    plannerMap =
        L.map(
            element,
            {
                zoomControl: false
            }
        )
        .setView(
            [16.5062, 80.6480],
            12
        );


    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution:
                "&copy; OpenStreetMap contributors"
        }
    ).addTo(
        plannerMap
    );


    L.control.zoom(
        {
            position:
                "bottomright"
        }
    ).addTo(
        plannerMap
    );


    setTimeout(
        () => {

            plannerMap.invalidateSize(
                true
            );

        },
        400
    );
}


/* =========================================================
   ANALYZE ROUTE
   ========================================================= */

function setupRouteForm() {

    const form =
        document.getElementById(
            "routeForm"
        );


    if (!form) {
        return;
    }


    form.addEventListener(
        "submit",
        async event => {

            event.preventDefault();


            const sourceInput =
                document.getElementById(
                    "source"
                );


            const destinationInput =
                document.getElementById(
                    "destination"
                );


            const preferenceInput =
                document.getElementById(
                    "preference"
                );


            const source =
                sourceInput?.value.trim();


            const destination =
                destinationInput?.value.trim();


            const preference =
                preferenceInput?.value ||
                "balanced";


            if (!source || !destination) {

                showError(
                    "Please enter both source and destination."
                );

                return;
            }


            if (
                source.toLowerCase() ===
                destination.toLowerCase()
            ) {

                showError(
                    "Source and destination cannot be the same."
                );

                return;
            }


            showLoading(
                true
            );


            try {

                const response =
                    await fetch(
                        `${API_BASE}/analyze`,
                        {
                            method: "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify({
                                    source,
                                    destination,
                                    preference
                                })
                        }
                    );


                const data =
                    await response.json();


                if (!response.ok) {

                    throw new Error(
                        data.error ||
                        data.message ||
                        "Route analysis failed."
                    );
                }


                if (
                    data.status &&
                    String(
                        data.status
                    ).toLowerCase() ===
                        "error"
                ) {

                    throw new Error(
                        data.error ||
                        data.message ||
                        "Unable to analyze route."
                    );
                }


                /*
                 * IMPORTANT:
                 * Store the complete backend response.
                 */

                localStorage.setItem(
                    STORAGE_ANALYSIS,
                    JSON.stringify(data)
                );


                /*
                 * Immediately verify that routes
                 * actually exist.
                 */

                const routes =
                    getRoutesFromAnalysis(
                        data
                    );


                console.log(
                    "RoadQuality /analyze response:",
                    data
                );


                console.log(
                    "RoadQuality routes detected:",
                    routes.length,
                    routes
                );


                if (!routes.length) {

                    throw new Error(
                        "Analysis completed, but no routes were returned by the server."
                    );
                }


                const recommended =
                    getRecommendedRoute(
                        data,
                        routes
                    );


                if (recommended) {

                    localStorage.setItem(
                        STORAGE_SELECTED_ROUTE,
                        JSON.stringify(
                            {
                                ...recommended,
                                coordinates:
                                    getRouteCoordinates(
                                        recommended
                                    )
                            }
                        )
                    );
                }


                window.location.href =
                    "recommendation.html";


            } catch (error) {

                console.error(
                    "RoadQuality analyze error:",
                    error
                );


                showError(
                    error.message ||
                    "Something went wrong while analyzing the route."
                );


            } finally {

                showLoading(
                    false
                );
            }
        }
    );
}


/* =========================================================
   RECOMMENDATION MAP
   ========================================================= */

function initializeRecommendationPage() {

    const mapElement =
        document.getElementById(
            "recommendationMap"
        );


    if (
        !mapElement ||
        typeof L === "undefined"
    ) {
        return;
    }


    const analysis =
        getStoredAnalysis();


    if (!analysis) {

        console.warn(
            "RoadQuality: no stored analysis."
        );

        return;
    }


    console.log(
        "RoadQuality recommendation analysis:",
        analysis
    );


    const routes =
        getRoutesFromAnalysis(
            analysis
        );


    console.log(
        "RoadQuality recommendation routes:",
        routes
    );


    if (!routes.length) {

        showRecommendationEmptyState(
            "No routes were returned by the analysis."
        );

        return;
    }


    recommendationMap =
        L.map(
            mapElement,
            {
                zoomControl: false
            }
        );


    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution:
                "&copy; OpenStreetMap contributors"
        }
    ).addTo(
        recommendationMap
    );


    L.control.zoom(
        {
            position:
                "bottomright"
        }
    ).addTo(
        recommendationMap
    );


    drawRecommendationRoutes(
        routes,
        analysis
    );


    renderRecommendationPage(
        analysis,
        routes
    );


    setTimeout(
        () => {

            recommendationMap.invalidateSize(
                true
            );

        },
        500
    );
}


/* =========================================================
   DRAW ROUTES
   ========================================================= */

function drawRecommendationRoutes(
    routes,
    analysis
) {

    recommendationLayers =
        [];


    const bounds =
        [];


    const recommended =
        getRecommendedRoute(
            analysis,
            routes
        );


    const recommendedIndex =
        getRecommendedIndex(
            analysis,
            routes,
            recommended
        );


    routes
        .slice(0, 3)
        .forEach(
            (route, index) => {

                const coordinates =
                    getRouteCoordinates(
                        route
                    );


                console.log(
                    `Route ${index + 1} coordinates:`,
                    coordinates.length
                );


                if (
                    coordinates.length < 2
                ) {

                    console.warn(
                        `Route ${index + 1} has no usable coordinates.`
                    );

                    return;
                }


                const selected =
                    index ===
                    recommendedIndex;


                const polyline =
                    L.polyline(
                        coordinates,
                        {
                            color:
                                routeColors[index] ||
                                "#39d98a",

                            weight:
                                selected
                                    ? 8
                                    : 5,

                            opacity:
                                selected
                                    ? 0.95
                                    : 0.65,

                            lineCap:
                                "round",

                            lineJoin:
                                "round"
                        }
                    )
                    .addTo(
                        recommendationMap
                    );


                polyline.bindTooltip(
                    route.name ||
                    `Route ${index + 1}`,
                    {
                        sticky:
                            true
                    }
                );


                recommendationLayers.push(
                    polyline
                );


                coordinates.forEach(
                    point => {

                        bounds.push(
                            point
                        );
                    }
                );
            }
        );


    if (bounds.length) {

        recommendationMap.fitBounds(
            bounds,
            {
                padding:
                    [50, 50]
            }
        );

    } else {

        /*
         * If route geometry is unavailable,
         * still keep the map usable.
         */

        recommendationMap.setView(
            [16.5062, 80.6480],
            11
        );
    }
}


/* =========================================================
   RECOMMENDATION PAGE
   ========================================================= */

function renderRecommendationPage(
    data,
    routes
) {

    const recommended =
        getRecommendedRoute(
            data,
            routes
        );


    const selectedIndex =
        getRecommendedIndex(
            data,
            routes,
            recommended
        );


    if (!recommended) {

        showRecommendationEmptyState(
            "No recommended route is available."
        );

        return;
    }


    /*
     * Save selected route.
     */

    localStorage.setItem(
        STORAGE_SELECTED_ROUTE,
        JSON.stringify(
            {
                ...recommended,
                coordinates:
                    getRouteCoordinates(
                        recommended
                    )
            }
        )
    );


    /*
     * Journey information.
     */

    renderJourney(
        data
    );


    /*
     * Main recommended route.
     */

    renderRecommendedRoute(
        data,
        recommended
    );


    /*
     * Route comparison cards.
     */

    renderRouteComparison(
        data,
        routes,
        selectedIndex
    );


    /*
     * AI explanation.
     */

    renderAIExplanation(
        data,
        recommended
    );


    /*
     * Navigation button.
     */

    setupStartNavigation(
        recommended
    );
}


/* =========================================================
   JOURNEY
   ========================================================= */

function renderJourney(data) {

    if (!data) {
        return;
    }


    const source =
        data.source;


    const destination =
        data.destination;


    let sourceName =
        "";


    let destinationName =
        "";


    if (
        source &&
        typeof source === "object"
    ) {

        sourceName =
            source.name ||
            source.display_name ||
            source.displayName ||
            "";

    } else {

        sourceName =
            source ||
            "";
    }


    if (
        destination &&
        typeof destination === "object"
    ) {

        destinationName =
            destination.name ||
            destination.display_name ||
            destination.displayName ||
            "";

    } else {

        destinationName =
            destination ||
            "";
    }


    setText(
        "journeySource",
        sourceName
    );


    setText(
        "journeyDestination",
        destinationName
    );


    if (
        sourceName &&
        destinationName
    ) {

        setText(
            "routeSummary",
            `Comparing routes from ${sourceName} to ${destinationName}.`
        );
    }
}


/* =========================================================
   RECOMMENDED ROUTE CARD
   ========================================================= */

function renderRecommendedRoute(
    data,
    route
) {

    const health =
        getRouteHealth(
            route
        );


    const condition =
        getConditionLabel(
            getRouteCondition(
                route
            )
        );


    const distance =
        getRouteDistance(
            route
        );


    const time =
        getRouteTime(
            route
        );


    const score =
        getRouteScore(
            route
        );


    setText(
        "recommendedName",
        route.name ||
        "Recommended Route"
    );


    setText(
        "recommendedHealth",
        health === null
            ? "N/A"
            : Math.round(health)
    );


    setText(
        "recommendedCondition",
        condition
    );


    setText(
        "recommendedDistance",
        formatDistance(
            distance
        )
    );


    setText(
        "recommendedTime",
        formatTime(
            time
        )
    );


    setText(
        "recommendedScore",
        score.toFixed(1)
    );


    /*
     * Metrics
     */

    setText(
        "metricHealth",
        health === null
            ? "N/A"
            : `${Math.round(health)}/100`
    );


    setText(
        "metricTime",
        formatTime(
            time
        )
    );


    const coverage =
        getRouteCoverage(
            route,
            data
        );


    setText(
        "metricCoverage",
        coverage === null
            ? "N/A"
            : `${coverage.toFixed(1)}%`
    );


    const segments =
        getRouteSegments(
            route
        );


    setText(
        "metricSegments",
        segments > 0
            ? segments
            : "N/A"
    );


    const reason =
        route.recommendation_reason ||
        route.reason ||
        data.recommendation_reason ||
        data.recommendationReason ||
        getRecommendationReason(
            route,
            data
        );


    setText(
        "recommendationReason",
        reason
    );
}


/* =========================================================
   RECOMMENDATION REASON
   ========================================================= */

function getRecommendationReason(
    route,
    data
) {

    const preference =
        data.preference ||
        "balanced";


    const health =
        getRouteHealth(
            route
        );


    if (
        preference ===
        "road_condition"
    ) {

        return (
            "This route provides the strongest road-condition score among the available routes."
        );
    }


    if (
        preference ===
        "fastest"
    ) {

        return (
            "This route is selected because it provides the best travel-time option."
        );
    }


    if (
        health !== null &&
        health >= 75
    ) {

        return (
            "This route offers a strong balance between road quality, distance and travel time."
        );
    }


    return (
        "This route provides the best overall balance according to RoadQuality's route scoring."
    );
}


/* =========================================================
   ROUTE COMPARISON
   ========================================================= */

function renderRouteComparison(
    data,
    routes,
    selectedIndex
) {

    const container =
        document.getElementById(
            "routeComparison"
        );


    const empty =
        document.getElementById(
            "routeEmpty"
        );


    if (!container) {

        console.error(
            "RoadQuality: #routeComparison not found."
        );

        return;
    }


    container.innerHTML =
        "";


    setText(
        "routeCount",
        `${routes.length} ${
            routes.length === 1
                ? "route"
                : "routes"
        }`
    );


    if (!routes.length) {

        if (empty) {
            empty.style.display =
                "block";
        }

        return;
    }


    if (empty) {
        empty.style.display =
            "none";
    }


    routes
        .slice(0, 3)
        .forEach(
            (route, index) => {

                const card =
                    createRouteCard(
                        data,
                        route,
                        index,
                        selectedIndex
                    );


                container.appendChild(
                    card
                );
            }
        );
}


/* =========================================================
   CREATE ROUTE CARD
   ========================================================= */

function createRouteCard(
    data,
    route,
    index,
    selectedIndex
) {

    const card =
        document.createElement(
            "div"
        );


    card.className =
        "rq-route-card";


    const isRecommended =
        index ===
        selectedIndex;


    if (isRecommended) {

        card.classList.add(
            "selected"
        );
    }


    const color =
        routeColors[index]
            ? index === 0
                ? "green"
                : index === 1
                    ? "blue"
                    : "orange"
            : "green";


    const health =
        getRouteHealth(
            route
        );


    const condition =
        getConditionLabel(
            getRouteCondition(
                route
            )
        );


    const distance =
        getRouteDistance(
            route
        );


    const time =
        getRouteTime(
            route
        );


    const score =
        getRouteScore(
            route
        );


    const healthText =
        health === null
            ? "N/A"
            : `${Math.round(health)}/100`;


    card.innerHTML = `

        <div class="rq-route-card-top">

            <div class="rq-route-card-name">

                <span class="rq-color ${color}">
                </span>

                <div>

                    <small>
                        ${
                            isRecommended
                                ? "RECOMMENDED"
                                : "ALTERNATIVE " +
                                  index
                        }
                    </small>

                    <strong>
                        ${escapeHtml(
                            route.name ||
                            `Route ${index + 1}`
                        )}
                    </strong>

                </div>

            </div>

            ${
                isRecommended
                    ? `
                        <span class="rq-card-badge">
                            BEST
                        </span>
                      `
                    : ""
            }

        </div>


        <div class="rq-route-card-condition">

            <span class="rq-health-dot ${getHealthState(health)}">
            </span>

            <strong>
                ${escapeHtml(
                    condition
                )}
            </strong>

            <span>
                ${healthText}
            </span>

        </div>


        <div class="rq-route-card-stats">

            <div>

                <small>
                    DISTANCE
                </small>

                <strong>
                    ${formatDistance(
                        distance
                    )}
                </strong>

            </div>


            <div>

                <small>
                    TIME
                </small>

                <strong>
                    ${formatTime(
                        time
                    )}
                </strong>

            </div>


            <div>

                <small>
                    SCORE
                </small>

                <strong>
                    ${score.toFixed(1)}
                </strong>

            </div>

        </div>
    `;


    card.addEventListener(
        "click",
        () => {

            localStorage.setItem(
                STORAGE_SELECTED_ROUTE,
                JSON.stringify(
                    {
                        ...route,
                        coordinates:
                            getRouteCoordinates(
                                route
                            )
                    }
                )
            );


            document
                .querySelectorAll(
                    ".rq-route-card"
                )
                .forEach(
                    element => {

                        element.classList.remove(
                            "selected"
                        );
                    }
                );


            card.classList.add(
                "selected"
            );


            /*
             * Update recommended panel when
             * user selects another route.
             */

            renderRecommendedRoute(
                data,
                route
            );


            renderAIExplanation(
                data,
                route
            );


            setupStartNavigation(
                route
            );


            /*
             * Update route line styles.
             */

            recommendationLayers.forEach(
                (layer, layerIndex) => {

                    const selected =
                        layerIndex ===
                        index;


                    layer.setStyle({
                        weight:
                            selected
                                ? 8
                                : 5,

                        opacity:
                            selected
                                ? 0.95
                                : 0.65
                    });
                }
            );
        }
    );


    return card;
}


/* =========================================================
   HEALTH STATE
   ========================================================= */

function getHealthState(
    health
) {

    if (health === null) {
        return "unknown";
    }


    if (health >= 80) {
        return "good";
    }


    if (health >= 60) {
        return "moderate";
    }


    return "poor";
}


/* =========================================================
   AI EXPLANATION
   ========================================================= */

function renderAIExplanation(
    data,
    route
) {

    const element =
        document.getElementById(
            "aiExplanation"
        );


    if (!element) {
        return;
    }


    const explicit =
        route.recommendation_reason ||
        route.reason ||
        data.recommendation_reason ||
        data.recommendationReason;


    if (explicit) {

        element.textContent =
            explicit;

        return;
    }


    const aiSegments =
        numberValue(
            route.ai_segments ??
            route.ai_segment_count ??
            data.ai_segments,
            0
        );


    const osmSegments =
        numberValue(
            route.osm_segments ??
            route.osm_segment_count ??
            data.osm_segments,
            0
        );


    const coverage =
        getRouteCoverage(
            route,
            data
        );


    element.textContent =
        `RoadQuality evaluated road condition, distance, travel time and route score to select the most suitable route. ` +
        `AI segments: ${aiSegments}. ` +
        `OSM segments: ${osmSegments}. ` +
        `Coverage: ${
            coverage === null
                ? "N/A"
                : coverage.toFixed(1) + "%"
        }.`;
}


/* =========================================================
   START NAVIGATION
   ========================================================= */

function setupStartNavigation(
    route
) {

    const button =
        document.getElementById(
            "startNavigationBtn"
        );


    if (!button) {
        return;
    }


    /*
     * Clone to remove previous listeners.
     */

    const newButton =
        button.cloneNode(
            true
        );


    button.parentNode.replaceChild(
        newButton,
        button
    );


    newButton.addEventListener(
        "click",
        () => {

            const selectedRoute = {
                ...route,

                coordinates:
                    getRouteCoordinates(
                        route
                    )
            };


            localStorage.setItem(
                STORAGE_SELECTED_ROUTE,
                JSON.stringify(
                    selectedRoute
                )
            );


            window.location.href =
                "navigation.html";
        }
    );
}


/* =========================================================
   EMPTY RECOMMENDATION STATE
   ========================================================= */

function showRecommendationEmptyState(
    message
) {

    const container =
        document.getElementById(
            "routeComparison"
        );


    const empty =
        document.getElementById(
            "routeEmpty"
        );


    if (container) {

        container.innerHTML = `
            <div class="rq-empty">
                ${escapeHtml(message)}
            </div>
        `;
    }


    if (empty) {

        empty.style.display =
            "block";

        empty.textContent =
            message;
    }


    console.warn(
        "RoadQuality recommendation:",
        message
    );
}


/* =========================================================
   NAVIGATION PAGE
   ========================================================= */

function initializeNavigationPage() {

    const mapElement =
        document.getElementById(
            "navigationMap"
        );


    if (
        !mapElement ||
        typeof L === "undefined"
    ) {
        return;
    }


    /*
     * Navigation GPS logic remains in
     * navigation.html.
     */
}


/* =========================================================
   PAGE INITIALIZATION
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        /*
         * Planner
         */

        if (
            document.getElementById(
                "routeForm"
            )
        ) {

            setupLocationAutocomplete(
                "source"
            );


            setupLocationAutocomplete(
                "destination"
            );


            setupLocationButton();


            initializePlannerMap();


            setupRouteForm();
        }


        /*
         * Recommendation
         */

        if (
            document.getElementById(
                "recommendationMap"
            )
        ) {

            initializeRecommendationPage();
        }


        /*
         * Navigation
         */

        if (
            document.getElementById(
                "navigationMap"
            )
        ) {

            initializeNavigationPage();
        }

    }
);