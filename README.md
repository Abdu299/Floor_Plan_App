# Floor Plan Analysis System

A full-stack floor plan analysis system developed as part of a master's thesis in Programming and System Architecture.

The application takes a floor plan image, analyzes it using computer vision and OCR, converts the result into structured data, allows the user to manually correct the detected elements, validates the floor plan, and stores revisions for later use.

The project is designed as a foundation for future floor plan optimization and constraint-based analysis.

---

## Overview

The system combines three main applications:

- **Python detection service** for computer vision, OCR, and geometric analysis
- **ASP.NET Core API** for persistence, validation, revisions, and business logic
- **React frontend** for uploading, visualizing, correcting, and managing floor plans

Docker Compose connects all three services and allows the entire application to be started with one command.

---

# Main Features

## Automated Floor Plan Detection

The Python detection pipeline analyzes uploaded floor plan images and detects:

- Rooms
- Room names
- Doors
- Windows
- Openings between rooms
- Room polygons and positions
- Connections between rooms

Several techniques and models are combined rather than relying on one model.

---

## Room Detection

Room detection uses an MMDetection Cascade R-CNN model.

The detector finds room regions in the original image and returns their positions and confidence values.

Detected room regions are later processed geometrically to produce usable room polygons.

---

## Room Name Recognition

EasyOCR is used to read text inside the floor plan.

Examples include:

```text
Kitchen
Bathroom
Bedroom
Living Room
Hall
Storage
Office
```

OCR results are associated with detected room polygons based on their position in the image.

The system also supports variations such as:

```text
Bathroom 1
Bathroom 2
Dining Room Kitchen
Kitchen 1
Main Bathroom
```

---

## Door and Window Detection

A trained YOLO model detects architectural objects such as:

```text
Doors
Windows
```

Detected doors are associated with nearby rooms so the system can determine which rooms are connected.

---

## Opening Detection

Some floor plans contain connections without a traditional door symbol.

A rule-based opening detector analyzes wall geometry and searches for gaps that may represent:

```text
Open doorways
Large passages
Open-plan connections
Missing wall sections
```

Known doors and windows are excluded to reduce duplicate detections.

---

# Floor Plan Validation

The system performs basic prototype validation.

A floor plan is currently considered structurally valid when it contains:

```text
At least one room
At least one bathroom
At least one kitchen or cooking area
At least one door OR opening
```

Windows are not required for validation.

Before a user-corrected revision can be saved, every room must also have a valid manually entered real-world area:

```text
Area > 0 m²
```

The current validation is prototype logic and is **not full TEK17 or building regulation compliance validation**.

---

# Human Correction

AI detections are not assumed to be perfect.

The frontend allows users to inspect and correct the result.

Users can:

```text
Rename rooms
Enter room areas
Move detected objects
Delete incorrect detections
Add rooms
Add doors
Add windows
Add openings
Change room connections
```

This creates a human-in-the-loop workflow where automatic detection provides the initial structure and the user can correct mistakes before later processing.

---

# Revision System

The application stores floor plans using revisions.

The original AI detection is stored as:

```text
Revision 1
Source: AI
```

It is never overwritten.

When the user makes corrections and saves them, a new revision is created:

```text
Revision 2
Source: User
```

Additional corrections create:

```text
Revision 3
Revision 4
...
```

Each revision keeps a reference to the revision it was based on.

This makes it possible to preserve the original AI output while maintaining a history of later corrections.

---

# Coordinate System

All geometry is stored using the coordinates of the **original uploaded image**.

For example:

```json
{
  "x": 425.5,
  "y": 311.2
}
```

The React interface may scale the image visually, but stored room, door, window, and opening coordinates remain in original image pixel coordinates.

This prevents geometry from changing when the browser window or display size changes.

---

# Architecture

The project contains three main services.

```text
Browser
   |
   v
React + Nginx
FloorPlan.Web
Port 3000
   |
   | HTTP /api/*
   v
ASP.NET Core API
FloorPlan.Api
Port 5131
   |
   | HTTP
   v
Python FastAPI Detector
ProjectMaster
Port 8000
```

The ASP.NET API communicates with Python internally through Docker using:

```text
http://detector:8000
```

The browser does not need to communicate directly with the Python service.

---

# Technology Stack

## Frontend

```text
React
TypeScript
Vite
React Router
react-konva
Nginx
```

React Konva is used to draw detected floor plan geometry and allow interactive editing.

---

## Backend

```text
C#
ASP.NET Core Web API
Entity Framework Core
SQLite
REST API
```

The backend is responsible for:

```text
Database access
Floor plan persistence
Revision management
Validation
Uploaded image storage
Communication with Python
REST API endpoints
```

---

## Detection Service

