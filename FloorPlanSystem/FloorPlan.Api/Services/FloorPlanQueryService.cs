using System.Text.Json;
using FloorPlan.Api.Data;
using FloorPlan.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace FloorPlan.Api.Services;


public class FloorPlanQueryService
{
    private readonly AppDbContext _db;


    public FloorPlanQueryService(
        AppDbContext db)
    {
        _db = db;
    }


    // =========================================================
    // GET ALL SAVED FLOOR PLANS
    // =========================================================

    public async Task<List<FloorPlanListItemResponse>>
        GetFloorPlansAsync(
            CancellationToken cancellationToken = default)
    {
        var floorPlans =
            await _db.FloorPlans
                .AsNoTracking()

                .OrderByDescending(
                    x => x.CreatedAtUtc
                )

                .Select(
                    floorPlan =>
                        new
                        {
                            floorPlan.Id,

                            floorPlan.OriginalFileName,

                            floorPlan.ImagePath,

                            floorPlan.WidthPixels,

                            floorPlan.HeightPixels,

                            floorPlan.CreatedAtUtc,


                            LatestRevision =
                                floorPlan.Revisions

                                    .OrderByDescending(
                                        revision =>
                                            revision.RevisionNumber
                                    )

                                    .Select(
                                        revision =>
                                            new
                                            {
                                                revision.RevisionNumber,

                                                revision.Source,

                                                revision.Status,

                                                RoomCount =
                                                    revision.Rooms.Count,

                                                DoorCount =
                                                    revision.Doors.Count,

                                                WindowCount =
                                                    revision.Windows.Count,

                                                OpeningCount =
                                                    revision.Openings.Count
                                            }
                                    )

                                    .FirstOrDefault()
                        }
                )

                .ToListAsync(
                    cancellationToken
                );


        return floorPlans
            .Select(
                floorPlan =>
                    new FloorPlanListItemResponse
                    {
                        FloorPlanId =
                            floorPlan.Id,

                        OriginalFileName =
                            floorPlan.OriginalFileName,

                        ImagePath =
                            floorPlan.ImagePath,

                        WidthPixels =
                            floorPlan.WidthPixels,

                        HeightPixels =
                            floorPlan.HeightPixels,

                        CreatedAtUtc =
                            floorPlan.CreatedAtUtc,


                        LatestRevisionNumber =
                            floorPlan.LatestRevision
                                ?.RevisionNumber
                            ?? 0,


                        LatestRevisionSource =
                            floorPlan.LatestRevision == null
                                ? ""
                                : floorPlan
                                    .LatestRevision
                                    .Source
                                    .ToString()
                                    .ToLowerInvariant(),


                        LatestRevisionStatus =
                            floorPlan.LatestRevision == null
                                ? ""
                                : floorPlan
                                    .LatestRevision
                                    .Status
                                    .ToString()
                                    .ToLowerInvariant(),


                        RoomCount =
                            floorPlan.LatestRevision
                                ?.RoomCount
                            ?? 0,


                        DoorCount =
                            floorPlan.LatestRevision
                                ?.DoorCount
                            ?? 0,


                        WindowCount =
                            floorPlan.LatestRevision
                                ?.WindowCount
                            ?? 0,


                        OpeningCount =
                            floorPlan.LatestRevision
                                ?.OpeningCount
                            ?? 0
                    }
            )

            .ToList();
    }


    // =========================================================
    // GET FLOOR PLAN + LATEST REVISION
    // =========================================================

    public async Task<FloorPlanResponse?>
        GetFloorPlanAsync(
            int floorPlanId,
            CancellationToken cancellationToken = default)
    {
        var floorPlan =
            await _db.FloorPlans
                .AsNoTracking()

                .FirstOrDefaultAsync(
                    x =>
                        x.Id ==
                        floorPlanId,

                    cancellationToken
                );


        if (floorPlan == null)
        {
            return null;
        }


        var latestRevisionNumber =
            await _db.FloorPlanRevisions
                .AsNoTracking()

                .Where(
                    x =>
                        x.FloorPlanId ==
                        floorPlanId
                )

                .MaxAsync(
                    x =>
                        (int?)x.RevisionNumber,

                    cancellationToken
                );


        if (latestRevisionNumber == null)
        {
            return null;
        }


        var revision =
            await GetRevisionInternalAsync(
                floorPlanId,
                latestRevisionNumber.Value,
                cancellationToken
            );


        if (revision == null)
        {
            return null;
        }


        return new FloorPlanResponse
        {
            FloorPlanId =
                floorPlan.Id,

            OriginalFileName =
                floorPlan.OriginalFileName,

            ImagePath =
                floorPlan.ImagePath,

            WidthPixels =
                floorPlan.WidthPixels,

            HeightPixels =
                floorPlan.HeightPixels,

            CreatedAtUtc =
                floorPlan.CreatedAtUtc,

            Revision =
                revision
        };
    }


