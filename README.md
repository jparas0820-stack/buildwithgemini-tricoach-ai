# TriCoach AI 🏊‍♂️🚴‍♂️🏃‍♂️

TriCoach AI is an intelligent conversational triathlon and endurance fitness coach built with the Google Agent Development Kit (ADK) and deployed on Agent Platform (Agent Engine / Agent Runtime).

![TriCoach AI Demo](agent_demo.gif)

---

## 🌟 What TriCoach AI Does

TriCoach AI assists endurance athletes, triathletes, and fitness enthusiasts with personalized training plans, workout management, nutrition and allergy safety, location-based facility searches, weather advisories, custom visuals, and AI-generated technique videos.

### Implemented Features & Tools

- **Cross-Session Long-Term Memory (Vertex AI Memory Bank)**:
  - Uses `VertexAiMemoryBankService` and `PreloadMemoryTool` to retain athlete preferences, health conditions, dietary restrictions, and allergies across sessions.
  - Ensures safety by consulting preloaded memories before recommending nutrition or sports drinks.

- **Workout Schedule Management (Google Cloud Firestore)**:
  - `list_workouts`: Queries the `triathlon_workouts` Firestore database filtered by sport (`swim`, `bike`, `run`, `brick`) and difficulty level (`Beginner`, `Intermediate`, `Advanced`).
  - `get_workout`: Retrieves detailed workout structures by ID.
  - `add_workout`: Saves new workout plans or updates existing entries in Firestore.

- **Training Zone Calculations**:
  - `calculate_training_zones`: Computes 5-zone power targets (FTP in Watts) or heart rate zones (BPM).

- **Location-Based Training Facility Search (Google Maps Platform)**:
  - `geocode_address`: Converts location strings or addresses into exact latitude and longitude coordinates.
  - `find_nearby_places`: Locates nearby gyms, pools, athletic tracks, and sports complexes using the Google Places API (New).

- **Live Outdoor Weather Conditions**:
  - `get_outdoor_weather_conditions`: Fetches real-time temperature and wind speed via Open-Meteo API, providing tailored heat/cold/wind training advisories.

- **AI Route & Poster Visual Generation (Vertex AI Image Generation)**:
  - `generate_workout_visual`: Generates custom workout route maps, race finish posters, and motivational badges using `gemini-3.1-flash-lite-image`.
  - Saves generated images to Playground Artifacts and uploads raw bytes directly to a public Cloud Storage bucket (`tricoach-ai-media-qwiklabs-gcp-02-23cc191dff3a`).

- **AI Technique Video Generation (Vertex AI Omni Model)**:
  - `generate_workout_video`: Generates short video clips of triathlon swim/bike/run technique using Google's Omni model (`gemini-omni-flash-preview`) in the `global` region via the Interactions API.
  - Saves generated MP4 bytes to Playground Artifacts and uploads directly to public Cloud Storage.

- **Secure Python Code Execution**:
  - `AgentEngineSandboxCodeExecutor`: Runs Python code in a secure Agent Engine sandbox for custom data processing and calculations.

- **Structured Display UI (A2UI v0.8)**:
  - Renders structured UI cards (`Card`, `Column`, `Row`, `Text`, `Image`) in supporting interfaces using `a2ui_callback`.

---

## 🏗️ Architecture & Technology Stack

- **Framework**: Google Agent Development Kit (ADK 1.1.0)
- **Model**: `gemini-flash-latest` (Interactions & Content Generation)
- **Database**: Google Cloud Firestore (`triathlon_workouts` collection)
- **Storage**: Google Cloud Storage (`tricoach-ai-media-qwiklabs-gcp-02-23cc191dff3a`)
- **Memory**: Vertex AI Memory Bank (`VertexAiMemoryBankService`)
- **Frontend**: Custom FastAPI proxy & HTML/CSS chat interface (`frontend/`)
- **Deployment Target**: Agent Runtime / Agent Engine (`us-east1`)

---

## 🚀 Setup & Local Execution

### Prerequisites

- Python 3.10+
- Node.js 18+
- Google Cloud SDK (`gcloud`) authenticated with a project containing Vertex AI, Firestore, and Cloud Storage permissions.

### 1. Backend Agent Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables in `.env`:
   ```bash
   GOOGLE_GENAI_USE_VERTEXAI=true
   GOOGLE_CLOUD_PROJECT=your-gcp-project-id
   GOOGLE_CLOUD_LOCATION=global
   GOOGLE_MAPS_API_KEY=your-google-maps-api-key
   ```

3. Run the agent locally or in the ADK Web UI:
   ```bash
   adk web
   ```

### 2. Frontend Chat UI Setup

1. Navigate to the `frontend/` directory and install dependencies:
   ```bash
   cd frontend
   pip install -r requirements.txt
   ```

2. Set required environment variables:
   ```bash
   export AGENT_ENGINE_RESOURCE_NAME="projects/your-project-id/locations/us-east1/reasoningEngines/your-engine-id"
   export AGENT_DIRECTORY="app"
   ```

3. Start the FastAPI server locally:
   ```bash
   python main.py
   ```

4. Open your browser and navigate to the local server port printed in the terminal (default port 8080).
