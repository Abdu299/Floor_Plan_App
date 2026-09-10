import {
  useEffect,
  useState,
  type ChangeEvent,
} from "react";

import {
  Link,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import "./App.css";

import {
  getFloorPlan,
  saveCorrectedRevision,
  uploadFloorPlan,
} from "./api";

import type {
  BoundaryKind,
  BoundingBox,
  FloorPlan,
  PixelPoint,
  Room,
} from "./types";

import FloorPlanCanvas, {
  type ElementType,
} from "./components/FloorPlanCanvas";

import SavedFloorPlansPage
  from "./pages/SavedFloorPlansPage";


// =========================================================
// BATHROOM NAMES
// =========================================================

const BATHROOM_NAMES =
  new Set<string>([
    "bath",
    "bathroom",
    "full bathroom",
    "half bathroom",
    "ba",
    "bth",
    "main bathroom",
    "family bathroom",
    "common bathroom",
    "shared bathroom",
    "private bathroom",
    "master bathroom",
    "primary bathroom",
    "toilet",
    "wc",
    "water closet",
    "lavatory",
    "half bath",
    "guest toilet",
    "restroom",
    "bathroom/laundry",
    "bath/laundry",
    "bath/wc",
    "toilet/shower",
    "wc/shower",
    "shower",
    "shower room",
    "p.bath",
    "g.bath",
    "toil",
  ]);


// =========================================================
// KITCHEN NAMES
// =========================================================

const KITCHEN_NAMES =
  new Set<string>([
    "kitchen",
    "kitch",
    "kit",
    "kitchenette",
    "kitchen area",
    "kitchen zone",
    "cooking area",
    "cooking zone",
    "open kitchen",
    "open-plan kitchen",
    "open plan kitchen",
    "open kitchen area",
    "open-plan kitchen/living room",
    "open plan kitchen/living room",
    "kitchen/living room",
    "kitchen living room",
    "living room/kitchen",
    "living kitchen",
    "kitchen/dining room",
    "kitchen dining room",
    "dining room/kitchen",
    "kitchen/dining",
    "kitchen diner",
    "eat-in kitchen",
    "kitchen/family room",
    "kitchen/lounge",
    "lounge/kitchen",
    "studio kitchen",
    "compact kitchen",
    "small kitchen",
    "galley kitchen",
    "main kitchen",
    "shared kitchen",
    "communal kitchen",
    "service kitchen",
    "prep kitchen",
    "preparation kitchen",
    "secondary kitchen",
    "back kitchen",
    "butler's kitchen",
    "scullery",
    "pantry kitchen",
    "summer kitchen",
    "chef's kitchen",
    "commercial kitchen",
    "staff kitchen",
    "break room kitchen",
    "tea kitchen",
    "tea point",
    "refreshment area",
    "k",
    "kit.",
    "kitch.",
    "kt",
    "kitchenette/living room",
    "living room/kitchenette",
    "kitchenette/dining",
    "kitchenette area",
  ]);


// =========================================================
// SAVE VALIDATION
// =========================================================

interface SaveValidation {
  hasRooms:
    boolean;

  hasDoors:
    boolean;

  hasOpenings:
    boolean;

  hasConnection:
    boolean;

  hasBathroom:
    boolean;

  hasKitchen:
    boolean;

  floorPlanValid:
    boolean;

  missingAreaRooms:
    Room[];

  allRoomsHaveArea:
    boolean;

  canSave:
    boolean;

  issues:
    string[];
}


// =========================================================
// ROOM TYPE KEYWORDS
// =========================================================

const BATHROOM_KEYWORDS = [
  "bathroom",
  "bath",
  "toilet",
  "wc",
  "water closet",
  "lavatory",
  "restroom",
  "shower",
];


const KITCHEN_KEYWORDS = [
  "kitchen",
  "kitchenette",
  "cooking area",
  "cooking zone",
  "cooking",
];


// =========================================================
// NORMALIZE ROOM NAME
// =========================================================

function normalizeRoomName(
  value: string
): string {

  return value
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");

}


// =========================================================
// NORMALIZE FOR KEYWORD SEARCH
// =========================================================

function normalizeForKeywordSearch(
  value: string
): string {

  return normalizeRoomName(
    value
  )
    .replace(
      /[^a-z0-9]+/g,
      " "
    )
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");

}


// =========================================================
// KEYWORD MATCH
// =========================================================

function containsRoomKeyword(
  roomName: string,
  keyword: string
): boolean {

  const normalizedRoomName =
    normalizeForKeywordSearch(
      roomName
    );


  const normalizedKeyword =
    normalizeForKeywordSearch(
      keyword
    );


  if (
    !normalizedRoomName
    ||
    !normalizedKeyword
  ) {
    return false;
  }


  return (
    ` ${normalizedRoomName} `
      .includes(
        ` ${normalizedKeyword} `
      )
  );

}


// =========================================================
// ROOM TYPE CHECKS
// =========================================================

function isBathroomName(
  roomName: string
): boolean {

  const normalized =
    normalizeRoomName(
      roomName
    );


  return (
    BATHROOM_NAMES.has(
      normalized
    )
    ||
    BATHROOM_KEYWORDS.some(
      keyword =>
        containsRoomKeyword(
          roomName,
          keyword
        )
    )
  );

}


function isKitchenName(
  roomName: string
): boolean {

  const normalized =
    normalizeRoomName(
      roomName
    );


  return (
    KITCHEN_NAMES.has(
      normalized
    )
    ||
    KITCHEN_KEYWORDS.some(
      keyword =>
        containsRoomKeyword(
          roomName,
          keyword
        )
    )
  );

}


// =========================================================
// VALIDATE CURRENT FLOOR PLAN
// =========================================================

function validateForSave(
  floorPlan: FloorPlan
): SaveValidation {

  const rooms =
    floorPlan.revision.rooms;


  const doors =
    floorPlan.revision.doors;


  const openings =
    floorPlan.revision.openings;


  // =======================================================
  // BASIC DATA
  // =======================================================

  const hasRooms =
    rooms.length > 0;


  const hasDoors =
    doors.length > 0;


  const hasOpenings =
    openings.length > 0;


  // =======================================================
  // DOOR OR OPENING
  // =======================================================

  const hasConnection =
    hasDoors
    ||
    hasOpenings;


  // =======================================================
  // ROOM TYPE VALIDATION
  // =======================================================

  const hasBathroom =
    rooms.some(
      room =>
        isBathroomName(
          room.name
        )
    );


  const hasKitchen =
    rooms.some(
      room =>
        isKitchenName(
          room.name
        )
    );


  // =======================================================
  // AREA VALIDATION
  // =======================================================

  const missingAreaRooms =
    rooms.filter(
      room =>
        room.areaSquareMetres == null
        ||
        !Number.isFinite(
          room.areaSquareMetres
        )
        ||
        room.areaSquareMetres <= 0
    );


  const allRoomsHaveArea =
    hasRooms
    &&
    missingAreaRooms.length === 0;


  // =======================================================
  // FLOOR PLAN VALIDITY
  //
  // REQUIREMENTS:
  //
  // Rooms
  // Bathroom
  // Kitchen
  // Door OR Opening
  // =======================================================

  const floorPlanValid =
    hasRooms
    &&
    hasConnection
    &&
    hasBathroom
    &&
    hasKitchen;


  // =======================================================
  // ISSUES
  // =======================================================

  const issues:
    string[] = [];


  if (!hasRooms) {

    issues.push(
      "No rooms were found."
    );

  }


  if (!hasConnection) {

    issues.push(
      "The floor plan needs at least one door or one opening."
    );

  }


  if (!hasBathroom) {

    issues.push(
      "No bathroom was found."
    );

  }


  if (!hasKitchen) {

    issues.push(
      "No kitchen or cooking area was found."
    );

  }


  for (
    const room
    of missingAreaRooms
  ) {

    issues.push(
      `Room ${room.id} – ${room.name} is missing a valid area.`
    );

  }


  // =======================================================
  // RESULT
  // =======================================================

  return {
    hasRooms,

    hasDoors,

    hasOpenings,

    hasConnection,

    hasBathroom,

    hasKitchen,

    floorPlanValid,

    missingAreaRooms,

    allRoomsHaveArea,

    canSave:
      floorPlanValid
      &&
      allRoomsHaveArea,

    issues,
  };

}


// =========================================================
// ANALYZE PAGE
// =========================================================

function AnalyzePage() {

  const navigate =
    useNavigate();


  const {
    floorPlanId,
  } =
    useParams();


  // =========================================================
  // STATE
  // =========================================================

  const [
    selectedFile,
    setSelectedFile,
  ] =
    useState<File | null>(
      null
    );


  const [
    floorPlan,
    setFloorPlan,
  ] =
    useState<FloorPlan | null>(
      null
    );


  const [
    selectedType,
    setSelectedType,
  ] =
    useState<ElementType | null>(
      null
    );


  const [
    selectedId,
    setSelectedId,
  ] =
    useState<number | null>(
      null
    );


  const [
    addMode,
    setAddMode,
  ] =
    useState<ElementType | null>(
      null
    );


  const [
    boundaryEditMode,
    setBoundaryEditMode,
  ] =
    useState<BoundaryKind | null>(
      null
    );


  const [
    uploading,
    setUploading,
  ] =
    useState(false);


  const [
    loadingFloorPlan,
    setLoadingFloorPlan,
  ] =
    useState(false);


  const [
    saving,
    setSaving,
  ] =
    useState(false);


  const [
    error,
    setError,
  ] =
    useState<string | null>(
      null
    );


  const [
    saveMessage,
    setSaveMessage,
  ] =
    useState<string | null>(
      null
    );


  // =========================================================
  // LIVE VALIDATION
  // =========================================================

  const saveValidation =
    floorPlan
      ? validateForSave(
          floorPlan
        )
      : null;


  // =========================================================
  // LOAD EXISTING FLOOR PLAN
  // =========================================================

  useEffect(
    () => {

      let cancelled =
        false;


      async function load() {

        if (!floorPlanId) {

          setFloorPlan(
            null
          );


          setSelectedType(
            null
          );


          setSelectedId(
            null
          );


          setAddMode(
            null
          );


          setBoundaryEditMode(
            null
          );


          return;
        }


        const id =
          Number(
            floorPlanId
          );


        if (
          !Number.isInteger(
            id
          )
          ||
          id <= 0
        ) {

          setError(
            "Invalid floor plan ID."
          );


          return;
        }


        try {

          setLoadingFloorPlan(
            true
          );


          setError(
            null
          );


          setSaveMessage(
            null
          );


          const result =
            await getFloorPlan(
              id
            );


          if (cancelled) {
            return;
          }


          setFloorPlan(
            result
          );


          setSelectedType(
            null
          );


          setSelectedId(
            null
          );


          setAddMode(
            null
          );


          setBoundaryEditMode(
            null
          );

        }
        catch (err) {

          if (cancelled) {
            return;
          }


          console.error(
            err
          );


          setError(
            err instanceof Error
              ? err.message
              : "Could not load floor plan."
          );

        }
        finally {

          if (!cancelled) {

            setLoadingFloorPlan(
              false
            );

          }

        }

      }


      void load();


      return () => {

        cancelled =
          true;

      };

    },
    [
      floorPlanId,
    ]
  );


  // =========================================================
  // SELECT ELEMENT
  // =========================================================

  function selectElement(
    type:
      ElementType | null,

    id:
      number | null
  ) {

    setSelectedType(
      type
    );


    setSelectedId(
      id
    );

  }


  // =========================================================
  // START ADD MODE
  // =========================================================

  function startAddMode(
    type:
      ElementType
  ) {

    if (!floorPlan) {
      return;
    }


    if (
      (
        type === "door"
        ||
        type === "opening"
      )
      &&
      floorPlan
        .revision
        .rooms
        .length < 2
    ) {

      setError(
        "A door or opening needs at least two rooms."
      );


      return;
    }


    setError(
      null
    );


    setSaveMessage(
      null
    );


    setBoundaryEditMode(
      null
    );


    selectElement(
      null,
      null
    );


    setAddMode(
      type
    );

  }


  // =========================================================
  // FILE
  // =========================================================

  function handleFileChange(
    event:
      ChangeEvent<HTMLInputElement>
  ) {

    const file =
      event
        .target
        .files?.[0];


    if (!file) {
      return;
    }


    setSelectedFile(
      file
    );


    setError(
      null
    );


    setSaveMessage(
      null
    );

  }


  // =========================================================
  // UPLOAD
  // =========================================================

  async function handleUpload() {

    if (!selectedFile) {

      setError(
        "Please choose a floor plan image."
      );


      return;
    }


    try {

      setUploading(
        true
      );


      setError(
        null
      );


      setSaveMessage(
        null
      );


      const result =
        await uploadFloorPlan(
          selectedFile
        );


      navigate(
        `/floorplans/${result.floorPlanId}`
      );

    }
    catch (err) {

      console.error(
        err
      );


      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong."
      );

    }
    finally {

      setUploading(
        false
      );

    }

  }


  // =========================================================
  // SAVE CORRECTIONS
  // =========================================================

  async function handleSaveCorrections() {

    if (!floorPlan) {
      return;
    }


    const validation =
      validateForSave(
        floorPlan
      );


    if (!validation.canSave) {

      setError(
        "Cannot save floor plan. "
        +
        validation.issues.join(
          " "
        )
      );


      return;
    }


    try {

      setSaving(
        true
      );


      setError(
        null
      );


      setSaveMessage(
        null
      );


      const previousRevisionId =
        floorPlan
          .revision
          .revisionId;


      // =====================================================
      // SEND RECALCULATED VALIDATION
      // =====================================================

      const floorPlanToSave:
        FloorPlan =
        {
          ...floorPlan,

          revision: {
            ...floorPlan.revision,

            validation: {
              valid:
                validation.floorPlanValid,

              hasBathroom:
                validation.hasBathroom,

              hasKitchen:
                validation.hasKitchen,
            },
          },
        };


      const saved =
        await saveCorrectedRevision(
          floorPlanToSave
        );


      setFloorPlan(
        current => {

          if (!current) {
            return current;
          }


          return {
            ...current,

            revision: {
              ...current.revision,

              revisionId:
                saved.revisionId,

              revisionNumber:
                saved.revisionNumber,

              source:
                saved.source,

              status:
                saved.status,

              basedOnRevisionId:
                previousRevisionId,

              createdAtUtc:
                saved.createdAtUtc,

              validation: {
                valid:
                  validation.floorPlanValid,

                hasBathroom:
                  validation.hasBathroom,

                hasKitchen:
                  validation.hasKitchen,
              },
            },
          };

        }
      );


      setAddMode(
        null
      );


      setBoundaryEditMode(
        null
      );


      selectElement(
        null,
        null
      );


      setSaveMessage(
        `Corrections saved as Revision ${saved.revisionNumber}.`
      );

    }
    catch (err) {

      console.error(
        err
      );


      setError(
        err instanceof Error
          ? err.message
          : "Could not save corrections."
      );

    }
    finally {

      setSaving(
        false
      );

    }

  }


  // =========================================================
  // BUILDING BOUNDARY EDITING
  // =========================================================
  //
  // IMPORTANT:
  // automaticAssessment.valid is only the detector's opinion.
  // It NEVER disables editing. A user may correct a boundary
  // whether the automatic result was valid=true or valid=false.
  // =========================================================

  function updateBoundaryPolygon(
    kind:
      BoundaryKind,

    update: (
      polygon: PixelPoint[]
    ) => PixelPoint[]
  ) {

    setSaveMessage(
      null
    );


    setError(
      null
    );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        const boundary =
          current
            .revision
            .buildingBoundary;


        const currentPolygon =
          kind === "outer"
            ? boundary.outerPolygon
            : boundary.usablePolygon;


        const nextPolygon =
          update(
            currentPolygon
          );


        return {
          ...current,

          revision: {
            ...current.revision,

            buildingBoundary: {
              ...boundary,

              outerPolygon:
                kind === "outer"
                  ? nextPolygon
                  : boundary.outerPolygon,

              usablePolygon:
                kind === "usable"
                  ? nextPolygon
                  : boundary.usablePolygon,

              // Current geometry is now user-authored.
              // The original automaticAssessment is preserved.
              source:
                "user",

              reviewStatus:
                "edited",

              isUserEdited:
                true,
            },
          },
        };

      }
    );

  }


  function moveBoundaryPoint(
    kind:
      BoundaryKind,

    pointIndex:
      number,

    point:
      PixelPoint
  ) {

    updateBoundaryPolygon(
      kind,

      polygon =>
        polygon.map(
          (
            currentPoint,
            index
          ) =>
            index === pointIndex
              ? point
              : currentPoint
        )
    );

  }


  function insertBoundaryPoint(
    kind:
      BoundaryKind,

    insertAfterIndex:
      number,

    point:
      PixelPoint
  ) {

    updateBoundaryPolygon(
      kind,

      polygon => {

        const copy =
          [...polygon];


        copy.splice(
          insertAfterIndex + 1,
          0,
          point
        );


        return copy;

      }
    );

  }


  function deleteBoundaryPoint(
    kind:
      BoundaryKind,

    pointIndex:
      number
  ) {

    updateBoundaryPolygon(
      kind,

      polygon => {

        if (
          polygon.length <= 3
        ) {
          return polygon;
        }


        return polygon.filter(
          (
            _,
            index
          ) =>
            index !== pointIndex
        );

      }
    );

  }


  function toggleBoundaryEdit(
    kind:
      BoundaryKind
  ) {

    if (!floorPlan) {
      return;
    }


    const polygon =
      kind === "outer"
        ? floorPlan
            .revision
            .buildingBoundary
            .outerPolygon

        : floorPlan
            .revision
            .buildingBoundary
            .usablePolygon;


    if (
      polygon.length < 3
    ) {

      setError(
        `The ${kind} boundary does not contain a polygon to edit yet.`
      );


      return;
    }


    setError(
      null
    );


    setSaveMessage(
      null
    );


    setAddMode(
      null
    );


    selectElement(
      null,
      null
    );


    setBoundaryEditMode(
      current =>
        current === kind
          ? null
          : kind
    );

  }


  function confirmBoundary() {

    setSaveMessage(
      null
    );


    setError(
      null
    );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        return {
          ...current,

          revision: {
            ...current.revision,

            buildingBoundary: {
              ...current
                .revision
                .buildingBoundary,

              reviewStatus:
                "confirmed",
            },
          },
        };

      }
    );

  }


  // =========================================================
  // BOUNDING BOX
  // =========================================================

  function createBoundingBox(
    polygon:
      PixelPoint[]
  ): BoundingBox {

    const xs =
      polygon.map(
        point =>
          point.x
      );


    const ys =
      polygon.map(
        point =>
          point.y
      );


    return {
      x1:
        Math.min(
          ...xs
        ),

      y1:
        Math.min(
          ...ys
        ),

      x2:
        Math.max(
          ...xs
        ),

      y2:
        Math.max(
          ...ys
        ),
    };

  }


  // =========================================================
  // NEXT ID
  // =========================================================

  function nextId(
    ids:
      number[]
  ): number {

    if (
      ids.length === 0
    ) {
      return 1;
    }


    return (
      Math.max(
        ...ids
      )
      +
      1
    );

  }


  // =========================================================
  // CREATE ELEMENT
  // =========================================================

  function createElement(
    type:
      ElementType,

    polygon:
      PixelPoint[]
  ) {

    if (!floorPlan) {
      return;
    }


    setSaveMessage(
      null
    );


    const bbox =
      createBoundingBox(
        polygon
      );


    // =====================================================
    // ROOM
    // =====================================================

    if (
      type === "room"
    ) {

      const id =
        nextId(
          floorPlan
            .revision
            .rooms
            .map(
              room =>
                room.id
            )
        );


      const centroid = {
        x:
          (
            bbox.x1 +
            bbox.x2
          ) / 2,

        y:
          (
            bbox.y1 +
            bbox.y2
          ) / 2,
      };


      const areaPixels =
        (
          bbox.x2 -
          bbox.x1
        )
        *
        (
          bbox.y2 -
          bbox.y1
        );


      setFloorPlan(
        current => {

          if (!current) {
            return current;
          }


          const rooms = [
            ...current
              .revision
              .rooms,

            {
              id,

              name:
                `NEW ROOM ${id}`,

              confidence:
                0,

              polygon,

              centroid,

              areaPixels,

              areaSquareMetres:
                null,

              isUserAdded:
                true,
            },
          ];


          return {
            ...current,

            revision: {
              ...current.revision,

              rooms,

              summary: {
                ...current
                  .revision
                  .summary,

                rooms:
                  rooms.length,
              },
            },
          };

        }
      );


      setAddMode(
        null
      );


      selectElement(
        "room",
        id
      );


      return;
    }


    // =====================================================
    // DOOR
    // =====================================================

    if (
      type === "door"
    ) {

      const rooms =
        floorPlan
          .revision
          .rooms;


      // A door only needs one connected room.
      // room2 may be null, which represents Outside.
      if (
        rooms.length < 1
      ) {
        return;
      }


      const id =
        nextId(
          floorPlan
            .revision
            .doors
            .map(
              door =>
                door.id
            )
        );


      setFloorPlan(
        current => {

          if (!current) {
            return current;
          }


          const doors = [
            ...current
              .revision
              .doors,

            {
              id,

              confidence:
                0,

              polygon,

              bbox,

              room1: {
                id:
                  rooms[0].id,

                name:
                  rooms[0].name,
              },

              // Preserve the old default when two or more rooms exist.
              // If there is only one room, the other side is Outside.
              room2:
                rooms.length > 1
                  ? {
                      id:
                        rooms[1].id,

                      name:
                        rooms[1].name,
                    }
                  : null,

              isUserAdded:
                true,
            },
          ];


          return {
            ...current,

            revision: {
              ...current.revision,

              doors,

              summary: {
                ...current
                  .revision
                  .summary,

                doors:
                  doors.length,
              },
            },
          };

        }
      );


      setAddMode(
        null
      );


      selectElement(
        "door",
        id
      );


      return;
    }


    // =====================================================
    // WINDOW
    // =====================================================

    if (
      type === "window"
    ) {

      const id =
        nextId(
          floorPlan
            .revision
            .windows
            .map(
              window =>
                window.id
            )
        );


      setFloorPlan(
        current => {

          if (!current) {
            return current;
          }


          const windows = [
            ...current
              .revision
              .windows,

            {
              id,

              polygon,

              bbox,

              isUserAdded:
                true,
            },
          ];


          return {
            ...current,

            revision: {
              ...current.revision,

              windows,

              summary: {
                ...current
                  .revision
                  .summary,

                windows:
                  windows.length,
              },
            },
          };

        }
      );


      setAddMode(
        null
      );


      selectElement(
        "window",
        id
      );


      return;
    }


    // =====================================================
    // OPENING
    // =====================================================

    const rooms =
      floorPlan
        .revision
        .rooms;


    if (
      rooms.length < 2
    ) {
      return;
    }


    const id =
      nextId(
        floorPlan
          .revision
          .openings
          .map(
            opening =>
              opening.id
          )
      );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        const openings = [
          ...current
            .revision
            .openings,

          {
            id,

            polygon,

            bbox,

            room1: {
              id:
                rooms[0].id,

              name:
                rooms[0].name,
            },

            room2: {
              id:
                rooms[1].id,

              name:
                rooms[1].name,
            },

            isUserAdded:
              true,
          },
        ];


        return {
          ...current,

          revision: {
            ...current.revision,

            openings,

            summary: {
              ...current
                .revision
                .summary,

              openings:
                openings.length,
            },
          },
        };

      }
    );


    setAddMode(
      null
    );


    selectElement(
      "opening",
      id
    );

  }


  // =========================================================
  // MOVE ELEMENT
  // =========================================================

  function moveElement(
    type:
      ElementType,

    id:
      number,

    deltaX:
      number,

    deltaY:
      number
  ) {

    setSaveMessage(
      null
    );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        // ROOM

        if (
          type === "room"
        ) {

          return {
            ...current,

            revision: {
              ...current.revision,

              rooms:
                current
                  .revision
                  .rooms
                  .map(
                    room => {

                      if (
                        room.id !== id
                      ) {
                        return room;
                      }


                      return {
                        ...room,

                        polygon:
                          room
                            .polygon
                            .map(
                              point => ({
                                x:
                                  point.x +
                                  deltaX,

                                y:
                                  point.y +
                                  deltaY,
                              })
                            ),

                        centroid: {
                          x:
                            room.centroid.x +
                            deltaX,

                          y:
                            room.centroid.y +
                            deltaY,
                        },
                      };

                    }
                  ),
            },
          };

        }


        // DOOR

        if (
          type === "door"
        ) {

          return {
            ...current,

            revision: {
              ...current.revision,

              doors:
                current
                  .revision
                  .doors
                  .map(
                    door => {

                      if (
                        door.id !== id
                      ) {
                        return door;
                      }


                      return {
                        ...door,

                        polygon:
                          door
                            .polygon
                            .map(
                              point => ({
                                x:
                                  point.x +
                                  deltaX,

                                y:
                                  point.y +
                                  deltaY,
                              })
                            ),

                        bbox:
                          door.bbox
                            ? {
                                x1:
                                  door.bbox.x1 +
                                  deltaX,

                                y1:
                                  door.bbox.y1 +
                                  deltaY,

                                x2:
                                  door.bbox.x2 +
                                  deltaX,

                                y2:
                                  door.bbox.y2 +
                                  deltaY,
                              }
                            : null,
                      };

                    }
                  ),
            },
          };

        }


        // WINDOW

        if (
          type === "window"
        ) {

          return {
            ...current,

            revision: {
              ...current.revision,

              windows:
                current
                  .revision
                  .windows
                  .map(
                    window => {

                      if (
                        window.id !== id
                      ) {
                        return window;
                      }


                      return {
                        ...window,

                        polygon:
                          window
                            .polygon
                            .map(
                              point => ({
                                x:
                                  point.x +
                                  deltaX,

                                y:
                                  point.y +
                                  deltaY,
                              })
                            ),

                        bbox:
                          window.bbox
                            ? {
                                x1:
                                  window.bbox.x1 +
                                  deltaX,

                                y1:
                                  window.bbox.y1 +
                                  deltaY,

                                x2:
                                  window.bbox.x2 +
                                  deltaX,

                                y2:
                                  window.bbox.y2 +
                                  deltaY,
                              }
                            : null,
                      };

                    }
                  ),
            },
          };

        }


        // OPENING

        return {
          ...current,

          revision: {
            ...current.revision,

            openings:
              current
                .revision
                .openings
                .map(
                  opening => {

                    if (
                      opening.id !== id
                    ) {
                      return opening;
                    }


                    return {
                      ...opening,

                      polygon:
                        opening
                          .polygon
                          .map(
                            point => ({
                              x:
                                point.x +
                                deltaX,

                              y:
                                point.y +
                                deltaY,
                            })
                          ),

                      bbox:
                        opening.bbox
                          ? {
                              x1:
                                opening.bbox.x1 +
                                deltaX,

                              y1:
                                opening.bbox.y1 +
                                deltaY,

                              x2:
                                opening.bbox.x2 +
                                deltaX,

                              y2:
                                opening.bbox.y2 +
                                deltaY,
                            }
                          : null,
                    };

                  }
                ),
          },
        };

      }
    );

  }


  // =========================================================
  // RENAME ROOM
  // =========================================================

  function renameRoom(
    roomId:
      number,

    newName:
      string
  ) {

    setSaveMessage(
      null
    );


    setError(
      null
    );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        return {
          ...current,

          revision: {
            ...current.revision,

            rooms:
              current
                .revision
                .rooms
                .map(
                  room =>
                    room.id === roomId
                      ? {
                          ...room,

                          name:
                            newName,
                        }
                      : room
                ),

            doors:
              current
                .revision
                .doors
                .map(
                  door => ({
                    ...door,

                    room1:
                      door.room1.id === roomId
                        ? {
                            ...door.room1,

                            name:
                              newName,
                          }
                        : door.room1,

                    room2:
                      door.room2?.id === roomId
                        ? {
                            ...door.room2,

                            name:
                              newName,
                          }
                        : door.room2,
                  })
                ),

            openings:
              current
                .revision
                .openings
                .map(
                  opening => ({
                    ...opening,

                    room1:
                      opening.room1.id === roomId
                        ? {
                            ...opening.room1,

                            name:
                              newName,
                          }
                        : opening.room1,

                    room2:
                      opening.room2.id === roomId
                        ? {
                            ...opening.room2,

                            name:
                              newName,
                          }
                        : opening.room2,
                  })
                ),
          },
        };

      }
    );

  }


  // =========================================================
  // ROOM AREA
  // =========================================================

  function changeRoomArea(
    roomId:
      number,

    value:
      string
  ) {

    setSaveMessage(
      null
    );


    setError(
      null
    );


    let area:
      number | null;


    if (
      value.trim() === ""
    ) {

      area =
        null;

    }
    else {

      const parsed =
        Number(
          value
        );


      if (
        !Number.isFinite(
          parsed
        )
      ) {
        return;
      }


      if (
        parsed < 0
      ) {
        return;
      }


      area =
        parsed;

    }


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        return {
          ...current,

          revision: {
            ...current.revision,

            rooms:
              current
                .revision
                .rooms
                .map(
                  room =>
                    room.id === roomId
                      ? {
                          ...room,

                          areaSquareMetres:
                            area,
                        }
                      : room
                ),
          },
        };

      }
    );

  }


  // =========================================================
  // CHANGE DOOR ROOM
  // =========================================================

  function changeDoorRoom(
    doorId:
      number,

    side:
      "room1" |
      "room2",

    roomId:
      number | null
  ) {

    setSaveMessage(
      null
    );


    setError(
      null
    );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        // Only room2 may be Outside/null.
        if (
          side === "room2"
          &&
          roomId === null
        ) {
          return {
            ...current,

            revision: {
              ...current.revision,

              doors:
                current
                  .revision
                  .doors
                  .map(
                    door =>
                      door.id === doorId
                        ? {
                            ...door,
                            room2: null,
                          }
                        : door
                  ),
            },
          };
        }


        if (roomId === null) {
          return current;
        }


        const room =
          current
            .revision
            .rooms
            .find(
              item =>
                item.id ===
                roomId
            );


        if (!room) {
          return current;
        }


        return {
          ...current,

          revision: {
            ...current.revision,

            doors:
              current
                .revision
                .doors
                .map(
                  door =>
                    door.id === doorId
                      ? {
                          ...door,

                          [side]: {
                            id:
                              room.id,

                            name:
                              room.name,
                          },
                        }
                      : door
                ),
          },
        };

      }
    );

  }


  // =========================================================
  // CHANGE OPENING ROOM
  // =========================================================

  function changeOpeningRoom(
    openingId:
      number,

    side:
      "room1" |
      "room2",

    roomId:
      number
  ) {

    setSaveMessage(
      null
    );


    setError(
      null
    );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        const room =
          current
            .revision
            .rooms
            .find(
              item =>
                item.id ===
                roomId
            );


        if (!room) {
          return current;
        }


        return {
          ...current,

          revision: {
            ...current.revision,

            openings:
              current
                .revision
                .openings
                .map(
                  opening =>
                    opening.id ===
                    openingId
                      ? {
                          ...opening,

                          [side]: {
                            id:
                              room.id,

                            name:
                              room.name,
                          },
                        }
                      : opening
                ),
          },
        };

      }
    );

  }


  // =========================================================
  // DELETE
  // =========================================================

  function deleteElement(
    type:
      ElementType,

    id:
      number
  ) {

    setSaveMessage(
      null
    );


    setError(
      null
    );


    setFloorPlan(
      current => {

        if (!current) {
          return current;
        }


        // ROOM

        if (
          type === "room"
        ) {

          const rooms =
            current
              .revision
              .rooms
              .filter(
                room =>
                  room.id !== id
              );


          const doors =
            current
              .revision
              .doors
              .filter(
                door =>
                  door.room1.id !== id
                  &&
                  door.room2?.id !== id
              );


          const openings =
            current
              .revision
              .openings
              .filter(
                opening =>
                  opening.room1.id !== id
                  &&
                  opening.room2.id !== id
              );


          return {
            ...current,

            revision: {
              ...current.revision,

              rooms,

              doors,

              openings,

              summary: {
                ...current
                  .revision
                  .summary,

                rooms:
                  rooms.length,

                doors:
                  doors.length,

                openings:
                  openings.length,
              },
            },
          };

        }


        // DOOR

        if (
          type === "door"
        ) {

          const doors =
            current
              .revision
              .doors
              .filter(
                door =>
                  door.id !== id
              );


          return {
            ...current,

            revision: {
              ...current.revision,

              doors,

              summary: {
                ...current
                  .revision
                  .summary,

                doors:
                  doors.length,
              },
            },
          };

        }


        // WINDOW

        if (
          type === "window"
        ) {

          const windows =
            current
              .revision
              .windows
              .filter(
                window =>
                  window.id !== id
              );


          return {
            ...current,

            revision: {
              ...current.revision,

              windows,

              summary: {
                ...current
                  .revision
                  .summary,

                windows:
                  windows.length,
              },
            },
          };

        }


        // OPENING

        const openings =
          current
            .revision
            .openings
            .filter(
              opening =>
                opening.id !== id
            );


        return {
          ...current,

          revision: {
            ...current.revision,

            openings,

            summary: {
              ...current
                .revision
                .summary,

              openings:
                openings.length,
            },
          },
        };

      }
    );


    selectElement(
      null,
      null
    );

  }


  // =========================================================
  // SELECTED OBJECTS
  // =========================================================

  const selectedRoom =
    selectedType === "room"
      ? floorPlan
          ?.revision
          .rooms
          .find(
            room =>
              room.id === selectedId
          )
          ?? null
      : null;


  const selectedDoor =
    selectedType === "door"
      ? floorPlan
          ?.revision
          .doors
          .find(
            door =>
              door.id === selectedId
          )
          ?? null
      : null;


  const selectedWindow =
    selectedType === "window"
      ? floorPlan
          ?.revision
          .windows
          .find(
            window =>
              window.id === selectedId
          )
          ?? null
      : null;


  const selectedOpening =
    selectedType === "opening"
      ? floorPlan
          ?.revision
          .openings
          .find(
            opening =>
              opening.id === selectedId
          )
          ?? null
      : null;


  // =========================================================
  // UI
  // =========================================================

  return (

    <div className="app">

      <header className="header">

        <div>

          <h1>
            Floor Plan Analysis
          </h1>


          <p>
            Upload, analyze and correct
            floor-plan detections.
          </p>

        </div>

      </header>


      <main className="main">

        {/* =============================================== */}
        {/* UPLOAD */}
        {/* =============================================== */}

        {
          !floorPlanId && (

            <section className="upload-card">

              <h2>
                Upload floor plan
              </h2>


              <input
                type="file"

                accept=
                  ".png,.jpg,.jpeg,.webp"

                onChange={
                  handleFileChange
                }

                disabled={
                  uploading
                }
              />


              {
                selectedFile && (

                  <p className="selected-file">

                    Selected:{" "}

                    {
                      selectedFile.name
                    }

                  </p>

                )
              }


              <button
                onClick={
                  handleUpload
                }

                disabled={
                  !selectedFile
                  ||
                  uploading
                }
              >

                {
                  uploading
                    ? "Analyzing..."
                    : "Analyze floor plan"
                }

              </button>

            </section>

          )
        }


        {/* LOADING */}

        {
          loadingFloorPlan && (

            <div
              style={{
                padding:
                  "40px",

                textAlign:
                  "center",
              }}
            >

              Loading floor plan...

            </div>

          )
        }


        {/* ERROR */}

        {
          error && (

            <div className="error">

              {
                error
              }

            </div>

          )
        }


        {/* =============================================== */}
        {/* RESULT */}
        {/* =============================================== */}

        {
          floorPlan
          &&
          !loadingFloorPlan
          && (

            <section className="result">

              {/* HEADER */}

              <div className="result-header">

                <div>

                  <h2>

                    {
                      floorPlan
                        .originalFileName
                    }

                  </h2>


                  <p>

                    Floor Plan ID:{" "}

                    {
                      floorPlan
                        .floorPlanId
                    }

                  </p>

                </div>


                <div className="revision-info">

                  Revision{" "}

                  {
                    floorPlan
                      .revision
                      .revisionNumber
                  }

                  {" · "}

                  {
                    floorPlan
                      .revision
                      .source
                  }

                </div>

              </div>


              {/* SUMMARY */}

              <div className="summary">

                <div className="summary-item">

                  <strong>

                    {
                      floorPlan
                        .revision
                        .summary
                        .rooms
                    }

                  </strong>

                  <span>
                    Rooms
                  </span>

                </div>


                <div className="summary-item">

                  <strong>

                    {
                      floorPlan
                        .revision
                        .summary
                        .doors
                    }

                  </strong>

                  <span>
                    Doors
                  </span>

                </div>


                <div className="summary-item">

                  <strong>

                    {
                      floorPlan
                        .revision
                        .summary
                        .windows
                    }

                  </strong>

                  <span>
                    Windows
                  </span>

                </div>


                <div className="summary-item">

                  <strong>

                    {
                      floorPlan
                        .revision
                        .summary
                        .openings
                    }

                  </strong>

                  <span>
                    Openings
                  </span>

                </div>

              </div>


              {/* BUILDING BOUNDARY */}

              <div
                className={
                  floorPlan
                    .revision
                    .buildingBoundary
                    .automaticAssessment
                    .valid

                    ? "boundary-panel boundary-panel-valid"
                    : "boundary-panel boundary-panel-review"
                }
              >

                <div className="boundary-panel-header">

                  <div>

                    <h3>
                      Building boundary
                    </h3>


                    <p>
                      {
                        floorPlan
                          .revision
                          .buildingBoundary
                          .automaticAssessment
                          .valid

                          ? "Automatic boundary check passed."
                          : "Automatic boundary is uncertain and should be reviewed."
                      }

                      {" "}

                      You can edit it in either case.
                    </p>

                  </div>


                  <div className="boundary-status">

                    {
                      floorPlan
                        .revision
                        .buildingBoundary
                        .automaticAssessment
                        .valid
                        ? "AI: valid"
                        : "AI: review"
                    }

                  </div>

                </div>


                <div className="boundary-meta">

                  <span>
                    Current source:{" "}

                    <strong>
                      {
                        floorPlan
                          .revision
                          .buildingBoundary
                          .source
                      }
                    </strong>
                  </span>


                  <span>
                    Review:{" "}

                    <strong>
                      {
                        floorPlan
                          .revision
                          .buildingBoundary
                          .reviewStatus
                      }
                    </strong>
                  </span>


                  <span>
                    Method:{" "}

                    <strong>
                      {
                        floorPlan
                          .revision
                          .buildingBoundary
                          .automaticAssessment
                          .candidateSource
                      }
                    </strong>
                  </span>

                </div>


                {
                  floorPlan
                    .revision
                    .buildingBoundary
                    .automaticAssessment
                    .message
                  && (

                    <p className="boundary-message">

                      {
                        floorPlan
                          .revision
                          .buildingBoundary
                          .automaticAssessment
                          .message
                      }

                    </p>

                  )
                }


                <div className="boundary-actions">

                  <button
                    type="button"

                    className={
                      boundaryEditMode === "outer"
                        ? "boundary-button active"
                        : "boundary-button"
                    }

                    disabled={
                      floorPlan
                        .revision
                        .buildingBoundary
                        .outerPolygon
                        .length < 3
                    }

                    onClick={
                      () =>
                        toggleBoundaryEdit(
                          "outer"
                        )
                    }
                  >

                    {
                      boundaryEditMode === "outer"
                        ? "Stop editing outer"
                        : "Edit outer boundary"
                    }

                  </button>


                  <button
                    type="button"

                    className={
                      boundaryEditMode === "usable"
                        ? "boundary-button active"
                        : "boundary-button"
                    }

                    disabled={
                      floorPlan
                        .revision
                        .buildingBoundary
                        .usablePolygon
                        .length < 3
                    }

                    onClick={
                      () =>
                        toggleBoundaryEdit(
                          "usable"
                        )
                    }
                  >

                    {
                      boundaryEditMode === "usable"
                        ? "Stop editing usable"
                        : "Edit usable boundary"
                    }

                  </button>


                  <button
                    type="button"

                    className="boundary-confirm-button"

                    disabled={
                      floorPlan
                        .revision
                        .buildingBoundary
                        .outerPolygon
                        .length < 3
                      ||
                      floorPlan
                        .revision
                        .buildingBoundary
                        .usablePolygon
                        .length < 3
                    }

                    onClick={
                      confirmBoundary
                    }
                  >

                    Mark boundary reviewed

                  </button>

                </div>


                {
                  boundaryEditMode && (

                    <div className="boundary-edit-instruction">

                      Editing{" "}
                      <strong>
                        {
                          boundaryEditMode
                        }
                      </strong>
                      {" "}boundary: drag a point to move it.
                      Double-click a boundary line to add a point.
                      Double-click a point to remove it.

                    </div>

                  )
                }

              </div>


              {/* ADD TOOLBAR */}

              <div className="add-toolbar">

                <div className="add-toolbar-title">

                  Add object

                </div>


                <button
                  className={
                    addMode === "room"
                      ? "add-object-button active room-add"
                      : "add-object-button"
                  }

                  onClick={
                    () =>
                      startAddMode(
                        "room"
                      )
                  }
                >

                  + Room

                </button>


                <button
                  className={
                    addMode === "door"
                      ? "add-object-button active door-add"
                      : "add-object-button"
                  }

                  onClick={
                    () =>
                      startAddMode(
                        "door"
                      )
                  }
                >

                  + Door

                </button>


                <button
                  className={
                    addMode === "window"
                      ? "add-object-button active window-add"
                      : "add-object-button"
                  }

                  onClick={
                    () =>
                      startAddMode(
                        "window"
                      )
                  }
                >

                  + Window

                </button>


                <button
                  className={
                    addMode === "opening"
                      ? "add-object-button active opening-add"
                      : "add-object-button"
                  }

                  onClick={
                    () =>
                      startAddMode(
                        "opening"
                      )
                  }
                >

                  + Opening

                </button>


                {
                  addMode && (

                    <button
                      className="cancel-add-button"

                      onClick={
                        () =>
                          setAddMode(
                            null
                          )
                      }
                    >

                      Cancel

                    </button>

                  )
                }

              </div>


              {/* ========================================= */}
              {/* VALIDATION BOX */}
              {/* ========================================= */}

              {
                saveValidation && (

                  <div
                    style={{
                      marginTop:
                        "18px",

                      padding:
                        "16px 18px",

                      borderRadius:
                        "10px",

                      border:
                        saveValidation.canSave
                          ? "1px solid #86efac"
                          : "1px solid #fca5a5",

                      background:
                        saveValidation.canSave
                          ? "#f0fdf4"
                          : "#fef2f2",

                      color:
                        saveValidation.canSave
                          ? "#166534"
                          : "#991b1b",
                    }}
                  >

                    <div
                      style={{
                        fontWeight:
                          800,

                        marginBottom:
                          "10px",
                      }}
                    >

                      {
                        saveValidation.canSave
                          ? "✓ Floor plan is ready to save"
                          : "⚠ Cannot save floor plan"
                      }

                    </div>


                    <div
                      style={{
                        display:
                          "grid",

                        gap:
                          "5px",
                      }}
                    >

                      <div>

                        {
                          saveValidation.hasBathroom
                            ? "✓"
                            : "✕"
                        }

                        {" "}

                        Bathroom

                      </div>


                      <div>

                        {
                          saveValidation.hasKitchen
                            ? "✓"
                            : "✕"
                        }

                        {" "}

                        Kitchen

                      </div>


                      {/* ================================= */}
                      {/* DOOR OR OPENING */}
                      {/* ================================= */}

                      <div>

                        {
                          saveValidation.hasConnection
                            ? "✓"
                            : "✕"
                        }

                        {" "}

                        At least one door or opening

                        {
                          saveValidation.hasConnection && (

                            <span
                              style={{
                                marginLeft:
                                  "6px",

                                opacity:
                                  0.75,

                                fontSize:
                                  "12px",
                              }}
                            >

                              (
                              {
                                floorPlan
                                  .revision
                                  .doors
                                  .length
                              }{" "}
                              door
                              {
                                floorPlan
                                  .revision
                                  .doors
                                  .length === 1
                                  ? ""
                                  : "s"
                              }

                              ,{" "}

                              {
                                floorPlan
                                  .revision
                                  .openings
                                  .length
                              }{" "}
                              opening
                              {
                                floorPlan
                                  .revision
                                  .openings
                                  .length === 1
                                  ? ""
                                  : "s"
                              }
                              )

                            </span>

                          )
                        }

                      </div>


                      <div>

                        {
                          saveValidation.allRoomsHaveArea
                            ? "✓"
                            : "✕"
                        }

                        {" "}

                        All rooms have an area

                      </div>

                    </div>


                    {
                      !saveValidation.canSave
                      &&
                      saveValidation.issues.length > 0
                      && (

                        <div
                          style={{
                            marginTop:
                              "12px",

                            paddingTop:
                              "12px",

                            borderTop:
                              "1px solid rgba(153, 27, 27, 0.15)",
                          }}
                        >

                          <strong>
                            Fix before saving:
                          </strong>


                          <ul
                            style={{
                              marginBottom:
                                0,

                              paddingLeft:
                                "20px",
                            }}
                          >

                            {
                              saveValidation
                                .issues
                                .map(
                                  (
                                    issue,
                                    index
                                  ) => (

                                    <li
                                      key={
                                        `${issue}-${index}`
                                      }
                                    >

                                      {
                                        issue
                                      }

                                    </li>

                                  )
                                )
                            }

                          </ul>

                        </div>

                      )
                    }

                  </div>

                )
              }


              {/* SAVE */}

              <div className="save-revision-row">

                <button
                  className="save-revision-button"

                  onClick={
                    handleSaveCorrections
                  }

                  disabled={
                    saving
                    ||
                    !saveValidation
                    ||
                    !saveValidation.canSave
                  }
                >

                  {
                    saving
                      ? "Saving..."
                      : "Save corrections"
                  }

                </button>


                {
                  saveMessage && (

                    <span className="save-message">

                      ✓{" "}

                      {
                        saveMessage
                      }

                    </span>

                  )
                }

              </div>


              {/* DRAW */}

              {
                addMode && (

                  <div className="draw-instruction">

                    <strong>

                      Adding{" "}

                      {
                        addMode
                      }

                    </strong>


                    <span>

                      Click and drag on the
                      floor plan to draw the
                      new{" "}

                      {
                        addMode
                      }.

                    </span>

                  </div>

                )
              }


              {/* LEGEND */}

              <div className="detection-legend">

                <div>

                  <span className="legend-color room-color" />

                  Rooms

                </div>


                <div>

                  <span className="legend-color door-color" />

                  Doors

                </div>


                <div>

                  <span className="legend-color window-color" />

                  Windows

                </div>


                <div>

                  <span className="legend-color opening-color" />

                  Openings

                </div>


                <div>

                  <span className="legend-color boundary-outer-color" />

                  Outer boundary

                </div>


                <div>

                  <span className="legend-color boundary-usable-color" />

                  Usable boundary

                </div>

              </div>


              {/* EDITOR */}

              <div className="editor-layout">

                <div className="canvas-section">

                  <FloorPlanCanvas
                    floorPlan={
                      floorPlan
                    }

                    selectedType={
                      selectedType
                    }

                    selectedId={
                      selectedId
                    }

                    addMode={
                      addMode
                    }

                    boundaryEditMode={
                      boundaryEditMode
                    }

                    onSelect={
                      selectElement
                    }

                    onMoveElement={
                      moveElement
                    }

                    onCreateElement={
                      createElement
                    }

                    onMoveBoundaryPoint={
                      moveBoundaryPoint
                    }

                    onInsertBoundaryPoint={
                      insertBoundaryPoint
                    }

                    onDeleteBoundaryPoint={
                      deleteBoundaryPoint
                    }
                  />

                </div>


                <aside className="editor-panel">

                  <h3>
                    Object editor
                  </h3>


                  {/* ROOM */}

                  {
                    selectedRoom && (

                      <>

                        <div className="object-type-badge room-badge">
                          Room
                        </div>


                        <div className="editor-field">

                          <label>
                            Room ID
                          </label>


                          <div className="readonly-value">

                            {
                              selectedRoom.id
                            }

                          </div>

                        </div>


                        <div className="editor-field">

                          <label>
                            Room name
                          </label>


                          <input
                            type="text"

                            value={
                              selectedRoom.name
                            }

                            onChange={
                              event =>
                                renameRoom(
                                  selectedRoom.id,
                                  event.target.value
                                )
                            }
                          />

                        </div>


                        <div className="editor-field">

                          <label>
                            Area (m²)
                          </label>


                          <input
                            type="number"

                            min="0"

                            step="0.01"

                            placeholder="Example: 12.5"

                            value={
                              selectedRoom
                                .areaSquareMetres
                                ??
                                ""
                            }

                            onChange={
                              event =>
                                changeRoomArea(
                                  selectedRoom.id,
                                  event.target.value
                                )
                            }

                            style={{
                              borderColor:
                                selectedRoom
                                  .areaSquareMetres == null
                                ||
                                selectedRoom
                                  .areaSquareMetres <= 0
                                  ? "#dc2626"
                                  : undefined,
                            }}
                          />


                          {
                            (
                              selectedRoom
                                .areaSquareMetres == null
                              ||
                              selectedRoom
                                .areaSquareMetres <= 0
                            )
                            && (

                              <small
                                style={{
                                  color:
                                    "#b42318",

                                  marginTop:
                                    "5px",
                                }}
                              >

                                Area is required before saving.

                              </small>

                            )
                          }

                        </div>


                        <div className="editor-field">

                          <label>
                            Source
                          </label>


                          <div className="readonly-value">

                            {
                              selectedRoom
                                .isUserAdded
                                ? "User added"
                                : `AI · ${(
                                    selectedRoom.confidence
                                    *
                                    100
                                  ).toFixed(1)}%`
                            }

                          </div>

                        </div>


                        <button
                          className="delete-button"

                          onClick={
                            () =>
                              deleteElement(
                                "room",
                                selectedRoom.id
                              )
                          }
                        >

                          Delete room

                        </button>

                      </>

                    )
                  }


                  {/* DOOR */}

                  {
                    selectedDoor && (

                      <>

                        <div className="object-type-badge door-badge">
                          Door
                        </div>


                        <div className="editor-field">

                          <label>
                            Door ID
                          </label>


                          <div className="readonly-value">

                            {
                              selectedDoor.id
                            }

                          </div>

                        </div>


                        <div className="editor-field">

                          <label>
                            Connected room 1
                          </label>


                          <select
                            value={
                              selectedDoor.room1.id
                            }

                            onChange={
                              event =>
                                changeDoorRoom(
                                  selectedDoor.id,
                                  "room1",
                                  Number(
                                    event.target.value
                                  )
                                )
                            }
                          >

                            {
                              floorPlan
                                .revision
                                .rooms
                                .map(
                                  room => (

                                    <option
                                      key={
                                        room.id
                                      }

                                      value={
                                        room.id
                                      }

                                      disabled={
                                        room.id ===
                                        selectedDoor.room2?.id
                                      }
                                    >

                                      {
                                        room.id
                                      }.{" "}

                                      {
                                        room.name
                                      }

                                    </option>

                                  )
                                )
                            }

                          </select>

                        </div>


                        <div className="editor-field">

                          <label>
                            Connected room 2
                          </label>


                          <select
                            value={
                              selectedDoor.room2?.id
                              ?? "outside"
                            }

                            onChange={
                              event =>
                                changeDoorRoom(
                                  selectedDoor.id,
                                  "room2",
                                  event.target.value ===
                                    "outside"
                                    ? null
                                    : Number(
                                        event.target.value
                                      )
                                )
                            }
                          >

                            <option
                              value="outside"
                            >
                              Outside
                            </option>

                            {
                              floorPlan
                                .revision
                                .rooms
                                .map(
                                  room => (

                                    <option
                                      key={
                                        room.id
                                      }

                                      value={
                                        room.id
                                      }

                                      disabled={
                                        room.id ===
                                        selectedDoor.room1.id
                                      }
                                    >

                                      {
                                        room.id
                                      }.{" "}

                                      {
                                        room.name
                                      }

                                    </option>

                                  )
                                )
                            }

                          </select>

                        </div>


                        <button
                          className="delete-button"

                          onClick={
                            () =>
                              deleteElement(
                                "door",
                                selectedDoor.id
                              )
                          }
                        >

                          Delete door

                        </button>

                      </>

                    )
                  }


                  {/* WINDOW */}

                  {
                    selectedWindow && (

                      <>

                        <div className="object-type-badge window-badge">
                          Window
                        </div>


                        <div className="editor-field">

                          <label>
                            Window ID
                          </label>


                          <div className="readonly-value">

                            {
                              selectedWindow.id
                            }

                          </div>

                        </div>


                        <button
                          className="delete-button"

                          onClick={
                            () =>
                              deleteElement(
                                "window",
                                selectedWindow.id
                              )
                          }
                        >

                          Delete window

                        </button>

                      </>

                    )
                  }


                  {/* OPENING */}

                  {
                    selectedOpening && (

                      <>

                        <div className="object-type-badge opening-badge">
                          Opening
                        </div>


                        <div className="editor-field">

                          <label>
                            Opening ID
                          </label>


                          <div className="readonly-value">

                            {
                              selectedOpening.id
                            }

                          </div>

                        </div>


                        <div className="editor-field">

                          <label>
                            Connected room 1
                          </label>


                          <select
                            value={
                              selectedOpening.room1.id
                            }

                            onChange={
                              event =>
                                changeOpeningRoom(
                                  selectedOpening.id,
                                  "room1",
                                  Number(
                                    event.target.value
                                  )
                                )
                            }
                          >

                            {
                              floorPlan
                                .revision
                                .rooms
                                .map(
                                  room => (

                                    <option
                                      key={
                                        room.id
                                      }

                                      value={
                                        room.id
                                      }

                                      disabled={
                                        room.id ===
                                        selectedOpening.room2.id
                                      }
                                    >

                                      {
                                        room.id
                                      }.{" "}

                                      {
                                        room.name
                                      }

                                    </option>

                                  )
                                )
                            }

                          </select>

                        </div>


                        <div className="editor-field">

                          <label>
                            Connected room 2
                          </label>


                          <select
                            value={
                              selectedOpening.room2.id
                            }

                            onChange={
                              event =>
                                changeOpeningRoom(
                                  selectedOpening.id,
                                  "room2",
                                  Number(
                                    event.target.value
                                  )
                                )
                            }
                          >

                            {
                              floorPlan
                                .revision
                                .rooms
                                .map(
                                  room => (

                                    <option
                                      key={
                                        room.id
                                      }

                                      value={
                                        room.id
                                      }

                                      disabled={
                                        room.id ===
                                        selectedOpening.room1.id
                                      }
                                    >

                                      {
                                        room.id
                                      }.{" "}

                                      {
                                        room.name
                                      }

                                    </option>

                                  )
                                )
                            }

                          </select>

                        </div>


                        <button
                          className="delete-button"

                          onClick={
                            () =>
                              deleteElement(
                                "opening",
                                selectedOpening.id
                              )
                          }
                        >

                          Delete opening

                        </button>

                      </>

                    )
                  }


                  {
                    !selectedRoom
                    &&
                    !selectedDoor
                    &&
                    !selectedWindow
                    &&
                    !selectedOpening
                    && (

                      <p className="no-selection">

                        {
                          addMode
                            ? `Draw the new ${addMode} on the floor plan.`
                            : "Click a room, door, window or opening to edit it."
                        }

                      </p>

                    )
                  }

                </aside>

              </div>


              {/* ROOM LIST */}

              <div className="rooms">

                <h3>
                  Rooms
                </h3>


                <div className="room-list">

                  {
                    floorPlan
                      .revision
                      .rooms
                      .map(
                        room => (

                          <button
                            key={
                              room.id
                            }

                            className={
                              selectedType === "room"
                              &&
                              selectedId === room.id
                                ? "room-card room-card-selected"
                                : "room-card"
                            }

                            onClick={
                              () => {

                                setAddMode(
                                  null
                                );


                                selectElement(
                                  "room",
                                  room.id
                                );

                              }
                            }
                          >

                            <strong>

                              {
                                room.id
                              }.{" "}

                              {
                                room.name
                              }

                            </strong>


                            <span>

                              {
                                room.isUserAdded
                                  ? "User added"
                                  : `Confidence: ${(
                                      room.confidence
                                      *
                                      100
                                    ).toFixed(1)}%`
                              }

                            </span>


                            <span
                              style={{
                                color:
                                  room.areaSquareMetres == null
                                  ||
                                  room.areaSquareMetres <= 0
                                    ? "#b42318"
                                    : undefined,

                                fontWeight:
                                  room.areaSquareMetres == null
                                  ||
                                  room.areaSquareMetres <= 0
                                    ? 700
                                    : undefined,
                              }}
                            >

                              Area:{" "}

                              {
                                room.areaSquareMetres == null
                                ||
                                room.areaSquareMetres <= 0
                                  ? "Missing"
                                  : `${room.areaSquareMetres} m²`
                              }

                            </span>

                          </button>

                        )
                      )
                  }

                </div>

              </div>

            </section>

          )
        }

      </main>

    </div>

  );

}