    // =========================================================
    // GET SPECIFIC REVISION
    // =========================================================

    public async Task<FloorPlanResponse?>
        GetRevisionAsync(
            int floorPlanId,
            int revisionNumber,
            CancellationToken cancellationToken = default)
    {
        var floorPlan =
            await _db.FloorPlans
                .AsNoTracking()

                .FirstOrDefaultAsync(
                    x =>
                        x.Id ==
                        floorPlanId,

                    cancellationToken
                );


        if (floorPlan == null)
        {
            return null;
        }


        var revision =
            await GetRevisionInternalAsync(
                floorPlanId,
                revisionNumber,
                cancellationToken
            );


        if (revision == null)
        {
            return null;
        }


        return new FloorPlanResponse
        {
            FloorPlanId =
                floorPlan.Id,

            OriginalFileName =
                floorPlan.OriginalFileName,

            ImagePath =
                floorPlan.ImagePath,

            WidthPixels =
                floorPlan.WidthPixels,

            HeightPixels =
                floorPlan.HeightPixels,

            CreatedAtUtc =
                floorPlan.CreatedAtUtc,

            Revision =
                revision
        };
    }


    // =========================================================
    // GET REVISION HISTORY
    // =========================================================

    public async Task<List<FloorPlanRevisionSummaryResponse>>
        GetRevisionHistoryAsync(
            int floorPlanId,
            CancellationToken cancellationToken = default)
    {
        return await _db.FloorPlanRevisions
            .AsNoTracking()

            .Where(
                x =>
                    x.FloorPlanId ==
                    floorPlanId
            )

            .OrderByDescending(
                x => x.RevisionNumber
            )

            .Select(
                x =>
                    new FloorPlanRevisionSummaryResponse
                    {
                        RevisionId =
                            x.Id,

                        RevisionNumber =
                            x.RevisionNumber,

                        Source =
                            x.Source
                                .ToString()
                                .ToLower(),

                        Status =
                            x.Status
                                .ToString()
                                .ToLower(),

                        BasedOnRevisionId =
                            x.BasedOnRevisionId,

                        CreatedAtUtc =
                            x.CreatedAtUtc
                    }
            )

            .ToListAsync(
                cancellationToken
            );
    }


    // =========================================================
    // INTERNAL REVISION LOADER
    // =========================================================

