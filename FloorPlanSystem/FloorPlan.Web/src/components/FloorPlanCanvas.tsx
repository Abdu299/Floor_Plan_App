import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Circle,
  Group,
  Image as KonvaImage,
  Layer,
  Line,
  Stage,
  Text,
} from "react-konva";

import type Konva from "konva";

import type {
  BoundaryKind,
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
  floorPlan: FloorPlan;

  selectedType: ElementType | null;
  selectedId: number | null;

  addMode: ElementType | null;

  boundaryEditMode: BoundaryKind | null;

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

  onMoveBoundaryPoint: (
    kind: BoundaryKind,
    pointIndex: number,
    point: PixelPoint
  ) => void;

  onInsertBoundaryPoint: (
    kind: BoundaryKind,
    insertAfterIndex: number,
    point: PixelPoint
  ) => void;

  onDeleteBoundaryPoint: (
    kind: BoundaryKind,
    pointIndex: number
  ) => void;
}


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


function distanceToSegmentSquared(
  point: PixelPoint,
  start: PixelPoint,
  end: PixelPoint
): number {
  const dx = end.x - start.x;
  const dy = end.y - start.y;

  if (
    dx === 0 &&
    dy === 0
  ) {
    const px = point.x - start.x;
    const py = point.y - start.y;
    return px * px + py * py;
  }

  const lengthSquared =
    dx * dx + dy * dy;

  const t = Math.max(
    0,
    Math.min(
      1,
      (
        (point.x - start.x) * dx +
        (point.y - start.y) * dy
      ) / lengthSquared
    )
  );

  const closestX = start.x + t * dx;
  const closestY = start.y + t * dy;

  const px = point.x - closestX;
  const py = point.y - closestY;

  return px * px + py * py;
}


function closestSegmentIndex(
  polygon: PixelPoint[],
  point: PixelPoint
): number {
  if (polygon.length < 2) {
    return 0;
  }

  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (
    let index = 0;
    index < polygon.length;
    index++
  ) {
    const nextIndex =
      (index + 1) % polygon.length;

    const distance =
      distanceToSegmentSquared(
        point,
        polygon[index],
        polygon[nextIndex]
      );

    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  }

  return bestIndex;
}


