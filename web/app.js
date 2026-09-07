/* =========================================================
   ROADQUALITY - MAIN APPLICATION JAVASCRIPT
   ========================================================= */

const API_BASE = "http://127.0.0.1:5000";

const STORAGE_ANALYSIS = "roadqualityAnalysis";
const STORAGE_SELECTED_ROUTE = "roadqualitySelectedRoute";

let plannerMap = null;
let recommendationMap = null;

let plannerMarkers = [];
let recommendationLayers = [];

let routeColors = [
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


function formatDistance(distance) {
    const value = Number(distance);

    if (!Number.isFinite(value)) {
        return "--";
    }

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
    if (!value) {
        return "Unknown";
    }

    return String(value)
        .replaceAll("_", " ")
        .replace(/\b\w/g, c => c.toUpperCase());
}


function normalizeCoordinates(coords) {
    if (!Array.isArray(coords)) {
        return [];
    }

    return coords
        .map(point => {
            if (!Array.isArray(point) || point.length < 2) {
                return null;
            }

            const a = Number(point[0]);
            const b = Number(point[1]);

            if (!Number.isFinite(a) || !Number.isFinite(b)) {
                return null;
            }

            /*
             * RoadQuality backend returns [latitude, longitude].
             *
             * This also handles [longitude, latitude] defensively.
             */
            if (Math.abs(a) <= 90 && Math.abs(b) <= 180) {
                return [a, b];
            }

            if (Math.abs(b) <= 90 && Math.abs(a) <= 180) {
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
        route.geometry;

    /*
     * Some APIs return geometry as:
     * { coordinates: [[lon, lat], ...] }
     */
    if (
        coordinates &&
        typeof coordinates === "object" &&
        !Array.isArray(coordinates) &&
        Array.isArray(coordinates.coordinates)
    ) {
        coordinates = coordinates.coordinates;
    }

    return normalizeCoordinates(coordinates);
}


function getRoutesFromAnalysis(analysis) {
    if (!analysis) {
        return [];
    }

    return (
        analysis.routes ||
        analysis.route_results ||
        analysis.candidate_routes ||
        analysis.candidates ||
        []
    );
}


/* =========================================================
   LOCATION AUTOCOMPLETE
   ========================================================= */

function setupLocationAutocomplete(inputId) {

    const input = document.getElementById(inputId);

    if (!input) {
        return;
    }

    const wrapper = input.parentElement;

    if (!wrapper) {
        return;
    }

    wrapper.style.position = "relative";

    const dropdown = document.createElement("div");

    dropdown.className = "location-suggestions";

    wrapper.appendChild(dropdown);

    let timer = null;
    let controller = null;


    input.addEventListener("input", () => {

        clearTimeout(timer);

        /*
         * Clear previously selected coordinates whenever
         * the user changes the text.
         */
        delete input.dataset.latitude;
        delete input.dataset.longitude;
        delete input.dataset.displayName;

        const query = input.value.trim();

        dropdown.innerHTML = "";
        dropdown.classList.remove("show");

        if (query.length < 2) {
            return;
        }

        timer = setTimeout(async () => {

            try {

                if (controller) {
                    controller.abort();
                }

                controller = new AbortController();

                const response = await fetch(
                    `${API_BASE}/suggest?q=${encodeURIComponent(query)}`,
                    {
                        signal: controller.signal
                    }
                );

                if (!response.ok) {
                    throw new Error(
                        `Suggestion request failed: ${response.status}`
                    );
                }

                const data = await response.json();

                const suggestions = data.suggestions || [];

                dropdown.innerHTML = "";

                if (!suggestions.length) {
                    dropdown.classList.remove("show");
                    return;
                }


                suggestions.forEach(place => {

                    const item = document.createElement("div");

                    item.className = "location-suggestion";

                    const parts =
                        String(place.display_name || "")
                            .split(",");

                    const title =
                        parts[0]?.trim() ||
                        place.display_name ||
                        "Unknown location";

                    const subtitle =
                        parts
                            .slice(1, 4)
                            .map(x => x.trim())
                            .filter(Boolean)
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


                    item.addEventListener("mousedown", event => {
                        event.preventDefault();
                    });


                    item.addEventListener("click", () => {

                        input.value =
                            place.display_name || title;

                        input.dataset.latitude =
                            place.latitude;

                        input.dataset.longitude =
                            place.longitude;

                        input.dataset.displayName =
                            place.display_name || title;

                        dropdown.innerHTML = "";

                        dropdown.classList.remove("show");
                    });


                    dropdown.appendChild(item);
                });


                dropdown.classList.add("show");

            } catch (error) {

                if (error.name !== "AbortError") {
                    console.error(
                        "Location suggestion error:",
                        error
                    );
                }
            }

        }, 350);
    });


    input.addEventListener("focus", () => {

        if (input.value.trim().length >= 2) {
            input.dispatchEvent(new Event("input"));
        }
    });


    document.addEventListener("click", event => {

        if (!wrapper.contains(event.target)) {
            dropdown.classList.remove("show");
        }
    });


    input.addEventListener("keydown", event => {

        if (event.key === "Escape") {
            dropdown.classList.remove("show");
        }
    });
}


/* =========================================================
   USE CURRENT LOCATION
   ========================================================= */

function setupLocationButton() {

    const button =
        document.getElementById("useLocationBtn");

    const source =
        document.getElementById("source");

    if (!button || !source) {
        return;
    }


    button.addEventListener("click", () => {

        if (!navigator.geolocation) {

            showError(
                "Geolocation is not supported by this browser."
            );

            return;
        }


        button.disabled = true;

        const originalText =
            button.innerHTML;

        button.innerHTML = "Locating...";


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


                button.disabled = false;
                button.innerHTML = originalText;
            },


            error => {

                console.error(error);

                showError(
                    "Unable to get your current location. Please allow location access."
                );

                button.disabled = false;
                button.innerHTML = originalText;
            },


            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 30000
            }
        );
    });
}


/* =========================================================
   ERROR MESSAGE
   ========================================================= */

function showError(message) {

    const errorBox =
        document.getElementById("errorBox");

    if (!errorBox) {
        alert(message);
        return;
    }

    errorBox.textContent = message;

    errorBox.hidden = false;

    setTimeout(() => {
        errorBox.hidden = true;
    }, 6000);
}


/* =========================================================
   LOADING
   ========================================================= */

function showLoading(show) {

    const overlay =
        document.getElementById("loadingOverlay");

    if (!overlay) {
        return;
    }

    overlay.hidden = !show;
}


/* =========================================================
   PLANNER MAP
   ========================================================= */

function initializePlannerMap() {

    const element =
        document.getElementById("plannerMap");

    if (!element || typeof L === "undefined") {
        return;
    }


    plannerMap =
        L.map(element, {
            zoomControl: false
        })
        .setView(
            [16.5062, 80.6480],
            12
        );


    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors"
        }
    ).addTo(plannerMap);


    L.control.zoom({
        position: "bottomright"
    }).addTo(plannerMap);


    setTimeout(() => {
        plannerMap.invalidateSize(true);
    }, 400);
}