    private async Task<FloorPlanRevisionResponse?>
        GetRevisionInternalAsync(
            int floorPlanId,
            int revisionNumber,
            CancellationToken cancellationToken)
    {
        var revision =
            await _db.FloorPlanRevisions

                .AsNoTracking()

                .Where(
                    x =>
                        x.FloorPlanId ==
                        floorPlanId
                        &&
                        x.RevisionNumber ==
                        revisionNumber
                )

                .Include(
                    x => x.Rooms
                )

                .Include(
                    x => x.Doors
                )
                    .ThenInclude(
                        x => x.Room1
                    )

                .Include(
                    x => x.Doors
                )
                    .ThenInclude(
                        x => x.Room2
                    )

                .Include(
                    x => x.Windows
                )

                .Include(
                    x => x.Openings
                )
                    .ThenInclude(
                        x => x.Room1
                    )

                .Include(
                    x => x.Openings
                )
                    .ThenInclude(
                        x => x.Room2
                    )

                .AsSplitQuery()

                .FirstOrDefaultAsync(
                    cancellationToken
                );


        if (revision == null)
        {
            return null;
        }


        // =====================================================
        // ROOMS
        // =====================================================

        var rooms =
            revision.Rooms

                .OrderBy(
                    x => x.SourceElementId
                )

                .Select(
                    room =>
                        new RoomDetection
                        {
                            Id =
                                room.SourceElementId,

                            Confidence =
                                room.Confidence ?? 0,

                            Name =
                                room.Name,

                            Polygon =
                                DeserializePolygon(
                                    room.PolygonJson
                                ),

                            Centroid =
                                new PixelPoint
                                {
                                    X =
                                        room.CentroidX,

                                    Y =
                                        room.CentroidY
                                },

                            AreaPixels =
                                room.AreaPixels,

                            AreaSquareMetres =
                                room.AreaSquareMetres
                        }
                )

                .ToList();


        // =====================================================
        // DOORS
        // =====================================================

        var doors =
            revision.Doors

                .OrderBy(
                    x => x.SourceElementId
                )

                .Select(
                    door =>
                        new DoorDetection
                        {
                            Id =
                                door.SourceElementId,

                            Confidence =
                                door.Confidence ?? 0,

                            Polygon =
                                DeserializePolygon(
                                    door.PolygonJson
                                ),

                            BoundingBox =
                                CreateBoundingBox(
                                    door.BboxX1,
                                    door.BboxY1,
                                    door.BboxX2,
                                    door.BboxY2
                                ),

                            Room1 =
                                new ConnectedRoom
                                {
                                    Id =
                                        door
                                            .Room1
                                            .SourceElementId,

                                    Name =
                                        door
                                            .Room1
                                            .Name
                                },

                            Room2 =
                                new ConnectedRoom
                                {
                                    Id =
                                        door
                                            .Room2
                                            .SourceElementId,

                                    Name =
                                        door
                                            .Room2
                                            .Name
                                }
                        }
                )

                .ToList();


        // =====================================================
        // WINDOWS
        // =====================================================

        var windows =
            revision.Windows

                .OrderBy(
                    x => x.SourceElementId
                )

                .Select(
                    window =>
                        new WindowDetection
                        {
                            Id =
                                window.SourceElementId,

                            Polygon =
                                DeserializePolygon(
                                    window.PolygonJson
                                ),

                            BoundingBox =
                                CreateBoundingBox(
                                    window.BboxX1,
                                    window.BboxY1,
                                    window.BboxX2,
                                    window.BboxY2
                                )
                        }
                )

                .ToList();


        // =====================================================
        // OPENINGS
        // =====================================================

        var openings =
            revision.Openings

                .OrderBy(
                    x => x.SourceElementId
                )

                .Select(
                    opening =>
                        new OpeningDetection
                        {
                            Id =
                                opening.SourceElementId,

                            Polygon =
                                DeserializePolygon(
                                    opening.PolygonJson
                                ),

                            BoundingBox =
                                CreateBoundingBox(
                                    opening.BboxX1,
                                    opening.BboxY1,
                                    opening.BboxX2,
                                    opening.BboxY2
                                ),

                            Room1 =
                                new ConnectedRoom
                                {
                                    Id =
                                        opening
                                            .Room1
                                            .SourceElementId,

                                    Name =
                                        opening
                                            .Room1
                                            .Name
                                },

                            Room2 =
                                new ConnectedRoom
                                {
                                    Id =
                                        opening
                                            .Room2
                                            .SourceElementId,

                                    Name =
                                        opening
                                            .Room2
                                            .Name
                                }
                        }
                )

                .ToList();


        return new FloorPlanRevisionResponse
        {
            RevisionId =
                revision.Id,

            RevisionNumber =
                revision.RevisionNumber,

            Source =
                revision.Source
                    .ToString()
                    .ToLowerInvariant(),

            Status =
                revision.Status
                    .ToString()
                    .ToLowerInvariant(),

            BasedOnRevisionId =
                revision.BasedOnRevisionId,

            CreatedAtUtc =
                revision.CreatedAtUtc,


            Validation =
                new FloorPlanValidation
                {
                    Valid =
                        revision.Valid,

                    HasBathroom =
                        revision.HasBathroom,

                    HasKitchen =
                        revision.HasKitchen
                },


            Summary =
                new DetectionSummary
                {
                    Rooms =
                        rooms.Count,

                    Doors =
                        doors.Count,

                    Windows =
                        windows.Count,

                    Openings =
                        openings.Count
                },


            Rooms =
                rooms,

            Doors =
                doors,

            Windows =
                windows,

            Openings =
                openings
        };
    }


    // =========================================================
    // DESERIALIZE POLYGON
    // =========================================================

    private static List<PixelPoint>
        DeserializePolygon(
            string json)
    {
        try
        {
            return JsonSerializer.Deserialize<
                List<PixelPoint>
            >(
                json,

                new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive =
                        true
                }
            )
            ?? [];
        }
        catch
        {
            return [];
        }
    }


    // =========================================================
    // CREATE BOUNDING BOX
    // =========================================================

    private static BoundingBox?
        CreateBoundingBox(
            double? x1,
            double? y1,
            double? x2,
            double? y2)
    {
        if (
            x1 == null ||
            y1 == null ||
            x2 == null ||
            y2 == null
        )
        {
            return null;
        }


        return new BoundingBox
        {
            X1 =
                x1.Value,

            Y1 =
                y1.Value,

            X2 =
                x2.Value,

            Y2 =
                y2.Value
        };
    }
}