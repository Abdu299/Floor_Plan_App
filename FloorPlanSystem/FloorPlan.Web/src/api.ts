import type {
  DetectionUploadResponse,
  FloorPlan,
  FloorPlanMeasurement,
  PixelPoint,
} from "./types";


// =========================================================
// API URL
// =========================================================
//
// LOCAL DEVELOPMENT:
//
// VITE_API_URL=http://localhost:5131
//
// DOCKER:
//
// No VITE_API_URL is required.
//
// The browser will use relative URLs:
//
// /api/...
// /uploads/...
//
// Nginx will forward those requests to the ASP.NET
// container.
// =========================================================

const API_URL =
  (
    import.meta.env.VITE_API_URL
    ??
    ""
  ).replace(/\/$/, "");


// =========================================================
// UPLOAD
// =========================================================

export async function uploadFloorPlan(
  file: File
): Promise<DetectionUploadResponse> {

  const formData =
    new FormData();


  formData.append(
    "image",
    file
  );


  const response =
    await fetch(
      `${API_URL}/api/detection`,
      {
        method: "POST",
        body: formData,
      }
    );


  if (!response.ok) {

    const text =
      await response.text();


    throw new Error(
      `Detection failed: ${text}`
    );
  }


  return await response.json();
}


// =========================================================
// GET FLOOR PLAN
// =========================================================

export async function getFloorPlan(
  floorPlanId: number
): Promise<FloorPlan> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans/${floorPlanId}`
    );


  if (!response.ok) {

    const text =
      await response.text();


    throw new Error(
      `Could not load floor plan: ${text}`
    );
  }


  return await response.json();
}


// =========================================================
// SAVE REVISION
// =========================================================

export interface SavedRevisionResponse {
  floorPlanId: number;

  revisionId: number;

  revisionNumber: number;

  basedOnRevisionId: number;

  source: string;

  status: string;

  createdAtUtc: string;
}


export async function saveCorrectedRevision(
  floorPlan: FloorPlan
): Promise<SavedRevisionResponse> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans/${floorPlan.floorPlanId}/revisions`,
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json",
        },

        body: JSON.stringify({
          basedOnRevisionId:
            floorPlan.revision.revisionId,

          validation:
            floorPlan.revision.validation,

          rooms:
            floorPlan.revision.rooms,

          doors:
            floorPlan.revision.doors,

          windows:
            floorPlan.revision.windows,

          openings:
            floorPlan.revision.openings,
        }),
      }
    );


  if (!response.ok) {

    const text =
      await response.text();


    throw new Error(
      `Could not save revision ` +
      `(${response.status}): ${text}`
    );
  }


  return await response.json();
}


// =========================================================
// SAVE SCALE
// =========================================================

export async function saveFloorPlanMeasurement(
  floorPlanId: number,
  start: PixelPoint,
  end: PixelPoint,
  actualDistance: number,
  unit: string
): Promise<FloorPlanMeasurement> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans/${floorPlanId}/measurements`,
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json",
        },

        body: JSON.stringify({
          startX: start.x,
          startY: start.y,

          endX: end.x,
          endY: end.y,

          actualDistance,
          unit,
        }),
      }
    );


  if (!response.ok) {

    const text =
      await response.text();


    throw new Error(
      `Could not save scale ` +
      `(${response.status}): ${text}`
    );
  }


  return await response.json();
}


// =========================================================
// GET LATEST SCALE
// =========================================================

export async function getLatestMeasurement(
  floorPlanId: number
): Promise<FloorPlanMeasurement | null> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans/${floorPlanId}/measurements/latest`
    );


  if (response.status === 404) {
    return null;
  }


  if (!response.ok) {

    const text =
      await response.text();


    throw new Error(
      `Could not load scale: ${text}`
    );
  }


  return await response.json();
}


// =========================================================
// IMAGE
// =========================================================

export function getImageUrl(
  imagePath: string
): string {

  return `${API_URL}${imagePath}`;
}

// =========================================================
// GET ALL FLOOR PLANS
// =========================================================

export async function getAllFloorPlans() {

  const response =
    await fetch(
      `${API_URL}/api/floorplans`
    );


  if (!response.ok) {

    const text =
      await response.text();


    throw new Error(
      `Could not load floor plans: ${text}`
    );
  }


  return await response.json();
}


// =========================================================
// DELETE FLOOR PLAN
// =========================================================

export async function deleteFloorPlan(
  floorPlanId: number
): Promise<void> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans/${floorPlanId}`,
      {
        method: "DELETE",
      }
    );


  if (!response.ok) {

    const text =
      await response.text();


    throw new Error(
      `Could not delete floor plan ` +
      `(${response.status}): ${text}`
    );
  }
}