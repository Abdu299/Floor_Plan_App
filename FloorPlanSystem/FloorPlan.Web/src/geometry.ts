import type {
  PixelPoint,
  Room,
} from "./types";


const EPSILON = 1e-7;
const MERGE_EPSILON = 1e-4;


type Segment = {
  a: PixelPoint;
  b: PixelPoint;
};


function samePoint(
  first: PixelPoint,
  second: PixelPoint,
  tolerance = MERGE_EPSILON
): boolean {
  return (
    Math.abs(first.x - second.x) <= tolerance &&
    Math.abs(first.y - second.y) <= tolerance
  );
}


function cross(
  ax: number,
  ay: number,
  bx: number,
  by: number
): number {
  return ax * by - ay * bx;
}


function interpolate(
  start: PixelPoint,
  end: PixelPoint,
  t: number
): PixelPoint {
  return {
    x: start.x + (end.x - start.x) * t,
    y: start.y + (end.y - start.y) * t,
  };
}


function segmentLengthSquared(
  start: PixelPoint,
  end: PixelPoint
): number {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  return dx * dx + dy * dy;
}


function pointOnSegment(
  point: PixelPoint,
  start: PixelPoint,
  end: PixelPoint,
  tolerance = MERGE_EPSILON
): boolean {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const px = point.x - start.x;
  const py = point.y - start.y;

  const area = Math.abs(
    cross(dx, dy, px, py)
  );

  const scale = Math.max(
    1,
    Math.sqrt(dx * dx + dy * dy)
  );

  if (area > tolerance * scale) {
    return false;
  }

  const dot =
    (point.x - start.x) * (point.x - end.x) +
    (point.y - start.y) * (point.y - end.y);

  return dot <= tolerance * tolerance;
}


function parameterOnSegment(
  point: PixelPoint,
  start: PixelPoint,
  end: PixelPoint
): number {
  const dx = end.x - start.x;
  const dy = end.y - start.y;

  if (Math.abs(dx) >= Math.abs(dy)) {
    if (Math.abs(dx) <= EPSILON) {
      return 0;
    }

    return (point.x - start.x) / dx;
  }

  if (Math.abs(dy) <= EPSILON) {
    return 0;
  }

  return (point.y - start.y) / dy;
}


function addSplitValue(
  values: number[],
  value: number
) {
  const clamped = Math.max(
    0,
    Math.min(1, value)
  );

  if (
    !values.some(
      current =>
        Math.abs(current - clamped) <=
        EPSILON
    )
  ) {
    values.push(clamped);
  }
}


function addEdgeIntersections(
  firstStart: PixelPoint,
  firstEnd: PixelPoint,
  secondStart: PixelPoint,
  secondEnd: PixelPoint,
  firstSplits: number[],
  secondSplits: number[]
) {
  const rx = firstEnd.x - firstStart.x;
  const ry = firstEnd.y - firstStart.y;
  const sx = secondEnd.x - secondStart.x;
  const sy = secondEnd.y - secondStart.y;

  const qpx = secondStart.x - firstStart.x;
  const qpy = secondStart.y - firstStart.y;

  const denominator = cross(
    rx,
    ry,
    sx,
    sy
  );

  const qpr = cross(
    qpx,
    qpy,
    rx,
    ry
  );

  if (Math.abs(denominator) > EPSILON) {
    const t =
      cross(qpx, qpy, sx, sy) /
      denominator;

    const u =
      cross(qpx, qpy, rx, ry) /
      denominator;

    if (
      t >= -EPSILON &&
      t <= 1 + EPSILON &&
      u >= -EPSILON &&
      u <= 1 + EPSILON
    ) {
      addSplitValue(
        firstSplits,
        t
      );

      addSplitValue(
        secondSplits,
        u
      );
    }

    return;
  }

  if (Math.abs(qpr) > EPSILON) {
    return;
  }

  // Collinear segments. Split at every endpoint that lies on the
  // opposite segment so overlapping boundary pieces are preserved.
  if (
    pointOnSegment(
      secondStart,
      firstStart,
      firstEnd
    )
  ) {
    addSplitValue(
      firstSplits,
      parameterOnSegment(
        secondStart,
        firstStart,
        firstEnd
      )
    );
  }

  if (
    pointOnSegment(
      secondEnd,
      firstStart,
      firstEnd
    )
  ) {
    addSplitValue(
      firstSplits,
      parameterOnSegment(
        secondEnd,
        firstStart,
        firstEnd
      )
    );
  }

  if (
    pointOnSegment(
      firstStart,
      secondStart,
      secondEnd
    )
  ) {
    addSplitValue(
      secondSplits,
      parameterOnSegment(
        firstStart,
        secondStart,
        secondEnd
      )
    );
  }

  if (
    pointOnSegment(
      firstEnd,
      secondStart,
      secondEnd
    )
  ) {
    addSplitValue(
      secondSplits,
      parameterOnSegment(
        firstEnd,
        secondStart,
        secondEnd
      )
    );
  }
}