/* =========================================================
   PLANNER FORM
   ========================================================= */

function setupRouteForm() {

    const form =
        document.getElementById("routeForm");

    if (!form) {
        return;
    }


    form.addEventListener("submit", async event => {

        event.preventDefault();


        const sourceInput =
            document.getElementById("source");

        const destinationInput =
            document.getElementById("destination");

        const preferenceInput =
            document.getElementById("preference");


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


        showLoading(true);


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

                        body: JSON.stringify({
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
                String(data.status).toLowerCase()
                    === "error"
            ) {

                throw new Error(
                    data.error ||
                    "Unable to analyze route."
                );
            }


            localStorage.setItem(
                STORAGE_ANALYSIS,
                JSON.stringify(data)
            );


            /*
             * Determine the recommended route.
             */
            const routes =
                getRoutesFromAnalysis(data);

            let selectedRoute = null;


            if (
                Number.isInteger(
                    data.recommended_route_index
                ) &&
                routes[data.recommended_route_index]
            ) {

                selectedRoute =
                    routes[
                        data.recommended_route_index
                    ];
            }


            if (!selectedRoute && data.recommended_route) {

                if (
                    typeof data.recommended_route ===
                    "object"
                ) {

                    selectedRoute =
                        data.recommended_route;

                } else {

                    selectedRoute =
                        routes.find(route =>
                            route.name ===
                            data.recommended_route
                        );
                }
            }


            if (!selectedRoute && routes.length) {
                selectedRoute = routes[0];
            }


            if (selectedRoute) {

                localStorage.setItem(
                    STORAGE_SELECTED_ROUTE,
                    JSON.stringify(
                        selectedRoute
                    )
                );
            }


            window.location.href =
                "recommendation.html";


        } catch (error) {

            console.error(error);

            showError(
                error.message ||
                "Something went wrong while analyzing the route."
            );

        } finally {

            showLoading(false);
        }
    });
}