function FloorPlanCanvas({
  floorPlan,
  selectedType,
  selectedId,
  addMode,
  boundaryEditMode,
  onSelect,
  onMoveElement,
  onCreateElement,
  onMoveBoundaryPoint,
  onInsertBoundaryPoint,
  onDeleteBoundaryPoint,
}: FloorPlanCanvasProps) {
  const containerRef =
    useRef<HTMLDivElement | null>(
      null
    );

  const [image, setImage] =
    useState<HTMLImageElement | null>(
      null
    );

  const [containerWidth, setContainerWidth] =
    useState(0);

  const [drawingStart, setDrawingStart] =
    useState<PixelPoint | null>(
      null
    );

  const [drawingCurrent, setDrawingCurrent] =
    useState<PixelPoint | null>(
      null
    );


  useEffect(() => {
    const imageElement =
      new window.Image();

    imageElement.onload = () => {
      setImage(imageElement);
    };

    imageElement.src =
      getImageUrl(
        floorPlan.imagePath
      );

    return () => {
      imageElement.onload = null;
    };
  }, [
    floorPlan.imagePath,
  ]);


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

    observer.observe(container);

    return () => {
      observer.disconnect();
    };
  }, []);


  useEffect(() => {
    setDrawingStart(null);
    setDrawingCurrent(null);
  }, [
    addMode,
  ]);


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
        ref={containerRef}
        className="floor-plan-stage-container"
      >
        Loading floor plan...
      </div>
    );
  }


  const displayWidth =
    Math.min(
      containerWidth,
      originalWidth
    );

  const scale =
    displayWidth /
    originalWidth;

  const displayHeight =
    originalHeight * scale;

  const roomStroke = 2 / scale;
  const selectedRoomStroke = 5 / scale;
  const objectStroke = 3 / scale;
  const selectedObjectStroke = 6 / scale;
  const fontSize = 16 / scale;
  const boundaryStroke = 4 / scale;
  const selectedBoundaryStroke = 7 / scale;
  const boundaryHandleRadius = 8 / scale;


  function clampPoint(
    point: PixelPoint
  ): PixelPoint {
    return {
      x: Math.max(
        0,
        Math.min(
          originalWidth,
          point.x
        )
      ),
      y: Math.max(
        0,
        Math.min(
          originalHeight,
          point.y
        )
      ),
    };
  }


  function getOriginalPointer(
    stage: Konva.Stage
  ): PixelPoint | null {
    const pointer =
      stage.getPointerPosition();

    if (!pointer) {
      return null;
    }

    return clampPoint({
      x: pointer.x / scale,
      y: pointer.y / scale,
    });
  }


  function finishDrag(
    type: ElementType,
    id: number,
    node: Konva.Node
  ) {
    const deltaX = node.x();
    const deltaY = node.y();

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


  function startDrawing(
    stage: Konva.Stage
  ) {
    if (!addMode) {
      return;
    }

    const point =
      getOriginalPointer(stage);

    if (!point) {
      return;
    }

    setDrawingStart(point);
    setDrawingCurrent(point);
  }


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
      getOriginalPointer(stage);

    if (!point) {
      return;
    }

    setDrawingCurrent(point);
  }


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
      getOriginalPointer(stage);

    if (!end) {
      return;
    }

    const x1 = Math.min(
      drawingStart.x,
      end.x
    );

    const y1 = Math.min(
      drawingStart.y,
      end.y
    );

    const x2 = Math.max(
      drawingStart.x,
      end.x
    );

    const y2 = Math.max(
      drawingStart.y,
      end.y
    );

    setDrawingStart(null);
    setDrawingCurrent(null);

    if (
      x2 - x1 < 8 ||
      y2 - y1 < 8
    ) {
      return;
    }

    onCreateElement(
      addMode,
      [
        { x: x1, y: y1 },
        { x: x2, y: y1 },
        { x: x2, y: y2 },
        { x: x1, y: y2 },
      ]
    );
  }


  let previewPolygon:
    PixelPoint[] | null = null;

  if (
    drawingStart &&
    drawingCurrent
  ) {
    const x1 = Math.min(
      drawingStart.x,
      drawingCurrent.x
    );

    const y1 = Math.min(
      drawingStart.y,
      drawingCurrent.y
    );

    const x2 = Math.max(
      drawingStart.x,
      drawingCurrent.x
    );

    const y2 = Math.max(
      drawingStart.y,
      drawingCurrent.y
    );

    previewPolygon = [
      { x: x1, y: y1 },
      { x: x2, y: y1 },
      { x: x2, y: y2 },
      { x: x1, y: y2 },
    ];
  }


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


  const boundary =
    floorPlan
      .revision
      .buildingBoundary;

  const outerPolygon =
    boundary?.outerPolygon ?? [];

  const usablePolygon =
    boundary?.usablePolygon ?? [];

  const automaticValid =
    boundary
      ?.automaticAssessment
      ?.valid ?? false;

  const boundaryNeedsReview =
    !automaticValid &&
    boundary?.reviewStatus !== "confirmed";


  function renderBoundaryLine(
    kind: BoundaryKind,
    polygon: PixelPoint[],
    color: string
  ) {
    if (polygon.length < 2) {
      return null;
    }

    const editing =
      boundaryEditMode === kind;

    return (
      <Line
        key={`boundary-${kind}`}
        points={polygonToPoints(polygon)}
        closed
        stroke={color}
        strokeWidth={
          editing
            ? selectedBoundaryStroke
            : boundaryStroke
        }
        dash={
          boundaryNeedsReview
            ? [
                12 / scale,
                7 / scale,
              ]
            : undefined
        }
        fill="rgba(0,0,0,0)"
        listening={
          editing &&
          !addMode
        }
        onDblClick={event => {
          if (!editing) {
            return;
          }

          event.cancelBubble = true;

          const stage =
            event.currentTarget.getStage();

          if (!stage) {
            return;
          }

          const point =
            getOriginalPointer(stage);

          if (!point) {
            return;
          }

          onInsertBoundaryPoint(
            kind,
            closestSegmentIndex(
              polygon,
              point
            ),
            point
          );
        }}
        onDblTap={event => {
          if (!editing) {
            return;
          }

          event.cancelBubble = true;

          const stage =
            event.currentTarget.getStage();

          if (!stage) {
            return;
          }

          const point =
            getOriginalPointer(stage);

          if (!point) {
            return;
          }

          onInsertBoundaryPoint(
            kind,
            closestSegmentIndex(
              polygon,
              point
            ),
            point
          );
        }}
      />
    );
  }


  function renderBoundaryHandles(
    kind: BoundaryKind,
    polygon: PixelPoint[],
    color: string
  ) {
    if (
      boundaryEditMode !== kind ||
      addMode
    ) {
      return null;
    }

    return polygon.map(
      (point, pointIndex) => (
        <Circle
          key={`boundary-${kind}-point-${pointIndex}`}
          x={point.x}
          y={point.y}
          radius={boundaryHandleRadius}
          fill="#ffffff"
          stroke={color}
          strokeWidth={3 / scale}
          draggable
          onDragEnd={event => {
            const next = clampPoint({
              x: event.currentTarget.x(),
              y: event.currentTarget.y(),
            });

            onMoveBoundaryPoint(
              kind,
              pointIndex,
              next
            );
          }}
          onDblClick={event => {
            event.cancelBubble = true;

            if (polygon.length <= 3) {
              return;
            }

            onDeleteBoundaryPoint(
              kind,
              pointIndex
            );
          }}
          onDblTap={event => {
            event.cancelBubble = true;

            if (polygon.length <= 3) {
              return;
            }

            onDeleteBoundaryPoint(
              kind,
              pointIndex
            );
          }}
        />
      )
    );
  }


  return (
    <div
      ref={containerRef}
      className="floor-plan-stage-container"
      style={{
        cursor:
          addMode
            ? "crosshair"
            : boundaryEditMode
              ? "crosshair"
              : "default",
      }}
    >
      <Stage
        width={displayWidth}
        height={displayHeight}
        onMouseDown={event => {
          const stage =
            event.target.getStage();

          if (!stage) {
            return;
          }

          if (addMode) {
            startDrawing(stage);
            return;
          }

          if (
            event.target === stage
          ) {
            onSelect(null, null);
          }
        }}
        onMouseMove={event => {
          if (!addMode) {
            return;
          }

          const stage =
            event.target.getStage();

          if (!stage) {
            return;
          }

          continueDrawing(stage);
        }}
        onMouseUp={event => {
          if (!addMode) {
            return;
          }

          const stage =
            event.target.getStage();

          if (!stage) {
            return;
          }

          finishDrawing(stage);
        }}
      >
        <Layer
          scaleX={scale}
          scaleY={scale}
        >
          <KonvaImage
            image={image}
            width={originalWidth}
            height={originalHeight}
            listening={false}
          />

          {/* Building boundary is always visible when geometry exists. */}
          {renderBoundaryLine(
            "outer",
            outerPolygon,
            "#d946ef"
          )}

          {renderBoundaryLine(
            "usable",
            usablePolygon,
            "#0891b2"
          )}


          {floorPlan.revision.rooms.map(room => {
            const selected =
              selectedType === "room" &&
              selectedId === room.id;

            const labelWidth =
              200 / scale;

            return (
              <Group
                key={`room-${room.id}`}
                listening={
                  !addMode &&
                  !boundaryEditMode
                }
                draggable={
                  selected &&
                  !addMode &&
                  !boundaryEditMode
                }
                onClick={event => {
                  event.cancelBubble = true;
                  onSelect("room", room.id);
                }}
                onTap={event => {
                  event.cancelBubble = true;
                  onSelect("room", room.id);
                }}
                onDragEnd={event => {
                  finishDrag(
                    "room",
                    room.id,
                    event.currentTarget
                  );
                }}
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
                  width={labelWidth}
                  text={`${room.id}. ${room.name}`}
                  align="center"
                  fontSize={fontSize}
                  fontStyle="bold"
                  fill="#111827"
                  listening={false}
                />
              </Group>
            );
          })}


          {floorPlan.revision.doors.map(door => {
            const selected =
              selectedType === "door" &&
              selectedId === door.id;

            return (
              <Group
                key={`door-${door.id}`}
                listening={
                  !addMode &&
                  !boundaryEditMode
                }
                draggable={
                  selected &&
                  !addMode &&
                  !boundaryEditMode
                }
                onClick={event => {
                  event.cancelBubble = true;
                  onSelect("door", door.id);
                }}
                onTap={event => {
                  event.cancelBubble = true;
                  onSelect("door", door.id);
                }}
                onDragEnd={event => {
                  finishDrag(
                    "door",
                    door.id,
                    event.currentTarget
                  );
                }}
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
          })}


          {floorPlan.revision.windows.map(window => {
            const selected =
              selectedType === "window" &&
              selectedId === window.id;

            return (
              <Group
                key={`window-${window.id}`}
                listening={
                  !addMode &&
                  !boundaryEditMode
                }
                draggable={
                  selected &&
                  !addMode &&
                  !boundaryEditMode
                }
                onClick={event => {
                  event.cancelBubble = true;
                  onSelect("window", window.id);
                }}
                onTap={event => {
                  event.cancelBubble = true;
                  onSelect("window", window.id);
                }}
                onDragEnd={event => {
                  finishDrag(
                    "window",
                    window.id,
                    event.currentTarget
                  );
                }}
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
          })}


          {floorPlan.revision.openings.map(opening => {
            const selected =
              selectedType === "opening" &&
              selectedId === opening.id;

            return (
              <Group
                key={`opening-${opening.id}`}
                listening={
                  !addMode &&
                  !boundaryEditMode
                }
                draggable={
                  selected &&
                  !addMode &&
                  !boundaryEditMode
                }
                onClick={event => {
                  event.cancelBubble = true;
                  onSelect("opening", opening.id);
                }}
                onTap={event => {
                  event.cancelBubble = true;
                  onSelect("opening", opening.id);
                }}
                onDragEnd={event => {
                  finishDrag(
                    "opening",
                    opening.id,
                    event.currentTarget
                  );
                }}
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
          })}


          {previewPolygon && addMode && (
            <Line
              points={
                polygonToPoints(
                  previewPolygon
                )
              }
              closed
              stroke={previewColor()}
              strokeWidth={4 / scale}
              dash={[
                12 / scale,
                8 / scale,
              ]}
              fill="rgba(255,255,255,0.20)"
              listening={false}
            />
          )}


          {/* Handles are rendered last so they remain easy to grab. */}
          {renderBoundaryHandles(
            "outer",
            outerPolygon,
            "#d946ef"
          )}

          {renderBoundaryHandles(
            "usable",
            usablePolygon,
            "#0891b2"
          )}
        </Layer>
      </Stage>
    </div>
  );
}


export default FloorPlanCanvas;
