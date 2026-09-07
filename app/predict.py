from ultralytics import YOLO
from pathlib import Path
import sys
import json
import csv

from road_condition import calculate_road_health
from road_observation import save_observation


# ============================================================
# ROADQUALITY - AI + GIS ROAD CONDITION ANALYSIS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

MODEL_PATH = BASE_DIR / "model" / "best.pt"

DEFAULT_SOURCE = BASE_DIR / "test_images"
DEFAULT_DESTINATION = BASE_DIR / "results"

LOCATION_FILE = BASE_DIR / "data" / "image_locations.csv"


# ============================================================
# LOAD IMAGE LOCATIONS
# ============================================================

def load_image_locations():

    locations = {}

    if not LOCATION_FILE.exists():

        print("\nWARNING: image_locations.csv not found.")
        return locations

    with open(
        LOCATION_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            image_name = row["image"].strip()

            locations[image_name] = {
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"])
            }

    return locations


# ============================================================
# LOAD MODEL
# ============================================================

print("=" * 70)
print("ROADQUALITY - AI + GIS ROAD CONDITION ANALYSIS")
print("=" * 70)

print("\nLoading YOLOv12s model...")
print("Model:", MODEL_PATH)

if not MODEL_PATH.exists():

    print("\nERROR: Model not found!")
    sys.exit(1)

model = YOLO(str(MODEL_PATH))

print("Model loaded successfully!")

print("\nClasses:")

for class_id, class_name in model.names.items():

    print(f"  {class_id}: {class_name}")


# ============================================================
# SOURCE / DESTINATION
# ============================================================

if len(sys.argv) >= 2:

    SOURCE = Path(sys.argv[1])

else:

    SOURCE = DEFAULT_SOURCE


if len(sys.argv) >= 3:

    DESTINATION = Path(sys.argv[2])

else:

    DESTINATION = DEFAULT_DESTINATION


DESTINATION.mkdir(
    parents=True,
    exist_ok=True
)


print("\n" + "=" * 70)
print("INPUT / OUTPUT")
print("=" * 70)

print("Source      :", SOURCE)
print("Destination :", DESTINATION)


if not SOURCE.exists():

    print("\nERROR: Source does not exist!")
    sys.exit(1)


# ============================================================
# LOAD GPS DATABASE
# ============================================================

image_locations = load_image_locations()

print("\nGPS locations loaded:", len(image_locations))


# ============================================================
# FIND INPUT IMAGES
# ============================================================

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp"
}


if SOURCE.is_file():

    if SOURCE.suffix.lower() not in IMAGE_EXTENSIONS:

        print(
            "\nERROR: Source file is not a supported image."
        )

        sys.exit(1)

    image_files = [SOURCE]

else:

    image_files = sorted([

        p for p in SOURCE.rglob("*")

        if p.is_file()
        and p.suffix.lower() in IMAGE_EXTENSIONS

    ])


print("\nImages found:", len(image_files))


if len(image_files) == 0:

    print("ERROR: No images found in source.")
    sys.exit(1)


# ============================================================
# PROCESS IMAGES
# ============================================================

all_assessments = []

print("\n" + "=" * 70)
print("RUNNING AI ROAD CONDITION ANALYSIS")
print("=" * 70)


for index, image_path in enumerate(
    image_files,
    start=1
):

    print("\n" + "-" * 70)

    print(
        f"IMAGE {index}/{len(image_files)}"
    )

    print("-" * 70)

    print("Source:", image_path)


    # --------------------------------------------------------
    # GPS LOCATION
    # --------------------------------------------------------

    location = image_locations.get(
        image_path.name
    )


    if location is None:

        print(
            "\nWARNING: GPS location not found "
            f"for {image_path.name}"
        )

        print(
            "Skipping GIS database update."
        )

    else:

        print(
            f"GPS: "
            f"{location['latitude']:.6f}, "
            f"{location['longitude']:.6f}"
        )


    # --------------------------------------------------------
    # YOLO PREDICTION
    # --------------------------------------------------------

    results = model.predict(

        source=str(image_path),

        imgsz=640,

        conf=0.25,

        save=False,

        verbose=False
    )

    result = results[0]


    # --------------------------------------------------------
    # EXTRACT DETECTIONS
    # --------------------------------------------------------

    detections = []


    if result.boxes is not None:

        for box in result.boxes:

            class_id = int(
                box.cls[0]
            )

            confidence = float(
                box.conf[0]
            )

            class_name = model.names[
                class_id
            ]

            detections.append({

                "class": class_name,

                "confidence": confidence

            })


    # --------------------------------------------------------
    # ROAD CONDITION ASSESSMENT
    # --------------------------------------------------------

    assessment = calculate_road_health(
        detections
    )

    assessment["image"] = image_path.name


    # --------------------------------------------------------
    # SAVE GIS OBSERVATION
    # --------------------------------------------------------

    if location is not None:

        segment_id = (
            f"S{index:03d}"
        )

        gis_detections = [

            {
                "class_name":
                    d["class"],

                "confidence":
                    d["confidence"]
            }

            for d in detections

        ]


        save_observation(

            segment_id=segment_id,

            latitude=location["latitude"],

            longitude=location["longitude"],

            health_score=
                assessment[
                    "road_health_score"
                ],

            detections=gis_detections
        )


        print("\nGIS OBSERVATION SAVED")

        print(
            "  Segment:",
            segment_id
        )

        print(
            "  Latitude:",
            location["latitude"]
        )

        print(
            "  Longitude:",
            location["longitude"]
        )


    # --------------------------------------------------------
    # SAVE ANNOTATED IMAGE
    # --------------------------------------------------------

    annotated = result.plot()

    output_image = (
        DESTINATION
        /
        f"{image_path.stem}_result.jpg"
    )


    from PIL import Image

    Image.fromarray(
        annotated[:, :, ::-1]
    ).save(output_image)


    # --------------------------------------------------------
    # PRINT RESULTS
    # --------------------------------------------------------

    print("\nDETECTIONS")


    if len(detections) == 0:

        print(
            "  No road defects detected."
        )

    else:

        for i, detection in enumerate(
            detections,
            start=1
        ):

            print(

                f"  {i}. "
                f"{detection['class']} | "
                f"Confidence: "
                f"{detection['confidence'] * 100:.2f}%"

            )


    print(
        "\nROAD CONDITION ASSESSMENT"
    )

    print(
        "  Total detections :",
        assessment[
            "total_detections"
        ]
    )

    print(
        "  Damage score     :",
        assessment[
            "damage_score"
        ]
    )

    print(
        "  Road Health Score:",
        assessment[
            "road_health_score"
        ],
        "/ 100"
    )

    print(
        "  Condition        :",
        assessment[
            "condition"
        ]
    )


    print(
        "\nOutput:",
        output_image
    )


    all_assessments.append(
        assessment
    )


# ============================================================
# SAVE JSON REPORT
# ============================================================

report_path = (
    DESTINATION
    /
    "road_condition_report.json"
)


with open(
    report_path,
    "w",
    encoding="utf-8"
) as f:

    json.dump(

        all_assessments,

        f,

        indent=4

    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 70)

print(
    "ROADQUALITY AI + GIS ANALYSIS COMPLETED"
)

print("=" * 70)

print(
    "Images processed :",
    len(all_assessments)
)

print(
    "\nResults saved to:"
)

print(DESTINATION)

print(
    "\nGIS database:"
)

print(
    BASE_DIR
    /
    "data"
    /
    "road_condition_data.csv"
)

print(
    "\nReport:"
)

print(report_path)

print("=" * 70)