```text
Python
FastAPI
MMDetection
MMCV
MMEngine
PyTorch
YOLO / Ultralytics
EasyOCR
OpenCV
Shapely
NumPy
```

---

## Deployment

```text
Docker
Docker Compose
Nginx
```

Docker allows the application and its dependencies to run consistently without requiring users to manually install Python packages, .NET packages, OCR libraries, or machine-learning frameworks.

---

# Project Structure

```text
FLOOR_PLAN_APP/
│
├── README.md
├── compose.yaml
│
├── ProjectMaster/
│   │
│   ├── api.py
│   ├── detection_pipeline.py
│   ├── requirements.txt
│   ├── install_openmmlab.sh
│   ├── Dockerfile
│   │
│   ├── configs/
│   │   ├── floorPlan.py
│   │   ├── room.py
│   │   ├── door.py
│   │   └── ...
│   │
│   ├── detections/
│   │   ├── room_detection.py
│   │   ├── objectDetect.py
│   │   ├── openingDetect_new.py
│   │   └── ...
│   │
│   └── weights/
│       ├── best.pt
│       └── cascade_swin_latest.pth
│
└── FloorPlanSystem/
    │
    ├── FloorPlan.Api/
    │   ├── Controllers/
    │   ├── Data/
    │   ├── Models/
    │   ├── Services/
    │   ├── Migrations/
    │   ├── Program.cs
    │   ├── Dockerfile
    │   └── FloorPlan.Api.csproj
    │
    └── FloorPlan.Web/
        ├── src/
        │   ├── components/
        │   ├── pages/
        │   ├── App.tsx
        │   ├── api.ts
        │   └── types.ts
        │
        ├── Dockerfile
        ├── nginx.conf
        ├── package.json
        └── vite.config.ts
```

Some filenames may change as the project develops.

---

# Installation

## Recommended Method: Docker

Docker is the recommended way to run the project.

You do **not** need to manually install:

```text
Python dependencies
PyTorch
MMDetection
EasyOCR
ASP.NET packages
Node packages
Nginx
SQLite
```

Docker installs and configures these inside the containers.

---

## Requirements

Install:

### Docker Desktop

Docker Desktop must be installed and running.

Verify Docker:

```bash
docker --version
```

Verify Docker Compose:

```bash
docker compose version
```

---

# Model Weights

The detection service requires trained model weights.

Required files:

```text
ProjectMaster/weights/best.pt
ProjectMaster/weights/cascade_swin_latest.pth
```

If the model weights are not included in the repository, download them from:

```text
MODEL WEIGHTS DOWNLOAD LINK:
ADD_LINK_HERE
```

Then place them in:

```text
ProjectMaster/
└── weights/
    ├── best.pt
    └── cascade_swin_latest.pth
```

The Docker build checks that these files exist.

---

# Running the Application

Open a terminal in the project root:

```bash
cd FLOOR_PLAN_APP
```

The directory should contain:

```text
compose.yaml
ProjectMaster/
FloorPlanSystem/
```

Start the complete system:

```bash
docker compose up --build
```

Docker will:

```text
Build the Python detector
Build the ASP.NET API
Build the React frontend
Create the Docker network
Create persistent storage
Start all three services
Load the AI models
Apply database migrations
Start the application
```

The first build may take several minutes because PyTorch, MMDetection, EasyOCR, and other machine-learning dependencies must be installed.

Later builds are normally faster because Docker caches dependencies.

---

# Open the Application

After the services have started, open:

```text
http://localhost:3000
```

The React frontend is served through Nginx.

---

# Service URLs

Frontend:

```text
http://localhost:3000
```

ASP.NET API:

```text
http://localhost:5131
```

API health endpoint:

```text
http://localhost:5131/health
```

Python detector:

```text
http://localhost:8000
```

Python health endpoint:

```text
http://localhost:8000/health
```

---

# Running in the Background

Instead of displaying all logs in the terminal:

```bash
docker compose up -d
```

Check running containers:

```bash
docker compose ps
```

---

# View Logs

All services:

```bash
docker compose logs -f
```

Python detector only:

```bash
docker compose logs -f detector
```

ASP.NET API only:

```bash
docker compose logs -f floorplan-api
```

Frontend only:

```bash
docker compose logs -f floorplan-web
```

---

# Stop the Application

Run:

```bash
docker compose down
```

This removes the running containers and Docker network but keeps the saved database and uploaded images.

---

# Persistent Data

The project uses Docker volumes.

Database:

```text
floorplan-db
```

Uploaded images:

```text
floorplan-uploads
```

Therefore this is safe:

```bash
docker compose down
docker compose up -d
```

Previously saved floor plans will still exist.

Do **not** run this unless you intentionally want to delete saved data:

```bash
docker compose down -v
```