/* =========================================================
   RECOMMENDATION PAGE
   ========================================================= */

function initializeRecommendationPage() {

    const mapElement =
        document.getElementById(
            "recommendationMap"
        );

    if (!mapElement || typeof L === "undefined") {
        return;
    }


    const raw =
        localStorage.getItem(
            STORAGE_ANALYSIS
        );


    if (!raw) {
        return;
    }


    let analysis;

    try {
        analysis = JSON.parse(raw);
    } catch {
        return;
    }


    const routes =
        getRoutesFromAnalysis(analysis);


    if (!routes.length) {
        return;
    }


    recommendationMap =
        L.map(mapElement, {
            zoomControl: false
        });


    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors"
        }
    ).addTo(recommendationMap);


    L.control.zoom({
        position: "bottomright"
    }).addTo(recommendationMap);


    drawRecommendationRoutes(
        routes,
        analysis
    );


    renderRecommendation(
        analysis,
        routes
    );


    setTimeout(() => {
        recommendationMap.invalidateSize(true);
    }, 500);
}


/* =========================================================
   DRAW ALL ROUTES
   ========================================================= */

function drawRecommendationRoutes(
    routes,
    analysis
) {

    recommendationLayers = [];


    const bounds = [];


    routes.slice(0, 3).forEach(
        (route, index) => {

            const coordinates =
                getRouteCoordinates(route);


            if (coordinates.length < 2) {
                return;
            }


            const selected =
                isRecommendedRoute(
                    route,
                    index,
                    analysis
                );


            const polyline =
                L.polyline(
                    coordinates,
                    {
                        color:
                            routeColors[index] ||
                            "#39d98a",

                        weight:
                            selected ? 8 : 5,

                        opacity:
                            selected ? 0.95 : 0.65,

                        lineCap: "round",

                        lineJoin: "round"
                    }
                )
                .addTo(recommendationMap);


            polyline.bindTooltip(
                route.name ||
                `Route ${index + 1}`,
                {
                    sticky: true
                }
            );


            recommendationLayers.push(
                polyline
            );


            coordinates.forEach(point => {
                bounds.push(point);
            });
        }
    );


    if (bounds.length) {

        recommendationMap.fitBounds(
            bounds,
            {
                padding: [50, 50]
            }
        );
    }
}


function isRecommendedRoute(
    route,
    index,
    analysis
) {

    if (
        Number.isInteger(
            analysis.recommended_route_index
        )
    ) {

        return (
            index ===
            analysis.recommended_route_index
        );
    }


    if (
        analysis.recommended_route &&
        typeof analysis.recommended_route ===
            "string"
    ) {

        return (
            route.name ===
            analysis.recommended_route
        );
    }


    return index === 0;
}