// =========================================================
// APP
// =========================================================

function App() {

  const location =
    useLocation();


  const analyzeActive =
    location.pathname === "/"
    ||
    location.pathname.startsWith(
      "/floorplans/"
    );


  const savedActive =
    location.pathname ===
    "/saved";


  return (

    <>

      <nav
        style={{
          display:
            "flex",

          alignItems:
            "center",

          gap:
            "8px",

          padding:
            "12px 24px",

          background:
            "#ffffff",

          borderBottom:
            "1px solid #e4e7ec",

          position:
            "sticky",

          top:
            0,

          zIndex:
            100,
        }}
      >

        <Link
          to="/"

          style={{
            padding:
              "9px 14px",

            borderRadius:
              "8px",

            textDecoration:
              "none",

            fontWeight:
              700,

            color:
              analyzeActive
                ? "#ffffff"
                : "#344054",

            background:
              analyzeActive
                ? "#101828"
                : "transparent",
          }}
        >

          Analyze floor plan

        </Link>


        <Link
          to="/saved"

          style={{
            padding:
              "9px 14px",

            borderRadius:
              "8px",

            textDecoration:
              "none",

            fontWeight:
              700,

            color:
              savedActive
                ? "#ffffff"
                : "#344054",

            background:
              savedActive
                ? "#101828"
                : "transparent",
          }}
        >

          Saved floor plans

        </Link>

      </nav>


      <Routes>

        <Route
          path="/"

          element={
            <AnalyzePage />
          }
        />


        <Route
          path="/floorplans/:floorPlanId"

          element={
            <AnalyzePage />
          }
        />


        <Route
          path="/saved"

          element={
            <SavedFloorPlansPage />
          }
        />

      </Routes>

    </>

  );

}


export default App;