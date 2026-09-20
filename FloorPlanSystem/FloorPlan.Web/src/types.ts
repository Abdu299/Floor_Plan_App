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

export type BoundaryReviewStatus =
  | "unreviewed"
  | "edited"
  | "confirmed"
  | "needs-recalculation"
  | string;

export interface BoundaryAutomaticAssessment {
  valid: boolean;
  requiresReview: boolean;
  method: string;
  candidateSource: string;
  message: string;
  roomAreaCoverage: number;
  roomCentroidCoverage: number;
  wallSupport: number;
  selectedStructuralGapPixels: number;
  estimatedWallThicknessPixels: number;
}

export interface BuildingBoundary {
  polygon: PixelPoint[];

  source:
    | "ai"
    | "user"
    | string;

  reviewStatus:
    BoundaryReviewStatus;

  isUserEdited: boolean;

  automaticAssessment:
    BoundaryAutomaticAssessment;
}

export interface Room {
  id: number;
  name: string;
  confidence: number;
  polygon: PixelPoint[];
  centroid: PixelPoint;
  areaPixels: number;
  areaSquareMetres:
    number | null;
  isUserAdded?: boolean;
}

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
    ConnectedRoom | null;

  isUserAdded?: boolean;
}

export interface WindowDetection {
  id: number;

  polygon:
    PixelPoint[];

  bbox:
    BoundingBox | null;

  isUserAdded?: boolean;
}

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

export interface Validation {
  valid: boolean;
  hasBathroom: boolean;
  hasKitchen: boolean;
}

export interface DetectionSummary {
  rooms: number;
  doors: number;
  windows: number;
  openings: number;
}

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

  buildingBoundary:
    BuildingBoundary;
}

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

export interface DetectionUploadResponse {
  floorPlanId: number;
  revisionId: number;
  imagePath: string;
}

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