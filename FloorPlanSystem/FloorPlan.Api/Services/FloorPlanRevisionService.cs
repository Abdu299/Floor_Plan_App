using System.Text.Json;
using FloorPlan.Api.Data;
using FloorPlan.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace FloorPlan.Api.Services;


public class FloorPlanRevisionService
{
    private static readonly JsonSerializerOptions BoundaryJsonOptions =
        new(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };


    private readonly AppDbContext _db;

    private readonly FloorPlanValidationService
        _validationService;


    public FloorPlanRevisionService(
        AppDbContext db,
        FloorPlanValidationService validationService)
    {
        _db =
            db;

        _validationService =
            validationService;
    }


    // =========================================================
    // SAVE USER REVISION
    // =========================================================

    public async Task<SavedRevisionResponse>
        SaveUserRevisionAsync(
            int floorPlanId,
            SaveRevisionRequest request,
            CancellationToken cancellationToken = default)
    {
        // =====================================================
        // FLOOR PLAN
        // =====================================================

        var floorPlan =
            await _db.FloorPlans
                .AsNoTracking()

                .FirstOrDefaultAsync(
                    x =>
                        x.Id ==
                        floorPlanId,

                    cancellationToken
                );


        if (
            floorPlan == null
        )
        {
            throw new KeyNotFoundException(
                $"Floor plan {floorPlanId} was not found."
            );
        }


        // =====================================================
        // BASE REVISION
        // =====================================================

        var baseRevision =
            await _db.FloorPlanRevisions
                .AsNoTracking()

                .FirstOrDefaultAsync(
                    x =>
                        x.Id ==
                        request.BasedOnRevisionId
                        &&
                        x.FloorPlanId ==
                        floorPlanId,

                    cancellationToken
                );


        if (
            baseRevision == null
        )
        {
            throw new InvalidOperationException(
                "The base revision does not exist " +
                "or does not belong to this floor plan."
            );
        }


        // =====================================================
        // NORMALIZE BOUNDARY PROVENANCE
        // =====================================================
        //
        // Do not rely only on the frontend to tell us whether the
        // boundary geometry changed. The server compares it with the
        // base revision and marks the current boundary as user-edited
        // when necessary.
        // =====================================================

        NormalizeBoundaryForUserRevision(
            request.BuildingBoundary,
            baseRevision.BuildingBoundaryJson
        );


        // =====================================================
        // BASIC STRUCTURAL VALIDATION
        // =====================================================

        ValidateRevisionStructure(
            request,
            floorPlan
        );


        // =====================================================
        // FLOOR PLAN VALIDATION
        //
        // IMPORTANT:
        // We calculate this from the CURRENT edited data.
        //
        // We DO NOT trust request.Validation because it may
        // contain the old AI validation result.
        // =====================================================

        var saveValidation =
            _validationService.Validate(
                request
            );


        if (
            !saveValidation.CanSave
        )
        {
            var message =
                "Floor plan cannot be saved:\n- "
                +
                string.Join(
                    "\n- ",
                    saveValidation.Errors
                );


            throw new InvalidOperationException(
                message
            );
        }


        // =====================================================
        // PRESERVE ROOM AI CONFIDENCE
        // =====================================================

        var baseRoomConfidences =
            await _db.Rooms
                .AsNoTracking()

                .Where(
                    x =>
                        x.FloorPlanRevisionId ==
                        baseRevision.Id
                )

                .ToDictionaryAsync(
                    x =>
                        x.SourceElementId,

                    x =>
                        x.Confidence,

                    cancellationToken
                );


        // =====================================================
        // PRESERVE DOOR AI CONFIDENCE
        // =====================================================

        var baseDoorConfidences =
            await _db.Doors
                .AsNoTracking()

                .Where(
                    x =>
                        x.FloorPlanRevisionId ==
                        baseRevision.Id
                )

                .ToDictionaryAsync(
                    x =>
                        x.SourceElementId,

                    x =>
                        x.Confidence,

                    cancellationToken
                );


        // =====================================================
        // NEXT REVISION NUMBER
        // =====================================================

        var latestRevisionNumber =
            await _db.FloorPlanRevisions

                .Where(
                    x =>
                        x.FloorPlanId ==
                        floorPlanId
                )

                .MaxAsync(
                    x =>
                        (int?)
                        x.RevisionNumber,

                    cancellationToken
                )
                ?? 0;


        var nextRevisionNumber =
            latestRevisionNumber + 1;


        // =====================================================
        // TRANSACTION
        // =====================================================

        await using var transaction =
            await _db.Database
                .BeginTransactionAsync(
                    cancellationToken
                );


        try
        {
            // =================================================
            // CREATE REVISION
            // =================================================

            var revision =
                new FloorPlanRevisionEntity
                {
                    FloorPlanId =
                        floorPlanId,

                    RevisionNumber =
                        nextRevisionNumber,

                    Source =
                        RevisionSource.User,

                    Status =
                        RevisionStatus.Draft,

                    BasedOnRevisionId =
                        baseRevision.Id,


                    // =========================================
                    // IMPORTANT:
                    //
                    // These values are recalculated from the
                    // current corrected floor plan.
                    // =========================================

                    Valid =
                        saveValidation.Valid,

                    HasBathroom =
                        saveValidation.HasBathroom,

                    HasKitchen =
                        saveValidation.HasKitchen,


                    BuildingBoundaryJson =
                        JsonSerializer.Serialize(
                            request.BuildingBoundary,
                            BoundaryJsonOptions
                        ),


                    CreatedAtUtc =
                        DateTime.UtcNow
                };


            _db.FloorPlanRevisions.Add(
                revision
            );


            await _db.SaveChangesAsync(
                cancellationToken
            );


            // =================================================
            // ROOMS
            // =================================================

            var roomMap =
                new Dictionary<
                    int,
                    RoomEntity
                >();


            foreach (
                var sourceRoom
                in request.Rooms
            )
            {
                baseRoomConfidences
                    .TryGetValue(
                        sourceRoom.Id,
                        out var originalConfidence
                    );


                var room =
                    new RoomEntity
                    {
                        FloorPlanRevisionId =
                            revision.Id,

                        SourceElementId =
                            sourceRoom.Id,

                        Name =
                            sourceRoom.Name,

                        Confidence =
                            originalConfidence,


                        // =====================================
                        // REAL AREA
                        // =====================================

                        AreaSquareMetres =
                            sourceRoom
                                .AreaSquareMetres,


                        PolygonJson =
                            JsonSerializer.Serialize(
                                sourceRoom.Polygon
                            ),

                        CentroidX =
                            sourceRoom
                                .Centroid
                                .X,

                        CentroidY =
                            sourceRoom
                                .Centroid
                                .Y,

                        AreaPixels =
                            sourceRoom
                                .AreaPixels
                    };


                _db.Rooms.Add(
                    room
                );


                roomMap[
                    sourceRoom.Id
                ] =
                    room;
            }


            // Save first so the rooms receive
            // their database IDs.

            await _db.SaveChangesAsync(
                cancellationToken
            );


            // =================================================
            // DOORS
            // =================================================

            foreach (
                var sourceDoor
                in request.Doors
            )
            {
                var room1 =
                    GetRoom(
                        roomMap,
                        sourceDoor.Room1.Id,
                        $"Door {sourceDoor.Id}"
                    );


                RoomEntity? room2 =
                    sourceDoor.Room2 is null
                        ? null
                        : GetRoom(
                            roomMap,
                            sourceDoor.Room2.Id,
                            $"Door {sourceDoor.Id}"
                        );


                baseDoorConfidences
                    .TryGetValue(
                        sourceDoor.Id,
                        out var originalConfidence
                    );


                var door =
                    new DoorEntity
                    {
                        FloorPlanRevisionId =
                            revision.Id,

                        SourceElementId =
                            sourceDoor.Id,

                        PolygonJson =
                            JsonSerializer.Serialize(
                                sourceDoor.Polygon
                            ),

                        Confidence =
                            originalConfidence,


                        BboxX1 =
                            sourceDoor
                                .BoundingBox
                                ?.X1,

                        BboxY1 =
                            sourceDoor
                                .BoundingBox
                                ?.Y1,

                        BboxX2 =
                            sourceDoor
                                .BoundingBox
                                ?.X2,

                        BboxY2 =
                            sourceDoor
                                .BoundingBox
                                ?.Y2,


                        Room1Id =
                            room1.Id,

                        // null means Room1 <-> Outside.
                        Room2Id =
                            room2?.Id
                    };


                _db.Doors.Add(
                    door
                );
            }


            // =================================================
            // WINDOWS
            // =================================================

            foreach (
                var sourceWindow
                in request.Windows
            )
            {
                var window =
                    new WindowEntity
                    {
                        FloorPlanRevisionId =
                            revision.Id,

                        SourceElementId =
                            sourceWindow.Id,

                        PolygonJson =
                            JsonSerializer.Serialize(
                                sourceWindow.Polygon
                            ),


                        BboxX1 =
                            sourceWindow
                                .BoundingBox
                                ?.X1,

                        BboxY1 =
                            sourceWindow
                                .BoundingBox
                                ?.Y1,

                        BboxX2 =
                            sourceWindow
                                .BoundingBox
                                ?.X2,

                        BboxY2 =
                            sourceWindow
                                .BoundingBox
                                ?.Y2
                    };


                _db.Windows.Add(
                    window
                );
            }


            // =================================================
            // OPENINGS
            // =================================================

            foreach (
                var sourceOpening
                in request.Openings
            )
            {
                var room1 =
                    GetRoom(
                        roomMap,
                        sourceOpening.Room1.Id,
                        $"Opening {sourceOpening.Id}"
                    );


                var room2 =
                    GetRoom(
                        roomMap,
                        sourceOpening.Room2.Id,
                        $"Opening {sourceOpening.Id}"
                    );


                var opening =
                    new OpeningEntity
                    {
                        FloorPlanRevisionId =
                            revision.Id,

                        SourceElementId =
                            sourceOpening.Id,

                        PolygonJson =
                            JsonSerializer.Serialize(
                                sourceOpening.Polygon
                            ),


                        BboxX1 =
                            sourceOpening
                                .BoundingBox
                                ?.X1,

                        BboxY1 =
                            sourceOpening
                                .BoundingBox
                                ?.Y1,

                        BboxX2 =
                            sourceOpening
                                .BoundingBox
                                ?.X2,

                        BboxY2 =
                            sourceOpening
                                .BoundingBox
                                ?.Y2,


                        Room1Id =
                            room1.Id,

                        Room2Id =
                            room2.Id
                    };


                _db.Openings.Add(
                    opening
                );
            }


            // =================================================
            // SAVE
            // =================================================

            await _db.SaveChangesAsync(
                cancellationToken
            );


            await transaction.CommitAsync(
                cancellationToken
            );


            // =================================================
            // RESPONSE
            // =================================================

            return new SavedRevisionResponse
            {
                FloorPlanId =
                    floorPlanId,

                RevisionId =
                    revision.Id,

                RevisionNumber =
                    revision.RevisionNumber,

                BasedOnRevisionId =
                    baseRevision.Id,

                Source =
                    "user",

                Status =
                    "draft",

                CreatedAtUtc =
                    revision.CreatedAtUtc
            };
        }
        catch
        {
            await transaction.RollbackAsync(
                cancellationToken
            );


            throw;
        }
    }


