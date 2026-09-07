from ultralytics import YOLO
from pathlib import Path
import csv


# ============================================================
# ROADQUALITY - GENERATE AI ROAD HEALTH SCORES
# ============================================================

MODEL_PATH = r"C:\Users\samue\runs\detect\road_quality_training\improved_2epochs\weights\best.pt"

IMAGE_DIR = Path(
    r"C:\Users\samue\Downloads\collection\roadquality\Dataset\images\test"
)

OUTPUT_FILE = "ai_road_scores.csv"

CONFIDENCE_THRESHOLD = 0.60


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("ROADQUALITY - AI ROAD HEALTH SCORE GENERATION")
print("=" * 70)

print("\nLoading trained YOLO model...")

model = YOLO(MODEL_PATH)

print("Model loaded successfully.")


# ============================================================
# GET ALL TEST IMAGES
# ============================================================

print("\nSearching test images...")

images = sorted(
    list(IMAGE_DIR.glob("*.jpg")) +
    list(IMAGE_DIR.glob("*.jpeg")) +
    list(IMAGE_DIR.glob("*.png"))
)

print(f"Total images found: {len(images)}")

if not images:
    raise FileNotFoundError(
        f"No images found in: {IMAGE_DIR}"
    )


# ============================================================
# PROCESS IMAGES
# ============================================================

rows = []

print("\nStarting AI road-condition analysis...")
print("This may take some time because all test images are processed.")
print()


for index, image_path in enumerate(images, start=1):

    try:

        results = model.predict(
            source=str(image_path),
            imgsz=640,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False
        )

        result = results[0]

        detections = []

        if result.boxes is not None:

            for box in result.boxes:

                confidence = float(
                    box.conf[0]
                )

                class_id = int(
                    box.cls[0]
                )

                # ------------------------------------------------
                # Calculate bounding-box area percentage
                # ------------------------------------------------

                x1, y1, x2, y2 = (
                    box.xyxy[0].tolist()
                )

                box_width = max(
                    0,
                    x2 - x1
                )

                box_height = max(
                    0,
                    y2 - y1
                )

                box_area = (
                    box_width *
                    box_height
                )

                image_height, image_width = (
                    result.orig_shape
                )

                image_area = (
                    image_width *
                    image_height
                )

                if image_area > 0:

                    area_percent = (
                        box_area /
                        image_area
                    ) * 100

                else:

                    area_percent = 0


                detections.append({
                    "class_id": class_id,
                    "confidence": confidence,
                    "area": area_percent
                })


        # ========================================================
        # CALCULATE HEALTH SCORE
        # ========================================================

        if not detections:

            detected_classes = "None"

            max_confidence = 0.0

            max_area = 0.0

            health_score = 100.0

            condition = "GOOD"

        else:

            # Use strongest detection
            strongest = max(
                detections,
                key=lambda x: x["confidence"]
            )

            max_confidence = (
                strongest["confidence"]
            )

            max_area = (
                strongest["area"]
            )

            detected_classes = ",".join(
                str(d["class_id"])
                for d in detections
            )

            # ----------------------------------------------------
            # Convert damage area into a bounded coverage value
            # ----------------------------------------------------

            damage_coverage = min(
                max_area / 100.0,
                0.50
            )

            # ----------------------------------------------------
            # Calculate penalty
            # ----------------------------------------------------

            penalty = (
                max_confidence
                * (damage_coverage / 0.50)
                * 70
            )

            penalty = min(
                penalty,
                70
            )

            # ----------------------------------------------------
            # Road health
            # ----------------------------------------------------

            health_score = (
                100 - penalty
            )

            # ----------------------------------------------------
            # Condition classification
            # ----------------------------------------------------

            if health_score >= 80:

                condition = "GOOD"

            elif health_score >= 60:

                condition = "MODERATE"

            elif health_score >= 40:

                condition = "POOR"

            else:

                condition = "VERY POOR"


        # ========================================================
        # SAVE RESULT
        # ========================================================

        rows.append({

            "image":
                image_path.name,

            "detected_classes":
                detected_classes,

            "max_confidence":
                round(
                    max_confidence,
                    3
                ),

            "max_damage_area_percent":
                round(
                    max_area,
                    2
                ),

            "road_health_score":
                round(
                    health_score,
                    2
                ),

            "condition":
                condition
        })


        # ========================================================
        # PROGRESS
        # ========================================================

        if (
            index == 1
            or index % 100 == 0
            or index == len(images)
        ):

            print(
                f"Processed "
                f"{index:,} / "
                f"{len(images):,} images"
            )


    except Exception as error:

        print(
            f"\nWARNING: Failed to process "
            f"{image_path.name}"
        )

        print(
            f"Reason: {error}"
        )

        continue


# ============================================================
# SAVE CSV
# ============================================================

print("\n")
print("Saving AI road scores...")

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as file:

    fieldnames = [

        "image",

        "detected_classes",

        "max_confidence",

        "max_damage_area_percent",

        "road_health_score",

        "condition"
    ]

    writer = csv.DictWriter(
        file,
        fieldnames=fieldnames
    )

    writer.writeheader()

    writer.writerows(rows)


# ============================================================
# SUMMARY
# ============================================================

scores = [

    row["road_health_score"]

    for row in rows

]


average_score = (

    sum(scores) /
    len(scores)

    if scores

    else 0
)


print()
print("=" * 70)
print("AI ROAD SCORE GENERATION COMPLETED")
print("=" * 70)

print(
    f"Images found       : "
    f"{len(images):,}"
)

print(
    f"Images processed    : "
    f"{len(rows):,}"
)

print(
    f"Average health      : "
    f"{average_score:.2f} / 100"
)

print(
    f"Output file         : "
    f"{OUTPUT_FILE}"
)

print("=" * 70)