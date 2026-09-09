import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Group,
  Image as KonvaImage,
  Layer,
  Line,
  Stage,
  Text,
} from "react-konva";

import type Konva from "konva";

import type {
  FloorPlan,
  PixelPoint,
} from "../types";

import {
  getImageUrl,
} from "../api";


export type ElementType =
  | "room"
  | "door"
  | "window"
  | "opening";


interface FloorPlanCanvasProps {
  floorPlan:
    FloorPlan;

  selectedType:
    ElementType | null;

  selectedId:
    number | null;

  addMode:
    ElementType | null;


  onSelect: (
    type: ElementType | null,
    id: number | null
  ) => void;


  onMoveElement: (
    type: ElementType,
    id: number,
    deltaX: number,
    deltaY: number
  ) => void;


  onCreateElement: (
    type: ElementType,
    polygon: PixelPoint[]
  ) => void;
}


// =========================================================
// POLYGON → KONVA POINTS
// =========================================================

function polygonToPoints(
  polygon: PixelPoint[]
): number[] {

  return polygon.flatMap(
    point => [
      point.x,
      point.y,
    ]
  );
}


// =========================================================
// CANVAS
// =========================================================

function FloorPlanCanvas({
  floorPlan,

  selectedType,
  selectedId,

  addMode,

  onSelect,
  onMoveElement,
  onCreateElement,
}: FloorPlanCanvasProps) {

  const containerRef =
    useRef<HTMLDivElement | null>(
      null
    );


  const [image, setImage] =
    useState<HTMLImageElement | null>(
      null
    );


  const [
    containerWidth,
    setContainerWidth,
  ] =
    useState(0);


  const [
    drawingStart,
    setDrawingStart,
  ] =
    useState<PixelPoint | null>(
      null
    );


  const [
    drawingCurrent,
    setDrawingCurrent,
  ] =
    useState<PixelPoint | null>(
      null
    );


  // =========================================================
  // LOAD IMAGE
  // =========================================================

  useEffect(() => {

    const imageElement =
      new window.Image();


    imageElement.onload =
      () => {

        setImage(
          imageElement
        );

      };


    imageElement.src =
      getImageUrl(
        floorPlan.imagePath
      );


    return () => {

      imageElement.onload =
        null;

    };

  }, [
    floorPlan.imagePath,
  ]);


  // =========================================================
  // CONTAINER SIZE
  // =========================================================

  useEffect(() => {

    const container =
      containerRef.current;


    if (!container) {
      return;
    }


    const updateWidth = () => {

      setContainerWidth(
        container.clientWidth
      );

    };


    updateWidth();


    const observer =
      new ResizeObserver(
        updateWidth
      );


    observer.observe(
      container
    );


    return () => {

      observer.disconnect();

    };

  }, []);


  // =========================================================
  // RESET DRAWING
  // =========================================================

  useEffect(() => {

    setDrawingStart(
      null
    );

    setDrawingCurrent(
      null
    );

  }, [
    addMode,
  ]);


  // =========================================================
  // DIMENSIONS
  // =========================================================

  const originalWidth =
    floorPlan.widthPixels;


  const originalHeight =
    floorPlan.heightPixels;


  if (
    !image ||
    containerWidth === 0 ||
    originalWidth === 0 ||
    originalHeight === 0
  ) {

    return (

      <div
        ref={
          containerRef
        }

        className=
          "floor-plan-stage-container"
      >

        Loading floor plan...

      </div>

    );

  }


  // =========================================================
  // DISPLAY SCALE
  // =========================================================

  const displayWidth =
    Math.min(
      containerWidth,
      originalWidth
    );


  const scale =
    displayWidth /
    originalWidth;


  const displayHeight =
    originalHeight *
    scale;


  const roomStroke =
    2 / scale;


  const selectedRoomStroke =
    5 / scale;


  const objectStroke =
    3 / scale;


  const selectedObjectStroke =
    6 / scale;


  const fontSize =
    16 / scale;


  // =========================================================
  // POINTER → ORIGINAL IMAGE COORDINATES
  // =========================================================

  function getOriginalPointer(
    stage: Konva.Stage
  ): PixelPoint | null {

    const pointer =
      stage.getPointerPosition();


    if (!pointer) {
      return null;
    }


    return {

      x:
        Math.max(
          0,
          Math.min(
            originalWidth,
            pointer.x / scale
          )
        ),

      y:
        Math.max(
          0,
          Math.min(
            originalHeight,
            pointer.y / scale
          )
        ),

    };

  }


  // =========================================================
  // FINISH DRAG
  // =========================================================

  function finishDrag(
    type: ElementType,
    id: number,
    node: Konva.Node
  ) {

    const deltaX =
      node.x();


    const deltaY =
      node.y();


    onMoveElement(
      type,
      id,
      deltaX,
      deltaY
    );


    node.position({
      x: 0,
      y: 0,
    });

  }


  // =========================================================
  // START DRAWING NEW OBJECT
  // =========================================================

  function startDrawing(
    stage: Konva.Stage
  ) {

    if (!addMode) {
      return;
    }


    const point =
      getOriginalPointer(
        stage
      );


    if (!point) {
      return;
    }


    setDrawingStart(
      point
    );


    setDrawingCurrent(
      point
    );

  }


  // =========================================================
  // CONTINUE DRAWING
  // =========================================================

  function continueDrawing(
    stage: Konva.Stage
  ) {

    if (
      !addMode ||
      !drawingStart
    ) {
      return;
    }


    const point =
      getOriginalPointer(
        stage
      );


    if (!point) {
      return;
    }


    setDrawingCurrent(
      point
    );

  }


  // =========================================================
  // FINISH DRAWING
  // =========================================================

  function finishDrawing(
    stage: Konva.Stage
  ) {

    if (
      !addMode ||
      !drawingStart
    ) {
      return;
    }


    const end =
      getOriginalPointer(
        stage
      );


    if (!end) {
      return;
    }


    const x1 =
      Math.min(
        drawingStart.x,
        end.x
      );


    const y1 =
      Math.min(
        drawingStart.y,
        end.y
      );


    const x2 =
      Math.max(
        drawingStart.x,
        end.x
      );


    const y2 =
      Math.max(
        drawingStart.y,
        end.y
      );


    setDrawingStart(
      null
    );


    setDrawingCurrent(
      null
    );


    if (
      x2 - x1 < 8 ||
      y2 - y1 < 8
    ) {
      return;
    }


    const polygon:
      PixelPoint[] = [

        {
          x: x1,
          y: y1,
        },

        {
          x: x2,
          y: y1,
        },

        {
          x: x2,
          y: y2,
        },

        {
          x: x1,
          y: y2,
        },

      ];


    onCreateElement(
      addMode,
      polygon
    );

  }


  // =========================================================
  // DRAWING PREVIEW
  // =========================================================

  let previewPolygon:
    PixelPoint[] | null =
    null;


  if (
    drawingStart &&
    drawingCurrent
  ) {

    const x1 =
      Math.min(
        drawingStart.x,
        drawingCurrent.x
      );


    const y1 =
      Math.min(
        drawingStart.y,
        drawingCurrent.y
      );


    const x2 =
      Math.max(
        drawingStart.x,
        drawingCurrent.x
      );


    const y2 =
      Math.max(
        drawingStart.y,
        drawingCurrent.y
      );


    previewPolygon = [

      {
        x: x1,
        y: y1,
      },

      {
        x: x2,
        y: y1,
      },

      {
        x: x2,
        y: y2,
      },

      {
        x: x1,
        y: y2,
      },

    ];

  }


  // =========================================================
  // PREVIEW COLOR
  // =========================================================

  function previewColor(): string {

    switch (addMode) {

      case "room":
        return "#16a34a";

      case "door":
        return "#dc2626";

      case "window":
        return "#2563eb";

      case "opening":
        return "#ea580c";

      default:
        return "#111827";

    }

  }


  // =========================================================
  // UI
  // =========================================================

  return (

    <div
      ref={
        containerRef
      }

      className=
        "floor-plan-stage-container"

      style={{
        cursor:
          addMode
            ? "crosshair"
            : "default",
      }}
    >

      <Stage
        width={
          displayWidth
        }

        height={
          displayHeight
        }

        onMouseDown={
          event => {

            const stage =
              event.target
                .getStage();


            if (!stage) {
              return;
            }


            if (addMode) {

              startDrawing(
                stage
              );

              return;

            }


            if (
              event.target ===
              stage
            ) {

              onSelect(
                null,
                null
              );

            }

          }
        }

        onMouseMove={
          event => {

            if (!addMode) {
              return;
            }


            const stage =
              event.target
                .getStage();


            if (!stage) {
              return;
            }


            continueDrawing(
              stage
            );

          }
        }

        onMouseUp={
          event => {

            if (!addMode) {
              return;
            }


            const stage =
              event.target
                .getStage();


            if (!stage) {
              return;
            }


            finishDrawing(
              stage
            );

          }
        }
      >

        <Layer
          scaleX={
            scale
          }

          scaleY={
            scale
          }
        >

          {/* =============================================== */}
          {/* IMAGE */}
          {/* =============================================== */}

          <KonvaImage
            image={
              image
            }

            width={
              originalWidth
            }

            height={
              originalHeight
            }

            listening={
              false
            }
          />


          {/* =============================================== */}
          {/* ROOMS */}
          {/* =============================================== */}

          {
            floorPlan
              .revision
              .rooms
              .map(
                room => {

                  const selected =
                    selectedType ===
                      "room"
                    &&
                    selectedId ===
                      room.id;


                  const labelWidth =
                    200 / scale;


                  return (

                    <Group
                      key={
                        `room-${room.id}`
                      }

                      listening={
                        !addMode
                      }

                      draggable={
                        selected &&
                        !addMode
                      }

                      onClick={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "room",
                            room.id
                          );

                        }
                      }

                      onTap={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "room",
                            room.id
                          );

                        }
                      }

                      onDragEnd={
                        event => {

                          finishDrag(
                            "room",
                            room.id,
                            event.currentTarget
                          );

                        }
                      }
                    >

                      <Line
                        points={
                          polygonToPoints(
                            room.polygon
                          )
                        }

                        closed

                        stroke={
                          selected
                            ? "#15803d"
                            : "#16a34a"
                        }

                        strokeWidth={
                          selected
                            ? selectedRoomStroke
                            : roomStroke
                        }

                        fill={
                          selected
                            ? "rgba(22, 163, 74, 0.22)"
                            : "rgba(22, 163, 74, 0.10)"
                        }
                      />


                      <Text
                        x={
                          room.centroid.x -
                          labelWidth / 2
                        }

                        y={
                          room.centroid.y -
                          fontSize / 2
                        }

                        width={
                          labelWidth
                        }

                        text={
                          `${room.id}. ${room.name}`
                        }

                        align=
                          "center"

                        fontSize={
                          fontSize
                        }

                        fontStyle=
                          "bold"

                        fill=
                          "#111827"

                        listening={
                          false
                        }
                      />

                    </Group>

                  );

                }
              )
          }


          {/* =============================================== */}
          {/* DOORS */}
          {/* =============================================== */}

          {
            floorPlan
              .revision
              .doors
              .map(
                door => {

                  const selected =
                    selectedType ===
                      "door"
                    &&
                    selectedId ===
                      door.id;


                  return (

                    <Group
                      key={
                        `door-${door.id}`
                      }

                      listening={
                        !addMode
                      }

                      draggable={
                        selected &&
                        !addMode
                      }

                      onClick={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "door",
                            door.id
                          );

                        }
                      }

                      onTap={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "door",
                            door.id
                          );

                        }
                      }

                      onDragEnd={
                        event => {

                          finishDrag(
                            "door",
                            door.id,
                            event.currentTarget
                          );

                        }
                      }
                    >

                      <Line
                        points={
                          polygonToPoints(
                            door.polygon
                          )
                        }

                        closed

                        stroke={
                          selected
                            ? "#991b1b"
                            : "#dc2626"
                        }

                        strokeWidth={
                          selected
                            ? selectedObjectStroke
                            : objectStroke
                        }

                        fill={
                          selected
                            ? "rgba(220, 38, 38, 0.35)"
                            : "rgba(220, 38, 38, 0.20)"
                        }
                      />

                    </Group>

                  );

                }
              )
          }


          {/* =============================================== */}
          {/* WINDOWS */}
          {/* =============================================== */}

          {
            floorPlan
              .revision
              .windows
              .map(
                window => {

                  const selected =
                    selectedType ===
                      "window"
                    &&
                    selectedId ===
                      window.id;


                  return (

                    <Group
                      key={
                        `window-${window.id}`
                      }

                      listening={
                        !addMode
                      }

                      draggable={
                        selected &&
                        !addMode
                      }

                      onClick={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "window",
                            window.id
                          );

                        }
                      }

                      onTap={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "window",
                            window.id
                          );

                        }
                      }

                      onDragEnd={
                        event => {

                          finishDrag(
                            "window",
                            window.id,
                            event.currentTarget
                          );

                        }
                      }
                    >

                      <Line
                        points={
                          polygonToPoints(
                            window.polygon
                          )
                        }

                        closed

                        stroke={
                          selected
                            ? "#1e40af"
                            : "#2563eb"
                        }

                        strokeWidth={
                          selected
                            ? selectedObjectStroke
                            : objectStroke
                        }

                        fill={
                          selected
                            ? "rgba(37, 99, 235, 0.35)"
                            : "rgba(37, 99, 235, 0.20)"
                        }
                      />

                    </Group>

                  );

                }
              )
          }


          {/* =============================================== */}
          {/* OPENINGS */}
          {/* =============================================== */}

          {
            floorPlan
              .revision
              .openings
              .map(
                opening => {

                  const selected =
                    selectedType ===
                      "opening"
                    &&
                    selectedId ===
                      opening.id;


                  return (

                    <Group
                      key={
                        `opening-${opening.id}`
                      }

                      listening={
                        !addMode
                      }

                      draggable={
                        selected &&
                        !addMode
                      }

                      onClick={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "opening",
                            opening.id
                          );

                        }
                      }

                      onTap={
                        event => {

                          event.cancelBubble =
                            true;


                          onSelect(
                            "opening",
                            opening.id
                          );

                        }
                      }

                      onDragEnd={
                        event => {

                          finishDrag(
                            "opening",
                            opening.id,
                            event.currentTarget
                          );

                        }
                      }
                    >

                      <Line
                        points={
                          polygonToPoints(
                            opening.polygon
                          )
                        }

                        closed

                        stroke={
                          selected
                            ? "#9a3412"
                            : "#ea580c"
                        }

                        strokeWidth={
                          selected
                            ? selectedObjectStroke
                            : objectStroke
                        }

                        fill={
                          selected
                            ? "rgba(234, 88, 12, 0.35)"
                            : "rgba(234, 88, 12, 0.20)"
                        }
                      />

                    </Group>

                  );

                }
              )
          }


          {/* =============================================== */}
          {/* ADD OBJECT PREVIEW */}
          {/* =============================================== */}

          {
            previewPolygon &&
            addMode && (

              <Line
                points={
                  polygonToPoints(
                    previewPolygon
                  )
                }

                closed

                stroke={
                  previewColor()
                }

                strokeWidth={
                  4 / scale
                }

                dash={[
                  12 / scale,
                  8 / scale,
                ]}

                fill=
                  "rgba(255,255,255,0.20)"

                listening={
                  false
                }
              />

            )
          }

        </Layer>

      </Stage>

    </div>

  );

}


export default FloorPlanCanvas;