    // =========================================================
    // GET ROOM
    // =========================================================

    private static RoomEntity GetRoom(
        Dictionary<int, RoomEntity> rooms,
        int sourceRoomId,
        string owner)
    {
        if (
            !rooms.TryGetValue(
                sourceRoomId,
                out var room
            )
        )
        {
            throw new InvalidOperationException(
                $"{owner} references room " +
                $"{sourceRoomId}, but that room " +
                "does not exist."
            );
        }


        return room;
    }


    // =========================================================
    // STRUCTURAL VALIDATION
    //
    // This checks IDs, polygons, coordinates,
    // door relationships, etc.
    //
    // Semantic floor-plan validation is handled
    // by FloorPlanValidationService.
    // =========================================================

    private static void ValidateRevisionStructure(
        SaveRevisionRequest request,
        FloorPlanEntity floorPlan)
    {
        EnsureUniqueIds(
            request.Rooms.Select(
                x => x.Id
            ),
            "room"
        );


        EnsureUniqueIds(
            request.Doors.Select(
                x => x.Id
            ),
            "door"
        );


        EnsureUniqueIds(
            request.Windows.Select(
                x => x.Id
            ),
            "window"
        );


        EnsureUniqueIds(
            request.Openings.Select(
                x => x.Id
            ),
            "opening"
        );


        // =====================================================
        // ROOMS
        // =====================================================

        foreach (
            var room
            in request.Rooms
        )
        {
            ValidatePolygon(
                room.Polygon,
                floorPlan,
                $"Room {room.Id}"
            );
        }


        // =====================================================
        // DOORS
        // =====================================================

        foreach (
            var door
            in request.Doors
        )
        {
            ValidatePolygon(
                door.Polygon,
                floorPlan,
                $"Door {door.Id}"
            );


            // room2 may be null for an exterior door.
            if (
                door.Room2 is not null
                &&
                door.Room1.Id ==
                door.Room2.Id
            )
            {
                throw new InvalidOperationException(
                    $"Door {door.Id} cannot connect a room to itself."
                );
            }
        }


        // =====================================================
        // WINDOWS
        // =====================================================

        foreach (
            var window
            in request.Windows
        )
        {
            ValidatePolygon(
                window.Polygon,
                floorPlan,
                $"Window {window.Id}"
            );
        }


        // =====================================================
        // OPENINGS
        // =====================================================

        foreach (
            var opening
            in request.Openings
        )
        {
            ValidatePolygon(
                opening.Polygon,
                floorPlan,
                $"Opening {opening.Id}"
            );


            if (
                opening.Room1.Id ==
                opening.Room2.Id
            )
            {
                throw new InvalidOperationException(
                    $"Opening {opening.Id} cannot connect a room to itself."
                );
            }
        }


        // =====================================================
        // BUILDING BOUNDARY
        // =====================================================
        //
        // An uncertain AI assessment does NOT prevent saving.
        // We only validate geometry when polygon coordinates exist.
        // =====================================================

        if (
            request.BuildingBoundary
                .OuterPolygon
                .Count > 0
        )
        {
            ValidatePolygon(
                request.BuildingBoundary.OuterPolygon,
                floorPlan,
                "Building outer boundary"
            );
        }


        if (
            request.BuildingBoundary
                .UsablePolygon
                .Count > 0
        )
        {
            ValidatePolygon(
                request.BuildingBoundary.UsablePolygon,
                floorPlan,
                "Building usable boundary"
            );
        }


        if (
            string.Equals(
                request.BuildingBoundary.ReviewStatus,
                "confirmed",
                StringComparison.OrdinalIgnoreCase
            )
            &&
            (
                request.BuildingBoundary.OuterPolygon.Count < 3
                ||
                request.BuildingBoundary.UsablePolygon.Count < 3
            )
        )
        {
            throw new InvalidOperationException(
                "A confirmed building boundary must contain both " +
                "outer and usable polygons."
            );
        }
    }