The `-v` option removes the persistent Docker volumes.

---

# Updating the Code

Docker images contain a copy of the source code at build time.

If source code changes, the relevant service must be rebuilt.

## Python changed

```bash
docker compose up -d --build detector
```

## ASP.NET changed

```bash
docker compose up -d --build floorplan-api
```

## React changed

```bash
docker compose up -d --build floorplan-web
```

## Multiple parts changed

```bash
docker compose up -d --build
```

Simply running:

```bash
docker compose restart detector
```

does **not** rebuild the image and therefore does not include changed source files.

---

# Typical Workflow

Upload a floor plan image from the frontend.

The request follows this flow:

```text
User uploads image
        |
        v
React frontend
        |
        v
ASP.NET API
        |
        v
Python detection API
        |
        v
Room detection
        |
        +--> MMDetection
        |
        +--> EasyOCR
        |
        +--> YOLO
        |
        +--> Opening detection
        |
        v
Structured detection result
        |
        v
ASP.NET stores Revision 1
        |
        v
React displays result
        |
        v
User corrects detections
        |
        v
Validation
        |
        v
ASP.NET stores Revision 2+
```

---

# Database

SQLite is currently used because it is lightweight and easy to distribute.

Entity Framework Core manages the database schema.

Database migrations are automatically applied when the ASP.NET container starts.

Users therefore do not normally need to run:

```bash
dotnet ef database update
```

manually.

The architecture can later be migrated to PostgreSQL or PostgreSQL/PostGIS if more advanced spatial storage is required.

---

# API Communication

The React frontend communicates with ASP.NET using HTTP REST endpoints.

Examples include:

```text
POST   /api/detection
GET    /api/floorplans
GET    /api/floorplans/{id}
DELETE /api/floorplans/{id}
POST   /api/floorplans/{id}/revisions
POST   /api/floorplans/{id}/measurements
GET    /api/floorplans/{id}/measurements/latest
```

Inside Docker, ASP.NET communicates with Python using:

```text
http://detector:8000
```

Docker's internal DNS automatically resolves the service name `detector`.

---

# Why Three Separate Services?

The project separates responsibilities.

## Python

Responsible for machine learning and computer vision.

## ASP.NET

Responsible for the application backend, persistence, validation, revisions, and API logic.

## React

Responsible for visualization and user interaction.

This makes the architecture easier to maintain and allows each part to evolve independently.

For example, the detection models can be changed without rewriting the frontend or database architecture.

---

# Current Limitations

This project is a research prototype.

Detection quality depends on:

```text
Image resolution
Floor plan drawing style
OCR quality
Model confidence
Wall visibility
Room label positioning
```

The system may therefore detect incorrect rooms, doors, windows, openings, or room labels.

The manual correction interface exists specifically so users can correct these results.

Validation currently represents prototype constraints and should not be interpreted as complete architectural or regulatory approval.

---

# Future Development

The current structured and corrected floor plan data is intended to support later work such as:

```text
Mathematical floor plan optimization
Constraint-based optimization
TEK17-related analysis
Accessibility constraints
Emergency exit analysis
Room adjacency optimization
Automatic layout improvements
GeoJSON export
CAD/BIM integration
PostgreSQL/PostGIS storage
Comparison of original and optimized floor plans
```

A major goal of the architecture is to ensure that optimization uses the **confirmed human-corrected revision** rather than blindly using the initial AI result.

---

# Research Goal

The project investigates how computer vision, OCR, geometric analysis, human correction, structured data storage, and optimization can be combined into one floor plan processing workflow.

The overall concept is:

```text
Image
  ↓
AI detection
  ↓
Structured floor plan
  ↓
Human verification
  ↓
Validated revision
  ↓
Optimization / constraint analysis
```

This separation is important because computer vision results are probabilistic, while optimization requires reliable structured input.

---

# Development Status

Current implementation includes:

```text
Automated room detection
OCR room-name recognition
Door detection
Window detection
Opening detection
Room connectivity
Floor plan visualization
Interactive correction
Object creation and deletion
Room renaming
Manual room areas
Floor plan validation
Revision history
SQLite persistence
Uploaded-image persistence
REST API
Dockerized Python detector
Dockerized ASP.NET API
Dockerized React frontend
Docker Compose setup
```

Future development will focus primarily on optimization and additional constraint analysis.

---

# Author

Developed as part of a master's thesis in:

**Programming and System Architecture**

The project is intended for research, experimentation, and development of automated floor plan analysis and optimization techniques.

---

# Quick Start

For users who already have Docker installed:

```bash
git clone YOUR_REPOSITORY_URL
cd FLOOR_PLAN_APP

docker compose up --build
```

Then open:

```text
http://localhost:3000
```

To stop:

```bash
docker compose down
```