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
  FloorPlan,
  PixelPoint,
} from "../types";

import {
  getImageUrl,
} from "../api";

import {
  polygonInsidePolygon,
} from "../geometry";

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
  boundaryEditMode: boolean;
  boundaryDrawMode: boolean;
  boundaryDraftPoints: PixelPoint[];
  roomEditModeId: number | null;
  roomDrawModeId: number | null;
  roomDraftPoints: PixelPoint[];

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
    pointIndex: number,
    point: PixelPoint
  ) => void;

  onInsertBoundaryPoint: (
    insertAfterIndex: number,
    point: PixelPoint
  ) => void;

  onDeleteBoundaryPoint: (
    pointIndex: number
  ) => void;

  onAddBoundaryDraftPoint: (
    point: PixelPoint
  ) => void;

  onMoveRoomPoint: (
    roomId: number,
    pointIndex: number,
    point: PixelPoint
  ) => void;

  onInsertRoomPoint: (
    roomId: number,
    insertAfterIndex: number,
    point: PixelPoint
  ) => void;

  onDeleteRoomPoint: (
    roomId: number,
    pointIndex: number
  ) => void;

  onAddRoomDraftPoint: (
    point: PixelPoint
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
  const dx =
    end.x - start.x;

  const dy =
    end.y - start.y;

  if (
    dx === 0 &&
    dy === 0
  ) {
    const px =
      point.x - start.x;

    const py =
      point.y - start.y;

    return (
      px * px +
      py * py
    );
  }

  const lengthSquared =
    dx * dx +
    dy * dy;

  const t =
    Math.max(
      0,
      Math.min(
        1,
        (
          (point.x - start.x) * dx +
          (point.y - start.y) * dy
        ) /
        lengthSquared
      )
    );

  const closestX =
    start.x +
    t * dx;

  const closestY =
    start.y +
    t * dy;

  const px =
    point.x - closestX;

  const py =
    point.y - closestY;

  return (
    px * px +
    py * py
  );
}