    // =========================================================
    // BOUNDARY PROVENANCE
    // =========================================================

    private static void NormalizeBoundaryForUserRevision(
        BuildingBoundaryDetection current,
        string? baseBoundaryJson)
    {
        var baseBoundary =
            DeserializeBoundary(
                baseBoundaryJson
            );


        var geometryChanged =
            !PolygonsEqual(
                current.OuterPolygon,
                baseBoundary.OuterPolygon
            )
            ||
            !PolygonsEqual(
                current.UsablePolygon,
                baseBoundary.UsablePolygon
            );


        if (geometryChanged)
        {
            current.Source =
                "user";

            current.IsUserEdited =
                true;


            if (
                !string.Equals(
                    current.ReviewStatus,
                    "confirmed",
                    StringComparison.OrdinalIgnoreCase
                )
            )
            {
                current.ReviewStatus =
                    "edited";
            }
        }
        else
        {
            if (
                string.IsNullOrWhiteSpace(
                    current.Source
                )
            )
            {
                current.Source =
                    baseBoundary.Source;
            }


            // Preserve the fact that an already edited boundary remains
            // user-edited in later revisions even when this save did not
            // move another point.
            current.IsUserEdited =
                current.IsUserEdited
                ||
                baseBoundary.IsUserEdited;


            if (
                current.IsUserEdited
                &&
                string.Equals(
                    current.Source,
                    "ai",
                    StringComparison.OrdinalIgnoreCase
                )
            )
            {
                current.Source =
                    "user";
            }
        }


        if (
            string.IsNullOrWhiteSpace(
                current.ReviewStatus
            )
        )
        {
            current.ReviewStatus =
                "unreviewed";
        }


        if (
            string.IsNullOrWhiteSpace(
                current.Source
            )
        )
        {
            current.Source =
                "ai";
        }
    }