/* =========================================================
   RENDER RECOMMENDATION
   ========================================================= */

function renderRecommendation(
    analysis,
    routes
) {

    let selectedIndex =
        Number.isInteger(
            analysis.recommended_route_index
        )
            ? analysis.recommended_route_index
            : 0;


    if (
        selectedIndex < 0 ||
        selectedIndex >= routes.length
    ) {
        selectedIndex = 0;
    }


    const route =
        routes[selectedIndex];


    if (!route) {
        return;
    }


    localStorage.setItem(
        STORAGE_SELECTED_ROUTE,
        JSON.stringify(route)
    );


    setText(
        "recommendedName",
        route.name ||
        `Route ${selectedIndex + 1}`
    );


    setText(
        "recommendedDistance",
        formatDistance(
            route.distance
        )
    );


    setText(
        "recommendedTime",
        formatTime(
            route.travel_time
        )
    );


    setText(
        "recommendedHealth",
        route.road_health != null
            ? `${Number(route.road_health).toFixed(0)}%`
            : "--"
    );


    setText(
        "recommendedScore",
        route.score != null
            ? Number(route.score).toFixed(1)
            : "--"
    );


    const condition =
        document.getElementById(
            "recommendedCondition"
        );


    if (condition) {

        condition.textContent =
            getConditionLabel(
                route.condition
            );
    }


    const reason =
        document.getElementById(
            "recommendationReason"
        );


    if (reason) {

        reason.textContent =
            getRecommendationReason(
                route,
                analysis
            );
    }


    renderRouteComparison(
        routes,
        selectedIndex
    );


    renderAIExplanation(
        analysis,
        route
    );


    setupStartNavigation(
        route
    );
}


/* =========================================================
   RECOMMENDATION REASON
   ========================================================= */

function getRecommendationReason(
    route,
    analysis
) {

    const preference =
        analysis.preference ||
        "balanced";


    const health =
        Number(route.road_health);


    if (preference === "road_condition") {

        return (
            "This route provides the strongest "
            +
            "road-condition score among the available routes."
        );
    }


    if (preference === "fastest") {

        return (
            "This route is selected because it provides "
            +
            "the best travel-time option."
        );
    }


    if (Number.isFinite(health) && health >= 75) {

        return (
            "This route offers a strong balance between "
            +
            "road quality, distance and travel time."
        );
    }


    return (
        "This route provides the best overall balance "
        +
        "according to RoadQuality's route scoring."
    );
}


/* =========================================================
   ROUTE COMPARISON
   ========================================================= */

