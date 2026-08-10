export interface PixelPoint {
  x: number;
  y: number;
}


export interface BoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}


export interface ConnectedRoom {
  id: number;
  name: string;
}


// =========================================================
// ROOM
// =========================================================

export interface Room {
  id: number;

  name: string;

  confidence: number;

  polygon: PixelPoint[];

  centroid: PixelPoint;

  areaPixels: number;


  // Manually entered real area.
  areaSquareMetres:
    number | null;


  isUserAdded?: boolean;
}


// =========================================================
// DOOR
// =========================================================

export interface Door {
  id: number;

  confidence: number;

  polygon:
    PixelPoint[];

  bbox:
    BoundingBox | null;

  room1:
    ConnectedRoom;

  room2:
    ConnectedRoom;

  isUserAdded?: boolean;
}


// =========================================================
// WINDOW
// =========================================================

export interface WindowDetection {
  id: number;

  polygon:
    PixelPoint[];

  bbox:
    BoundingBox | null;

  isUserAdded?: boolean;
}


// =========================================================
// OPENING
// =========================================================

export interface Opening {
  id: number;

  polygon:
    PixelPoint[];

  bbox:
    BoundingBox | null;

  room1:
    ConnectedRoom;

  room2:
    ConnectedRoom;

  isUserAdded?: boolean;
}


// =========================================================
// VALIDATION
// =========================================================

export interface Validation {
  valid: boolean;

  hasBathroom: boolean;

  hasKitchen: boolean;
}


// =========================================================
// SUMMARY
// =========================================================

export interface DetectionSummary {
  rooms: number;

  doors: number;

  windows: number;

  openings: number;
}


// =========================================================
// REVISION
// =========================================================

export interface FloorPlanRevision {
  revisionId: number;

  revisionNumber: number;

  source: string;

  status: string;

  basedOnRevisionId:
    number | null;

  createdAtUtc: string;

  validation:
    Validation;

  summary:
    DetectionSummary;

  rooms:
    Room[];

  doors:
    Door[];

  windows:
    WindowDetection[];

  openings:
    Opening[];
}


// =========================================================
// COMPLETE FLOOR PLAN
// =========================================================

export interface FloorPlan {
  floorPlanId: number;

  originalFileName: string;

  imagePath: string;

  widthPixels: number;

  heightPixels: number;

  createdAtUtc: string;

  revision:
    FloorPlanRevision;
}


// =========================================================
// UPLOAD RESPONSE
// =========================================================

export interface DetectionUploadResponse {
  floorPlanId: number;

  revisionId: number;

  imagePath: string;
}


// =========================================================
// SAVED FLOOR PLAN LIST ITEM
// =========================================================

export interface SavedFloorPlanSummary {
  floorPlanId: number;

  originalFileName: string;

  imagePath: string;

  widthPixels: number;

  heightPixels: number;

  createdAtUtc: string;

  latestRevisionNumber: number;

  latestRevisionSource: string;

  latestRevisionStatus: string;

  roomCount: number;

  doorCount: number;

  windowCount: number;

  openingCount: number;
}

// =========================================================
// FLOOR PLAN MEASUREMENT
// =========================================================

export interface FloorPlanMeasurement {
  id: number;
  floorPlanId: number;

  startX: number;
  startY: number;

  endX: number;
  endY: number;

  actualDistance: number;
  unit: string;

  metresPerPixel: number | null;
}