function closestSegmentIndex(
  polygon: PixelPoint[],
  point: PixelPoint
): number {
  if (
    polygon.length < 2
  ) {
    return 0;
  }

  let bestIndex = 0;
  let bestDistance =
    Number.POSITIVE_INFINITY;

  for (
    let index = 0;
    index < polygon.length;
    index++
  ) {
    const nextIndex =
      (index + 1) %
      polygon.length;

    const distance =
      distanceToSegmentSquared(
        point,
        polygon[index],
        polygon[nextIndex]
      );

    if (
      distance < bestDistance
    ) {
      bestDistance =
        distance;

      bestIndex =
        index;
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
  boundaryDrawMode,
  boundaryDraftPoints,
  roomEditModeId,
  roomDrawModeId,
  roomDraftPoints,
  onSelect,
  onMoveElement,
  onCreateElement,
  onMoveBoundaryPoint,
  onInsertBoundaryPoint,
  onDeleteBoundaryPoint,
  onAddBoundaryDraftPoint,
  onMoveRoomPoint,
  onInsertRoomPoint,
  onDeleteRoomPoint,
  onAddRoomDraftPoint,
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

  const [boundaryHoverPoint, setBoundaryHoverPoint] =
    useState<PixelPoint | null>(
      null
    );

  const [roomHoverPoint, setRoomHoverPoint] =
    useState<PixelPoint | null>(
      null
    );

  useEffect(
    () => {
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
    },
    [floorPlan.imagePath]
  );

  useEffect(
    () => {
      const container =
        containerRef.current;

      if (!container) {
        return;
      }

      const updateWidth =
        () => {
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
    },
    []
  );

  useEffect(
    () => {
      setDrawingStart(
        null
      );

      setDrawingCurrent(
        null
      );
    },
    [addMode]
  );

  useEffect(
    () => {
      setBoundaryHoverPoint(
        null
      );
    },
    [boundaryDrawMode]
  );

  useEffect(
    () => {
      setRoomHoverPoint(
        null
      );
    },
    [roomDrawModeId]
  );

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

  const boundaryStroke =
    4 / scale;

  const selectedBoundaryStroke =
    7 / scale;

  const boundaryHandleRadius =
    8 / scale;

  const boundaryColor =
    "#0891b2";

  function clampPoint(
    point: PixelPoint
  ): PixelPoint {
    return {
      x:
        Math.max(
          0,
          Math.min(
            originalWidth,
            point.x
          )
        ),

      y:
        Math.max(
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
      x:
        pointer.x /
        scale,

      y:
        pointer.y /
        scale,
    });
  }

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

  const boundaryPolygon =
    boundary?.polygon ?? [];

  const automaticValid =
    boundary
      ?.automaticAssessment
      ?.valid ?? false;

  const boundaryNeedsReview =
    !automaticValid &&
    boundary?.reviewStatus !==
      "confirmed";

  function addBoundaryDraftPointFromStage(
    stage: Konva.Stage
  ) {
    if (!boundaryDrawMode) {
      return;
    }

    const point =
      getOriginalPointer(
        stage
      );

    if (!point) {
      return;
    }

    onAddBoundaryDraftPoint(
      point
    );
  }

  function updateBoundaryHoverFromStage(
    stage: Konva.Stage
  ) {
    if (!boundaryDrawMode) {
      return;
    }

    const point =
      getOriginalPointer(
        stage
      );

    setBoundaryHoverPoint(
      point
    );
  }

  function addRoomDraftPointFromStage(
    stage: Konva.Stage
  ) {
    if (
      roomDrawModeId === null
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

    onAddRoomDraftPoint(
      point
    );
  }

  function updateRoomHoverFromStage(
    stage: Konva.Stage
  ) {
    if (
      roomDrawModeId === null
    ) {
      return;
    }

    const point =
      getOriginalPointer(
        stage
      );

    setRoomHoverPoint(
      point
    );
  }

  function renderBoundaryLine() {
    if (
      boundaryPolygon.length < 2
    ) {
      return null;
    }

    const editing =
      boundaryEditMode &&
      !boundaryDrawMode;

    return (
      <Line
        points={
          polygonToPoints(
            boundaryPolygon
          )
        }
        closed
        stroke={boundaryColor}
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
        opacity={
          boundaryDrawMode
            ? 0.35
            : 1
        }
        listening={
          editing &&
          !addMode
        }
        onDblClick={
          event => {
            if (!editing) {
              return;
            }

            event.cancelBubble =
              true;

            const stage =
              event.currentTarget.getStage();

            if (!stage) {
              return;
            }

            const point =
              getOriginalPointer(
                stage
              );

            if (!point) {
              return;
            }

            onInsertBoundaryPoint(
              closestSegmentIndex(
                boundaryPolygon,
                point
              ),
              point
            );
          }
        }
        onDblTap={
          event => {
            if (!editing) {
              return;
            }

            event.cancelBubble =
              true;

            const stage =
              event.currentTarget.getStage();

            if (!stage) {
              return;
            }

            const point =
              getOriginalPointer(
                stage
              );

            if (!point) {
              return;
            }

            onInsertBoundaryPoint(
              closestSegmentIndex(
                boundaryPolygon,
                point
              ),
              point
            );
          }
        }
      />
    );
  }

  function renderBoundaryHandles() {
    if (
      !boundaryEditMode ||
      addMode ||
      boundaryDrawMode
    ) {
      return null;
    }

    return boundaryPolygon.map(
      (
        point,
        pointIndex
      ) => (
        <Circle
          key={`boundary-point-${pointIndex}`}
          x={point.x}
          y={point.y}
          radius={boundaryHandleRadius}
          fill="#ffffff"
          stroke={boundaryColor}
          strokeWidth={3 / scale}
          draggable
          onDragEnd={
            event => {
              const next =
                clampPoint({
                  x:
                    event.currentTarget.x(),

                  y:
                    event.currentTarget.y(),
                });

              onMoveBoundaryPoint(
                pointIndex,
                next
              );
            }
          }
          onDblClick={
            event => {
              event.cancelBubble =
                true;

              if (
                boundaryPolygon.length <= 3
              ) {
                return;
              }

              onDeleteBoundaryPoint(
                pointIndex
              );
            }
          }
          onDblTap={
            event => {
              event.cancelBubble =
                true;

              if (
                boundaryPolygon.length <= 3
              ) {
                return;
              }

              onDeleteBoundaryPoint(
                pointIndex
              );
            }
          }
        />
      )
    );
  }

  function renderRoomHandles() {
    if (
      roomEditModeId === null ||
      roomDrawModeId !== null ||
      addMode ||
      boundaryEditMode ||
      boundaryDrawMode
    ) {
      return null;
    }

    const room =
      floorPlan
        .revision
        .rooms
        .find(
          current =>
            current.id ===
            roomEditModeId
        );

    if (!room) {
      return null;
    }

    return room.polygon.map(
      (
        point,
        pointIndex
      ) => (
        <Circle
          key={`room-edit-${room.id}-point-${pointIndex}`}
          x={point.x}
          y={point.y}
          radius={boundaryHandleRadius}
          fill="#ffffff"
          stroke="#15803d"
          strokeWidth={3 / scale}
          draggable
          onDragEnd={
            event => {
              const next =
                clampPoint({
                  x:
                    event.currentTarget.x(),

                  y:
                    event.currentTarget.y(),
                });

              onMoveRoomPoint(
                room.id,
                pointIndex,
                next
              );
            }
          }
          onDblClick={
            event => {
              event.cancelBubble =
                true;

              if (
                room.polygon.length <= 3
              ) {
                return;
              }

              onDeleteRoomPoint(
                room.id,
                pointIndex
              );
            }
          }
          onDblTap={
            event => {
              event.cancelBubble =
                true;

              if (
                room.polygon.length <= 3
              ) {
                return;
              }

              onDeleteRoomPoint(
                room.id,
                pointIndex
              );
            }
          }
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
          addMode ||
          boundaryEditMode ||
          boundaryDrawMode ||
          roomEditModeId !== null ||
          roomDrawModeId !== null
            ? "crosshair"
            : "default",
      }}
    >
      <Stage
        width={displayWidth}
        height={displayHeight}
        onMouseDown={
          event => {
            const stage =
              event.target.getStage();

            if (!stage) {
              return;
            }

            if (
              boundaryDrawMode
            ) {
              addBoundaryDraftPointFromStage(
                stage
              );

              return;
            }

            if (
              roomDrawModeId !== null
            ) {
              addRoomDraftPointFromStage(
                stage
              );

              return;
            }

            if (
              addMode
            ) {
              startDrawing(
                stage
              );

              return;
            }

            if (
              event.target === stage
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
            const stage =
              event.target.getStage();

            if (!stage) {
              return;
            }

            if (
              boundaryDrawMode
            ) {
              updateBoundaryHoverFromStage(
                stage
              );

              return;
            }

            if (
              roomDrawModeId !== null
            ) {
              updateRoomHoverFromStage(
                stage
              );

              return;
            }

            if (
              !addMode
            ) {
              return;
            }

            continueDrawing(
              stage
            );
          }
        }
        onMouseLeave={
          () => {
            if (
              boundaryDrawMode
            ) {
              setBoundaryHoverPoint(
                null
              );
            }

            if (
              roomDrawModeId !== null
            ) {
              setRoomHoverPoint(
                null
              );
            }
          }
        }
        onTouchStart={
          event => {
            const stage =
              event.target.getStage();

            if (!stage) {
              return;
            }

            if (
              boundaryDrawMode
            ) {
              addBoundaryDraftPointFromStage(
                stage
              );

              return;
            }

            if (
              roomDrawModeId !== null
            ) {
              addRoomDraftPointFromStage(
                stage
              );
            }
          }
        }
        onMouseUp={
          event => {
            if (!addMode) {
              return;
            }

            const stage =
              event.target.getStage();

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
          scaleX={scale}
          scaleY={scale}
        >
          <KonvaImage
            image={image}
            width={originalWidth}
            height={originalHeight}
            listening={false}
          />

          {renderBoundaryLine()}

          {
            boundaryDrawMode &&
            boundaryDraftPoints.length > 0 && (
              <>
                <Line
                  points={
                    polygonToPoints(
                      boundaryDraftPoints
                    )
                  }
                  closed={
                    boundaryDraftPoints.length >= 3
                  }
                  stroke={boundaryColor}
                  strokeWidth={selectedBoundaryStroke}
                  dash={[
                    12 / scale,
                    7 / scale,
                  ]}
                  fill={
                    boundaryDraftPoints.length >= 3
                      ? "rgba(8,145,178,0.12)"
                      : "rgba(0,0,0,0)"
                  }
                  listening={false}
                />

                {
                  boundaryHoverPoint &&
                  boundaryDraftPoints.length > 0 && (
                    <Line
                      points={[
                        boundaryDraftPoints[
                          boundaryDraftPoints.length - 1
                        ].x,

                        boundaryDraftPoints[
                          boundaryDraftPoints.length - 1
                        ].y,

                        boundaryHoverPoint.x,
                        boundaryHoverPoint.y,
                      ]}
                      stroke={boundaryColor}
                      strokeWidth={3 / scale}
                      dash={[
                        8 / scale,
                        6 / scale,
                      ]}
                      listening={false}
                    />
                  )
                }

                {
                  boundaryDraftPoints.map(
                    (
                      point,
                      index
                    ) => (
                      <Circle
                        key={`boundary-draft-${index}`}
                        x={point.x}
                        y={point.y}
                        radius={
                          index === 0
                            ? 10 / scale
                            : 7 / scale
                        }
                        fill={
                          index === 0
                            ? boundaryColor
                            : "#ffffff"
                        }
                        stroke={boundaryColor}
                        strokeWidth={3 / scale}
                        listening={false}
                      />
                    )
                  )
                }
              </>
            )
          }

          {
            roomDrawModeId !== null &&
            roomDraftPoints.length > 0 && (
              <>
                <Line
                  points={
                    polygonToPoints(
                      roomDraftPoints
                    )
                  }
                  closed={
                    roomDraftPoints.length >= 3
                  }
                  stroke="#15803d"
                  strokeWidth={selectedRoomStroke}
                  dash={[
                    12 / scale,
                    7 / scale,
                  ]}
                  fill={
                    roomDraftPoints.length >= 3
                      ? "rgba(22,163,74,0.18)"
                      : "rgba(0,0,0,0)"
                  }
                  listening={false}
                />

                {
                  roomHoverPoint &&
                  roomDraftPoints.length > 0 && (
                    <Line
                      points={[
                        roomDraftPoints[
                          roomDraftPoints.length - 1
                        ].x,

                        roomDraftPoints[
                          roomDraftPoints.length - 1
                        ].y,

                        roomHoverPoint.x,
                        roomHoverPoint.y,
                      ]}
                      stroke="#15803d"
                      strokeWidth={3 / scale}
                      dash={[
                        8 / scale,
                        6 / scale,
                      ]}
                      listening={false}
                    />
                  )
                }

                {
                  roomDraftPoints.map(
                    (
                      point,
                      index
                    ) => (
                      <Circle
                        key={`room-draft-${index}`}
                        x={point.x}
                        y={point.y}
                        radius={
                          index === 0
                            ? 10 / scale
                            : 7 / scale
                        }
                        fill={
                          index === 0
                            ? "#15803d"
                            : "#ffffff"
                        }
                        stroke="#15803d"
                        strokeWidth={3 / scale}
                        listening={false}
                      />
                    )
                  )
                }
              </>
            )
          }

          {
            floorPlan.revision.rooms.map(
              room => {
                const selected =
                  selectedType === "room" &&
                  selectedId === room.id;

                const editing =
                  roomEditModeId === room.id &&
                  roomDrawModeId === null;

                const outsideBoundary =
                  boundaryPolygon.length >= 3 &&
                  !polygonInsidePolygon(
                    room.polygon,
                    boundaryPolygon
                  );

                const roomListening =
                  !addMode &&
                  !boundaryEditMode &&
                  !boundaryDrawMode &&
                  roomDrawModeId === null &&
                  (
                    roomEditModeId === null ||
                    editing
                  );

                const labelWidth =
                  200 / scale;

                return (
                  <Group
                    key={`room-${room.id}`}
                    listening={roomListening}
                    draggable={
                      selected &&
                      roomEditModeId === null &&
                      roomDrawModeId === null &&
                      !addMode &&
                      !boundaryEditMode &&
                      !boundaryDrawMode
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
                        outsideBoundary
                          ? "#dc2626"
                          : selected
                            ? "#15803d"
                            : "#16a34a"
                      }
                      strokeWidth={
                        selected
                          ? selectedRoomStroke
                          : roomStroke
                      }
                      fill={
                        outsideBoundary
                          ? "rgba(220,38,38,0.16)"
                          : selected
                            ? "rgba(22,163,74,0.22)"
                            : "rgba(22,163,74,0.10)"
                      }
                      dash={
                        outsideBoundary
                          ? [
                              10 / scale,
                              6 / scale,
                            ]
                          : undefined
                      }
                      onDblClick={
                        event => {
                          if (!editing) {
                            return;
                          }

                          event.cancelBubble =
                            true;

                          const stage =
                            event.currentTarget.getStage();

                          if (!stage) {
                            return;
                          }

                          const point =
                            getOriginalPointer(
                              stage
                            );

                          if (!point) {
                            return;
                          }

                          onInsertRoomPoint(
                            room.id,
                            closestSegmentIndex(
                              room.polygon,
                              point
                            ),
                            point
                          );
                        }
                      }
                      onDblTap={
                        event => {
                          if (!editing) {
                            return;
                          }

                          event.cancelBubble =
                            true;

                          const stage =
                            event.currentTarget.getStage();

                          if (!stage) {
                            return;
                          }

                          const point =
                            getOriginalPointer(
                              stage
                            );

                          if (!point) {
                            return;
                          }

                          onInsertRoomPoint(
                            room.id,
                            closestSegmentIndex(
                              room.polygon,
                              point
                            ),
                            point
                          );
                        }
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
              }
            )
          }

          {
            floorPlan.revision.doors.map(
              door => {
                const selected =
                  selectedType === "door" &&
                  selectedId === door.id;

                return (
                  <Group
                    key={`door-${door.id}`}
                    listening={
                      !addMode &&
                      !boundaryEditMode &&
                      !boundaryDrawMode &&
                      roomEditModeId === null &&
                      roomDrawModeId === null
                    }
                    draggable={
                      selected &&
                      !addMode &&
                      !boundaryEditMode &&
                      !boundaryDrawMode &&
                      roomEditModeId === null &&
                      roomDrawModeId === null
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
                          ? "rgba(220,38,38,0.35)"
                          : "rgba(220,38,38,0.20)"
                      }
                    />
                  </Group>
                );
              }
            )
          }

          {
            floorPlan.revision.windows.map(
              window => {
                const selected =
                  selectedType === "window" &&
                  selectedId === window.id;

                return (
                  <Group
                    key={`window-${window.id}`}
                    listening={
                      !addMode &&
                      !boundaryEditMode &&
                      !boundaryDrawMode &&
                      roomEditModeId === null &&
                      roomDrawModeId === null
                    }
                    draggable={
                      selected &&
                      !addMode &&
                      !boundaryEditMode &&
                      !boundaryDrawMode &&
                      roomEditModeId === null &&
                      roomDrawModeId === null
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
                          ? "rgba(37,99,235,0.35)"
                          : "rgba(37,99,235,0.20)"
                      }
                    />
                  </Group>
                );
              }
            )
          }

          {
            floorPlan.revision.openings.map(
              opening => {
                const selected =
                  selectedType === "opening" &&
                  selectedId === opening.id;

                return (
                  <Group
                    key={`opening-${opening.id}`}
                    listening={
                      !addMode &&
                      !boundaryEditMode &&
                      !boundaryDrawMode &&
                      roomEditModeId === null &&
                      roomDrawModeId === null
                    }
                    draggable={
                      selected &&
                      !addMode &&
                      !boundaryEditMode &&
                      !boundaryDrawMode &&
                      roomEditModeId === null &&
                      roomDrawModeId === null
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
                          ? "rgba(234,88,12,0.35)"
                          : "rgba(234,88,12,0.20)"
                      }
                    />
                  </Group>
                );
              }
            )
          }

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
                stroke={previewColor()}
                strokeWidth={4 / scale}
                dash={[
                  12 / scale,
                  8 / scale,
                ]}
                fill="rgba(255,255,255,0.20)"
                listening={false}
              />
            )
          }

          {renderBoundaryHandles()}
          {renderRoomHandles()}
        </Layer>
      </Stage>
    </div>
  );
}

export default FloorPlanCanvas;