function renderRouteComparison(
    routes,
    selectedIndex
) {

    const container =
        document.getElementById(
            "routeComparison"
        );


    if (!container) {
        return;
    }


    container.innerHTML = "";


    const count =
        document.getElementById(
            "routeCount"
        );


    if (count) {
        count.textContent =
            `${routes.length} routes`;
    }


    routes.slice(0, 3).forEach(
        (route, index) => {

            const card =
                document.createElement("div");


            card.className =
                "route-comparison-card";


            if (index === selectedIndex) {
                card.classList.add(
                    "selected"
                );
            }


            const health =
                Number(route.road_health);


            card.innerHTML = `
                <div class="route-card-header">

                    <div>
                        <span class="route-number">
                            ${index + 1}
                        </span>

                        <strong>
                            ${escapeHtml(
                                route.name ||
                                `Route ${index + 1}`
                            )}
                        </strong>
                    </div>

                    ${
                        index === selectedIndex
                            ? `<span class="recommended-badge">
                                Recommended
                               </span>`
                            : ""
                    }

                </div>


                <div class="route-card-stats">

                    <div>
                        <span>Distance</span>
                        <strong>
                            ${formatDistance(
                                route.distance
                            )}
                        </strong>
                    </div>


                    <div>
                        <span>Time</span>
                        <strong>
                            ${formatTime(
                                route.travel_time
                            )}
                        </strong>
                    </div>


                    <div>
                        <span>Road Health</span>
                        <strong class="${getHealthClass(health)}">
                            ${
                                Number.isFinite(health)
                                    ? `${health.toFixed(0)}%`
                                    : "--"
                            }
                        </strong>
                    </div>


                    <div>
                        <span>Score</span>
                        <strong>
                            ${
                                route.score != null
                                    ? Number(
                                        route.score
                                      ).toFixed(1)
                                    : "--"
                            }
                        </strong>
                    </div>

                </div>
            `;


            card.addEventListener(
                "click",
                () => {

                    localStorage.setItem(
                        STORAGE_SELECTED_ROUTE,
                        JSON.stringify(route)
                    );


                    recommendationLayers.forEach(
                        (layer, layerIndex) => {

                            layer.setStyle({
                                weight:
                                    layerIndex === index
                                        ? 8
                                        : 5,

                                opacity:
                                    layerIndex === index
                                        ? 0.95
                                        : 0.65
                            });
                        }
                    );


                    document
                        .querySelectorAll(
                            ".route-comparison-card"
                        )
                        .forEach(
                            element =>
                                element.classList.remove(
                                    "selected"
                                )
                        );


                    card.classList.add(
                        "selected"
                    );


                    setupStartNavigation(
                        route
                    );
                }
            );


            container.appendChild(card);
        }
    );
}


/* =========================================================
   AI EXPLANATION
   ========================================================= */

function renderAIExplanation(
    analysis,
    route
) {

    const element =
        document.getElementById(
            "aiExplanation"
        );


    if (!element) {
        return;
    }


    const aiSegments =
        Number(
            route.ai_segments ??
            analysis.ai_segments ??
            0
        );


    const osmSegments =
        Number(
            route.osm_segments ??
            analysis.osm_segments ??
            0
        );


    const coverage =
        Number(
            route.ai_coverage ??
            analysis.ai_coverage ??
            0
        );


    element.innerHTML = `
        <div class="ai-explanation-content">

            <div class="ai-explanation-icon">
                ✦
            </div>

            <div>

                <strong>
                    AI Route Analysis
                </strong>

                <p>
                    RoadQuality evaluated this route
                    using road-condition information
                    and available map data.
                </p>

                <div class="ai-metrics">

                    <span>
                        AI segments:
                        <b>${aiSegments}</b>
                    </span>

                    <span>
                        OSM segments:
                        <b>${osmSegments}</b>
                    </span>

                    <span>
                        Coverage:
                        <b>
                            ${
                                Number.isFinite(coverage)
                                    ? `${coverage.toFixed(0)}%`
                                    : "--"
                            }
                        </b>
                    </span>

                </div>

            </div>

        </div>
    `;
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
     * Remove previous listeners safely.
     */
    const newButton =
        button.cloneNode(true);


    button.parentNode.replaceChild(
        newButton,
        button
    );


    newButton.addEventListener(
        "click",
        () => {

            const analysisRaw =
                localStorage.getItem(
                    STORAGE_ANALYSIS
                );


            if (!analysisRaw) {

                showError(
                    "Route data is unavailable."
                );

                return;
            }


            let analysis;

            try {
                analysis =
                    JSON.parse(
                        analysisRaw
                    );
            } catch {

                showError(
                    "Unable to read route data."
                );

                return;
            }


            /*
             * Make sure coordinates are definitely
             * attached to the selected route.
             */
            const selectedRoute = {
                ...route,

                coordinates:
                    getRouteCoordinates(route)
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
   TEXT HELPER
   ========================================================= */

function setText(
    id,
    value
) {

    const element =
        document.getElementById(id);

    if (element) {
        element.textContent =
            value;
    }
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
     * Navigation page is implemented in
     * navigation.html.
     *
     * app.js does not duplicate its GPS logic.
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