export function normalizePolygon(
  polygon: PixelPoint[]
): PixelPoint[] {
  const result: PixelPoint[] = [];

  for (const point of polygon) {
    if (
      !Number.isFinite(point.x) ||
      !Number.isFinite(point.y)
    ) {
      continue;
    }

    const copy = {
      x: point.x,
      y: point.y,
    };

    const previous =
      result[result.length - 1];

    if (
      previous &&
      samePoint(previous, copy)
    ) {
      continue;
    }

    result.push(copy);
  }

  if (
    result.length > 1 &&
    samePoint(
      result[0],
      result[result.length - 1]
    )
  ) {
    result.pop();
  }

  if (result.length < 3) {
    return result;
  }

  // Remove points that are exactly on the straight segment between their
  // neighbours. This keeps clipping output compact and easier to edit.
  let changed = true;

  while (
    changed &&
    result.length > 3
  ) {
    changed = false;

    for (
      let index = 0;
      index < result.length;
      index++
    ) {
      const previous =
        result[
          (index - 1 + result.length) %
          result.length
        ];

      const current =
        result[index];

      const next =
        result[
          (index + 1) %
          result.length
        ];

      if (
        pointOnSegment(
          current,
          previous,
          next
        )
      ) {
        result.splice(index, 1);
        changed = true;
        break;
      }
    }
  }

  return result;
}


export function polygonSignedArea(
  polygon: PixelPoint[]
): number {
  if (polygon.length < 3) {
    return 0;
  }

  let twiceArea = 0;

  for (
    let index = 0;
    index < polygon.length;
    index++
  ) {
    const next =
      (index + 1) % polygon.length;

    twiceArea +=
      polygon[index].x * polygon[next].y -
      polygon[next].x * polygon[index].y;
  }

  return twiceArea / 2;
}


export function polygonArea(
  polygon: PixelPoint[]
): number {
  return Math.abs(
    polygonSignedArea(polygon)
  );
}


export function polygonCentroid(
  polygon: PixelPoint[]
): PixelPoint {
  if (polygon.length === 0) {
    return {
      x: 0,
      y: 0,
    };
  }

  const signedArea =
    polygonSignedArea(polygon);

  if (Math.abs(signedArea) <= EPSILON) {
    const total = polygon.reduce(
      (sum, point) => ({
        x: sum.x + point.x,
        y: sum.y + point.y,
      }),
      {
        x: 0,
        y: 0,
      }
    );

    return {
      x: total.x / polygon.length,
      y: total.y / polygon.length,
    };
  }

  let x = 0;
  let y = 0;

  for (
    let index = 0;
    index < polygon.length;
    index++
  ) {
    const next =
      (index + 1) % polygon.length;

    const factor =
      polygon[index].x * polygon[next].y -
      polygon[next].x * polygon[index].y;

    x +=
      (polygon[index].x + polygon[next].x) *
      factor;

    y +=
      (polygon[index].y + polygon[next].y) *
      factor;
  }

  const divisor =
    6 * signedArea;

  return {
    x: x / divisor,
    y: y / divisor,
  };
}


