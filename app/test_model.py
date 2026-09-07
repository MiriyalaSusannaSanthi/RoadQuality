from ultralytics import YOLO
import os

MODEL_PATH = r"C:\Users\samue\Documents\RoadQuality_Final\model\best.pt"

print("=" * 70)
print("LOADING FINAL ROADQUALITY MODEL")
print("=" * 70)

print("Model exists:", os.path.exists(MODEL_PATH))
print(
    "Model size:",
    round(os.path.getsize(MODEL_PATH) / (1024**2), 2),
    "MB"
)

model = YOLO(MODEL_PATH)

print("\nModel loaded successfully!")

print("\nClasses:")
for class_id, class_name in model.names.items():
    print(f"  {class_id}: {class_name}")

print("=" * 70)
print("✅ FINAL MODEL READY")
print("=" * 70)