    private static BuildingBoundaryDetection
        DeserializeBoundary(
            string? json)
    {
        if (
            string.IsNullOrWhiteSpace(
                json
            )
        )
        {
            return new BuildingBoundaryDetection();
        }


        try
        {
            return JsonSerializer.Deserialize<
                BuildingBoundaryDetection
            >(
                json,
                BoundaryJsonOptions
            )
            ?? new BuildingBoundaryDetection();
        }
        catch
        {
            return new BuildingBoundaryDetection();
        }
    }


    private static bool PolygonsEqual(
        IReadOnlyList<PixelPoint> first,
        IReadOnlyList<PixelPoint> second)
    {
        if (
            first.Count !=
            second.Count
        )
        {
            return false;
        }


        const double tolerance =
            0.000001;


        for (
            var index = 0;
            index < first.Count;
            index++
        )
        {
            if (
                Math.Abs(
                    first[index].X -
                    second[index].X
                )
                > tolerance
                ||
                Math.Abs(
                    first[index].Y -
                    second[index].Y
                )
                > tolerance
            )
            {
                return false;
            }
        }


        return true;
    }


    // =========================================================
    // UNIQUE IDS
    // =========================================================

    private static void EnsureUniqueIds(
        IEnumerable<int> ids,
        string elementName)
    {
        var list =
            ids.ToList();


        if (
            list.Count !=
            list.Distinct().Count()
        )
        {
            throw new InvalidOperationException(
                $"Duplicate {elementName} IDs detected."
            );
        }
    }


    // =========================================================
    // POLYGON VALIDATION
    // =========================================================

    private static void ValidatePolygon(
        List<PixelPoint> polygon,
        FloorPlanEntity floorPlan,
        string elementName)
    {
        if (
            polygon.Count < 3
        )
        {
            throw new InvalidOperationException(
                $"{elementName} does not contain a valid polygon."
            );
        }


        foreach (
            var point
            in polygon
        )
        {
            if (
                !double.IsFinite(
                    point.X
                )
                ||
                !double.IsFinite(
                    point.Y
                )
            )
            {
                throw new InvalidOperationException(
                    $"{elementName} contains invalid coordinates."
                );
            }


            if (
                point.X < 0
                ||
                point.Y < 0
                ||
                point.X >
                    floorPlan.WidthPixels
                ||
                point.Y >
                    floorPlan.HeightPixels
            )
            {
                throw new InvalidOperationException(
                    $"{elementName} contains coordinates outside the floor-plan image."
                );
            }
        }
    }
}