export function pointInPolygonInclusive(
  point: PixelPoint,
  polygon: PixelPoint[]
): boolean {
  if (polygon.length < 3) {
    return false;
  }

  for (
    let index = 0;
    index < polygon.length;
    index++
  ) {
    const next =
      (index + 1) % polygon.length;

    if (
      pointOnSegment(
        point,
        polygon[index],
        polygon[next]
      )
    ) {
      return true;
    }
  }

  let inside = false;

  for (
    let index = 0,
    previous = polygon.length - 1;
    index < polygon.length;
    previous = index++
  ) {
    const currentPoint =
      polygon[index];

    const previousPoint =
      polygon[previous];

    const crossesRay =
      (
        currentPoint.y > point.y
      ) !== (
        previousPoint.y > point.y
      );

    if (!crossesRay) {
      continue;
    }

    const xAtY =
      (
        (previousPoint.x - currentPoint.x) *
        (point.y - currentPoint.y)
      ) /
      (previousPoint.y - currentPoint.y) +
      currentPoint.x;

    if (point.x < xAtY) {
      inside = !inside;
    }
  }

  return inside;
}


function splitValuesForEdgeAgainstPolygon(
  start: PixelPoint,
  end: PixelPoint,
  polygon: PixelPoint[]
): number[] {
  const splits = [0, 1];

  for (
    let index = 0;
    index < polygon.length;
    index++
  ) {
    const next =
      (index + 1) % polygon.length;

    const otherSplits = [0, 1];

    addEdgeIntersections(
      start,
      end,
      polygon[index],
      polygon[next],
      splits,
      otherSplits
    );
  }

  return splits.sort(
    (first, second) => first - second
  );
}


export function polygonInsidePolygon(
  inner: PixelPoint[],
  outer: PixelPoint[]
): boolean {
  const normalizedInner =
    normalizePolygon(inner);

  const normalizedOuter =
    normalizePolygon(outer);

  if (
    normalizedInner.length < 3 ||
    normalizedOuter.length < 3
  ) {
    return false;
  }

  for (const point of normalizedInner) {
    if (
      !pointInPolygonInclusive(
        point,
        normalizedOuter
      )
    ) {
      return false;
    }
  }

  // Vertex-only checks are not enough for a concave outer polygon. An edge
  // can connect two inside vertices while crossing an outside bay. Split each
  // inner edge at every boundary intersection and test every resulting piece.
  for (
    let index = 0;
    index < normalizedInner.length;
    index++
  ) {
    const next =
      (index + 1) % normalizedInner.length;

    const start =
      normalizedInner[index];

    const end =
      normalizedInner[next];

    const splits =
      splitValuesForEdgeAgainstPolygon(
        start,
        end,
        normalizedOuter
      );

    for (
      let splitIndex = 0;
      splitIndex < splits.length - 1;
      splitIndex++
    ) {
      const first = splits[splitIndex];
      const second = splits[splitIndex + 1];

      if (
        second - first <= EPSILON
      ) {
        continue;
      }

      const midpoint =
        interpolate(
          start,
          end,
          (first + second) / 2
        );

      if (
        !pointInPolygonInclusive(
          midpoint,
          normalizedOuter
        )
      ) {
        return false;
      }
    }
  }

  return true;
}


function pointKey(
  point: PixelPoint
): string {
  return `${Math.round(point.x / MERGE_EPSILON)}:${Math.round(point.y / MERGE_EPSILON)}`;
}


