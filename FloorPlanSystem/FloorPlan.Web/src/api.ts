import type {
  DetectionUploadResponse,
  FloorPlan,
  SavedFloorPlanSummary,
} from "./types";


const API_URL =
  import.meta.env.VITE_API_URL;


if (!API_URL) {

  throw new Error(
    "VITE_API_URL is not configured."
  );

}


// =========================================================
// UPLOAD FLOOR PLAN
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
        method:
          "POST",

        body:
          formData,
      }
    );


  if (
    !response.ok
  ) {

    const errorText =
      await response.text();


    throw new Error(
      `Detection failed ` +
      `(${response.status} ${response.statusText}): ` +
      `${errorText || "No error response from server."}`
    );

  }


  return await response.json();
}


// =========================================================
// GET ALL FLOOR PLANS
// =========================================================

export async function getAllFloorPlans():
  Promise<SavedFloorPlanSummary[]> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans`
    );


  if (
    !response.ok
  ) {

    const errorText =
      await response.text();


    throw new Error(
      `Could not load saved floor plans ` +
      `(${response.status}): ` +
      `${errorText || "No error response from server."}`
    );

  }


  return await response.json();
}


// =========================================================
// GET ONE FLOOR PLAN
// =========================================================

export async function getFloorPlan(
  floorPlanId: number
): Promise<FloorPlan> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans/${floorPlanId}`
    );


  if (
    !response.ok
  ) {

    const errorText =
      await response.text();


    throw new Error(
      `Could not load floor plan ` +
      `(${response.status} ${response.statusText}): ` +
      `${errorText || "No error response from server."}`
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
        method:
          "DELETE",
      }
    );


  if (
    !response.ok
  ) {

    const errorText =
      await response.text();


    throw new Error(
      `Could not delete floor plan ` +
      `(${response.status} ${response.statusText}): ` +
      `${errorText || "No error response from server."}`
    );

  }

}


// =========================================================
// SAVED REVISION RESPONSE
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


// =========================================================
// SAVE CORRECTED REVISION
// =========================================================

export async function saveCorrectedRevision(
  floorPlan: FloorPlan
): Promise<SavedRevisionResponse> {

  const response =
    await fetch(
      `${API_URL}/api/floorplans/${floorPlan.floorPlanId}/revisions`,
      {
        method:
          "POST",

        headers: {
          "Content-Type":
            "application/json",
        },

        body:
          JSON.stringify(
            {
              basedOnRevisionId:
                floorPlan
                  .revision
                  .revisionId,

              validation:
                floorPlan
                  .revision
                  .validation,

              rooms:
                floorPlan
                  .revision
                  .rooms,

              doors:
                floorPlan
                  .revision
                  .doors,

              windows:
                floorPlan
                  .revision
                  .windows,

              openings:
                floorPlan
                  .revision
                  .openings,
            }
          ),
      }
    );


  if (
    !response.ok
  ) {

    const errorText =
      await response.text();


    throw new Error(
      `Could not save revision ` +
      `(${response.status} ${response.statusText}): ` +
      `${errorText || "No error response from server."}`
    );

  }


  return await response.json();
}


// =========================================================
// IMAGE URL
// =========================================================

export function getImageUrl(
  imagePath: string
): string {

  return `${API_URL}${imagePath}`;

}