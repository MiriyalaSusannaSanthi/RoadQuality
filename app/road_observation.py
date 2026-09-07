import csv
import os


# ============================================================
# ROADQUALITY - ROAD CONDITION GIS OBSERVATION DATABASE
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

OUTPUT_FILE = os.path.join(
    DATA_DIR,
    "road_condition_data.csv"
)


# ============================================================
# CONDITION CLASSIFICATION
# ============================================================

def get_condition(health):

    if health >= 80:
        return "Good"

    elif health >= 60:
        return "Moderate"

    elif health >= 40:
        return "Poor"

    return "Very Poor"


# ============================================================
# SAVE ONE OBSERVATION
# ============================================================

def save_observation(
    segment_id,
    latitude,
    longitude,
    health_score,
    detections
):

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    file_exists = os.path.exists(
        OUTPUT_FILE
    )

    file_empty = (
        not file_exists
        or os.path.getsize(OUTPUT_FILE) == 0
    )

    with open(
        OUTPUT_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)

        if file_empty:

            writer.writerow([
                "segment_id",
                "latitude",
                "longitude",
                "health_score",
                "condition",
                "detections"
            ])

        detection_text = "; ".join(

            f"{d['class_name']}:{d['confidence']:.2f}"

            for d in detections

        )

        writer.writerow([

            segment_id,

            round(float(latitude), 6),

            round(float(longitude), 6),

            round(float(health_score), 2),

            get_condition(
                health_score
            ),

            detection_text

        ])


# ============================================================
# SAVE MULTIPLE OBSERVATIONS
# ============================================================

def save_observations(
    observations
):

    if not observations:

        return

    for observation in observations:

        save_observation(

            segment_id=
                observation["segment_id"],

            latitude=
                observation["latitude"],

            longitude=
                observation["longitude"],

            health_score=
                observation["health_score"],

            detections=
                observation.get(
                    "detections",
                    []
                )

        )


# ============================================================
# LOAD OBSERVATIONS
# ============================================================

def load_observations():

    observations = []

    if not os.path.exists(
        OUTPUT_FILE
    ):

        return observations

    with open(
        OUTPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            observations.append({

                "segment_id":
                    row["segment_id"],

                "latitude":
                    float(
                        row["latitude"]
                    ),

                "longitude":
                    float(
                        row["longitude"]
                    ),

                "health_score":
                    float(
                        row["health_score"]
                    ),

                "condition":
                    row["condition"],

                "detections":
                    row["detections"]

            })

    return observations


# ============================================================
# DATABASE SUMMARY
# ============================================================

def print_database():

    observations = load_observations()

    print("\n" + "=" * 70)

    print(
        "ROADQUALITY - GIS OBSERVATION DATABASE"
    )

    print("=" * 70)

    print(
        f"\nTotal observations: "
        f"{len(observations)}"
    )

    for observation in observations:

        print(

            f"{observation['segment_id']} | "

            f"({observation['latitude']}, "
            f"{observation['longitude']}) | "

            f"Health: "
            f"{observation['health_score']} | "

            f"{observation['condition']}"

        )

    print(
        "\nDatabase:"
    )

    print(
        OUTPUT_FILE
    )

    print("\n" + "=" * 70)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print_database()