function buildBoundarySegments(
  source: PixelPoint[],
  clip: PixelPoint[],
  sourceSplits: number[][]
): Segment[] {
  const segments: Segment[] = [];

  for (
    let index = 0;
    index < source.length;
    index++
  ) {
    const next =
      (index + 1) % source.length;

    const start = source[index];
    const end = source[next];

    const splits = [
      ...sourceSplits[index],
    ].sort(
      (first, second) => first - second
    );

    for (
      let splitIndex = 0;
      splitIndex < splits.length - 1;
      splitIndex++
    ) {
      const first = splits[splitIndex];
      const second = splits[splitIndex + 1];

      if (
        second - first <= EPSILON
      ) {
        continue;
      }

      const a =
        interpolate(
          start,
          end,
          first
        );

      const b =
        interpolate(
          start,
          end,
          second
        );

      if (
        segmentLengthSquared(a, b) <=
        EPSILON * EPSILON
      ) {
        continue;
      }

      const midpoint =
        interpolate(a, b, 0.5);

      if (
        pointInPolygonInclusive(
          midpoint,
          clip
        )
      ) {
        segments.push({ a, b });
      }
    }
  }

  return segments;
}


function uniqueSegments(
  segments: Segment[]
): Segment[] {
  const seen =
    new Set<string>();

  const result: Segment[] = [];

  for (const segment of segments) {
    const firstKey =
      pointKey(segment.a);

    const secondKey =
      pointKey(segment.b);

    if (firstKey === secondKey) {
      continue;
    }

    const edgeKey =
      firstKey < secondKey
        ? `${firstKey}|${secondKey}`
        : `${secondKey}|${firstKey}`;

    if (seen.has(edgeKey)) {
      continue;
    }

    seen.add(edgeKey);
    result.push(segment);
  }

  return result;
}


function segmentsToPolygons(
  segments: Segment[]
): PixelPoint[][] {
  const unique =
    uniqueSegments(segments);

  if (unique.length === 0) {
    return [];
  }

  const vertices =
    new Map<string, PixelPoint>();

  const adjacency =
    new Map<string, number[]>();

  const edges = unique.map(
    segment => {
      const aKey = pointKey(segment.a);
      const bKey = pointKey(segment.b);

      if (!vertices.has(aKey)) {
        vertices.set(aKey, segment.a);
      }

      if (!vertices.has(bKey)) {
        vertices.set(bKey, segment.b);
      }

      return {
        aKey,
        bKey,
      };
    }
  );

  edges.forEach(
    (edge, edgeIndex) => {
      const aList =
        adjacency.get(edge.aKey) ?? [];

      aList.push(edgeIndex);
      adjacency.set(edge.aKey, aList);

      const bList =
        adjacency.get(edge.bKey) ?? [];

      bList.push(edgeIndex);
      adjacency.set(edge.bKey, bList);
    }
  );

  const used =
    new Set<number>();

  const polygons: PixelPoint[][] = [];

  for (
    let startEdgeIndex = 0;
    startEdgeIndex < edges.length;
    startEdgeIndex++
  ) {
    if (used.has(startEdgeIndex)) {
      continue;
    }

    const startEdge =
      edges[startEdgeIndex];

    const startKey =
      startEdge.aKey;

    let previousKey =
      startEdge.aKey;

    let currentKey =
      startEdge.bKey;

    const pathKeys = [
      startKey,
      currentKey,
    ];

    used.add(startEdgeIndex);

    let closed =
      currentKey === startKey;

    let guard = 0;

    while (
      !closed &&
      guard < edges.length * 4
    ) {
      guard++;

      const candidateEdges =
        (adjacency.get(currentKey) ?? [])
          .filter(
            edgeIndex =>
              !used.has(edgeIndex)
          );

      if (candidateEdges.length === 0) {
        break;
      }

      let chosenEdgeIndex =
        candidateEdges[0];

      if (candidateEdges.length > 1) {
        // Prefer continuing to a new vertex rather than immediately
        // backtracking. In valid simple polygon intersections each boundary
        // vertex normally has degree 2, so this only handles touch cases.
        const nonBacktracking =
          candidateEdges.find(
            edgeIndex => {
              const edge =
                edges[edgeIndex];

              const otherKey =
                edge.aKey === currentKey
                  ? edge.bKey
                  : edge.aKey;

              return otherKey !== previousKey;
            }
          );

        if (
          nonBacktracking !== undefined
        ) {
          chosenEdgeIndex =
            nonBacktracking;
        }
      }

      const chosen =
        edges[chosenEdgeIndex];

      const nextKey =
        chosen.aKey === currentKey
          ? chosen.bKey
          : chosen.aKey;

      used.add(chosenEdgeIndex);

      previousKey = currentKey;
      currentKey = nextKey;

      if (currentKey === startKey) {
        closed = true;
        break;
      }

      pathKeys.push(currentKey);
    }

    if (!closed) {
      continue;
    }

    const polygon =
      normalizePolygon(
        pathKeys
          .map(key => vertices.get(key))
          .filter(
            (point): point is PixelPoint =>
              point !== undefined
          )
      );

    if (
      polygon.length >= 3 &&
      polygonArea(polygon) > EPSILON
    ) {
      polygons.push(polygon);
    }
  }

  return polygons;
}


