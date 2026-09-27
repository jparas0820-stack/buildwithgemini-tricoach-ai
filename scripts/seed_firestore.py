"""Seed script for populating Firestore database with triathlon workout plans."""

import subprocess
from google.cloud import firestore
from google.oauth2.credentials import Credentials

# Hardcoded project ID as required for Agent Platform compatibility
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-23cc191dff3a"
COLLECTION_NAME = "workouts"

WORKOUTS_DATA = [
    {
        "id": "swim_endurance_base",
        "title": "Aerobic Swim Base Builder",
        "sport": "swim",
        "discipline": "Swimming",
        "duration_minutes": 45,
        "difficulty": "Intermediate",
        "description": "200m easy warm up, 4x100m technique drills, 8x200m Zone 2 aerobic pacing, 200m easy cool down.",
        "target_zones": "Zone 2 (Aerobic)",
        "equipment": ["goggles", "swim cap", "pull buoy", "paddles"],
    },
    {
        "id": "bike_ftp_intervals",
        "title": "Sweetspot FTP Booster",
        "sport": "bike",
        "discipline": "Cycling",
        "duration_minutes": 60,
        "difficulty": "Advanced",
        "description": "15 min warm up, 4x10 min at 88-92% FTP (Sweetspot) with 3 min recovery, 9 min cool down.",
        "target_zones": "Zone 3 (Sweetspot) / Zone 4 (Threshold)",
        "equipment": ["smart trainer / road bike", "heart rate monitor", "power meter"],
    },
    {
        "id": "run_tempo_pyramid",
        "title": "Pacing Pyramid Run",
        "sport": "run",
        "discipline": "Running",
        "duration_minutes": 50,
        "difficulty": "Intermediate",
        "description": "10 min Zone 2 jog, 5-4-3-2-1 min tempo intervals with 90s jog recovery, 10 min cool down.",
        "target_zones": "Zone 3 / Zone 4 (Tempo & Threshold)",
        "equipment": ["running shoes", "GPS watch", "heart rate monitor"],
    },
    {
        "id": "brick_703_transition",
        "title": "70.3 Race Simulation Brick",
        "sport": "brick",
        "discipline": "Triathlon",
        "duration_minutes": 90,
        "difficulty": "Advanced",
        "description": "60 min Zone 3 tempo ride immediately followed by a 30 min Zone 3 race-pace run transition.",
        "target_zones": "Zone 3 (Tempo)",
        "equipment": ["tri bike", "running shoes", "nutrition/hydration"],
    },
]


def get_db_client():
    """Instantiates Firestore client using hardcoded project ID."""
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        credentials = Credentials(token)
        return firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials)
    except Exception:
        return firestore.Client(project=FIRESTORE_PROJECT_ID)


def seed_database():
    """Seeds the Firestore workouts collection."""
    print(f"Connecting to Firestore for project: '{FIRESTORE_PROJECT_ID}'...")
    db = get_db_client()
    collection_ref = db.collection(COLLECTION_NAME)

    for item in WORKOUTS_DATA:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(item)
        print(f"  ✓ Seeded document '{doc_id}': {item['title']}")

    print(f"\nSuccessfully seeded {len(WORKOUTS_DATA)} workouts into collection '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    seed_database()