export function intersectPolygons(
  firstPolygon: PixelPoint[],
  secondPolygon: PixelPoint[]
): PixelPoint[][] {
  const first =
    normalizePolygon(firstPolygon);

  const second =
    normalizePolygon(secondPolygon);

  if (
    first.length < 3 ||
    second.length < 3
  ) {
    return [];
  }

  const firstSplits =
    first.map(() => [0, 1]);

  const secondSplits =
    second.map(() => [0, 1]);

  for (
    let firstIndex = 0;
    firstIndex < first.length;
    firstIndex++
  ) {
    const firstNext =
      (firstIndex + 1) % first.length;

    for (
      let secondIndex = 0;
      secondIndex < second.length;
      secondIndex++
    ) {
      const secondNext =
        (secondIndex + 1) % second.length;

      addEdgeIntersections(
        first[firstIndex],
        first[firstNext],
        second[secondIndex],
        second[secondNext],
        firstSplits[firstIndex],
        secondSplits[secondIndex]
      );
    }
  }

  const segments = [
    ...buildBoundarySegments(
      first,
      second,
      firstSplits
    ),
    ...buildBoundarySegments(
      second,
      first,
      secondSplits
    ),
  ];

  const polygons =
    segmentsToPolygons(segments);

  if (polygons.length > 0) {
    return polygons;
  }

  // Fallbacks for pure containment without boundary intersections.
  if (
    polygonInsidePolygon(
      first,
      second
    )
  ) {
    return [first];
  }

  if (
    polygonInsidePolygon(
      second,
      first
    )
  ) {
    return [second];
  }

  return [];
}


export function clipPolygonToPolygon(
  subject: PixelPoint[],
  clip: PixelPoint[]
): PixelPoint[] | null {
  const intersections =
    intersectPolygons(
      subject,
      clip
    );

  if (intersections.length === 0) {
    return null;
  }

  return intersections.reduce(
    (largest, polygon) =>
      polygonArea(polygon) >
      polygonArea(largest)
        ? polygon
        : largest
  );
}


export function roomWithPolygon(
  room: Room,
  polygon: PixelPoint[]
): Room {
  const normalized =
    normalizePolygon(polygon);

  return {
    ...room,
    polygon: normalized,
    centroid:
      polygonCentroid(normalized),
    areaPixels:
      polygonArea(normalized),
  };
}


export function constrainRoomToUsableBoundary(
  room: Room,
  usablePolygon: PixelPoint[]
): Room {
  const normalizedUsable =
    normalizePolygon(usablePolygon);

  if (normalizedUsable.length < 3) {
    return roomWithPolygon(
      room,
      room.polygon
    );
  }

  if (
    polygonInsidePolygon(
      room.polygon,
      normalizedUsable
    )
  ) {
    return roomWithPolygon(
      room,
      room.polygon
    );
  }

  const clipped =
    clipPolygonToPolygon(
      room.polygon,
      normalizedUsable
    );

  // A completely outside room is intentionally kept instead of silently
  // deleting it. Save validation will flag it so the user can fix/redraw it.
  if (
    !clipped ||
    clipped.length < 3 ||
    polygonArea(clipped) <= EPSILON
  ) {
    return roomWithPolygon(
      room,
      room.polygon
    );
  }

  return roomWithPolygon(
    room,
    clipped
  );
}
