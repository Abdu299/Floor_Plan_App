using System.Text.Json;
using FloorPlan.Api.Data;
using FloorPlan.Api.Models;

namespace FloorPlan.Api.Services;

public class FloorPlanPersistenceService
{
    private static readonly JsonSerializerOptions BoundaryJsonOptions =
        new(JsonSerializerDefaults.Web);


    private readonly AppDbContext _db;
    private readonly IWebHostEnvironment _environment;


    public FloorPlanPersistenceService(
        AppDbContext db,
        IWebHostEnvironment environment)
    {
        _db = db;
        _environment = environment;
    }


    public async Task<SavedFloorPlanResult> SaveAiDetectionAsync(
        IFormFile image,
        FloorPlanDetectionResult detection,
        CancellationToken cancellationToken = default)
    {
        string? savedPhysicalPath = null;

        await using var transaction =
            await _db.Database.BeginTransactionAsync(
                cancellationToken
            );

        try
        {
            // -------------------------------------------------
            // Save original image
            // -------------------------------------------------

            var extension =
                Path.GetExtension(image.FileName).ToLowerInvariant();

            var allowedExtensions = new[]
            {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp"
            };

            if (!allowedExtensions.Contains(extension))
            {
                throw new InvalidOperationException(
                    "Unsupported image type."
                );
            }


            var webRoot =
                _environment.WebRootPath
                ?? Path.Combine(
                    _environment.ContentRootPath,
                    "wwwroot"
                );


            var uploadDirectory =
                Path.Combine(
                    webRoot,
                    "uploads"
                );


            Directory.CreateDirectory(uploadDirectory);


            var storedFileName =
                $"{Guid.NewGuid():N}{extension}";


            savedPhysicalPath =
                Path.Combine(
                    uploadDirectory,
                    storedFileName
                );


            await using (
                var fileStream = new FileStream(
                    savedPhysicalPath,
                    FileMode.Create
                )
            )
            {
                await image.CopyToAsync(
                    fileStream,
                    cancellationToken
                );
            }


            var relativeImagePath =
                $"/uploads/{storedFileName}";


            // -------------------------------------------------
            // FloorPlan
            // -------------------------------------------------

            var floorPlan = new FloorPlanEntity
            {
                OriginalFileName =
                    Path.GetFileName(image.FileName),

                ImagePath = relativeImagePath,

                WidthPixels =
                    detection.Image.WidthPixels,

                HeightPixels =
                    detection.Image.HeightPixels,

                CreatedAtUtc = DateTime.UtcNow
            };


            _db.FloorPlans.Add(floorPlan);


            // -------------------------------------------------
            // AI Revision #1
            // -------------------------------------------------

            var revision = new FloorPlanRevisionEntity
            {
                FloorPlan = floorPlan,

                RevisionNumber = 1,

                Source = RevisionSource.Ai,

                Status = RevisionStatus.Draft,

                BasedOnRevisionId = null,

                Valid = detection.Validation.Valid,

                HasBathroom =
                    detection.Validation.HasBathroom,

                HasKitchen =
                    detection.Validation.HasKitchen,

                BuildingBoundaryJson =
                    JsonSerializer.Serialize(
                        detection.BuildingBoundary,
                        BoundaryJsonOptions
                    ),

                CreatedAtUtc = DateTime.UtcNow
            };


            _db.FloorPlanRevisions.Add(revision);


            // -------------------------------------------------
            // Rooms
            // -------------------------------------------------

            var roomMap =
                new Dictionary<int, RoomEntity>();


            foreach (var detectedRoom in detection.Rooms)
            {
                var room = new RoomEntity
                {
                    Revision = revision,

                    SourceElementId =
                        detectedRoom.Id,

                    Name =
                        detectedRoom.Name,

                    Confidence =
                        detectedRoom.Confidence,

                    PolygonJson =
                        JsonSerializer.Serialize(
                            detectedRoom.Polygon
                        ),

                    CentroidX =
                        detectedRoom.Centroid.X,

                    CentroidY =
                        detectedRoom.Centroid.Y,

                    AreaPixels =
                        detectedRoom.AreaPixels
                };


                _db.Rooms.Add(room);

                roomMap[detectedRoom.Id] = room;
            }


            // We need room database IDs before creating
            // door/opening foreign keys.
            await _db.SaveChangesAsync(
                cancellationToken
            );


            // -------------------------------------------------
            // Doors
            // -------------------------------------------------

            foreach (var detectedDoor in detection.Doors)
            {
                if (!roomMap.TryGetValue(
                        detectedDoor.Room1.Id,
                        out var room1))
                {
                    throw new InvalidOperationException(
                        $"Door {detectedDoor.Id} references " +
                        $"unknown room {detectedDoor.Room1.Id}."
                    );
                }


                RoomEntity? room2 = null;


                if (detectedDoor.Room2 is not null)
                {
                    if (!roomMap.TryGetValue(
                            detectedDoor.Room2.Id,
                            out room2))
                    {
                        throw new InvalidOperationException(
                            $"Door {detectedDoor.Id} references " +
                            $"unknown room {detectedDoor.Room2.Id}."
                        );
                    }
                }


                var door = new DoorEntity
                {
                    Revision = revision,

                    SourceElementId =
                        detectedDoor.Id,

                    PolygonJson =
                        JsonSerializer.Serialize(
                            detectedDoor.Polygon
                        ),

                    Confidence =
                        detectedDoor.Confidence,

                    BboxX1 =
                        detectedDoor.BoundingBox?.X1,

                    BboxY1 =
                        detectedDoor.BoundingBox?.Y1,

                    BboxX2 =
                        detectedDoor.BoundingBox?.X2,

                    BboxY2 =
                        detectedDoor.BoundingBox?.Y2,

                    Room1Id = room1.Id,

                    // null means Room1 <-> Outside.
                    Room2Id = room2?.Id
                };


                _db.Doors.Add(door);
            }


            // -------------------------------------------------
            // Windows
            // -------------------------------------------------

            foreach (var detectedWindow in detection.Windows)
            {
                var window = new WindowEntity
                {
                    Revision = revision,

                    SourceElementId =
                        detectedWindow.Id,

                    PolygonJson =
                        JsonSerializer.Serialize(
                            detectedWindow.Polygon
                        ),

                    BboxX1 =
                        detectedWindow.BoundingBox?.X1,

                    BboxY1 =
                        detectedWindow.BoundingBox?.Y1,

                    BboxX2 =
                        detectedWindow.BoundingBox?.X2,

                    BboxY2 =
                        detectedWindow.BoundingBox?.Y2
                };


                _db.Windows.Add(window);
            }


            // -------------------------------------------------
            // Openings
            // -------------------------------------------------

            foreach (var detectedOpening in detection.Openings)
            {
                if (!roomMap.TryGetValue(
                        detectedOpening.Room1.Id,
                        out var room1))
                {
                    throw new InvalidOperationException(
                        $"Opening {detectedOpening.Id} references " +
                        $"unknown room {detectedOpening.Room1.Id}."
                    );
                }


                if (!roomMap.TryGetValue(
                        detectedOpening.Room2.Id,
                        out var room2))
                {
                    throw new InvalidOperationException(
                        $"Opening {detectedOpening.Id} references " +
                        $"unknown room {detectedOpening.Room2.Id}."
                    );
                }


                var opening = new OpeningEntity
                {
                    Revision = revision,

                    SourceElementId =
                        detectedOpening.Id,

                    PolygonJson =
                        JsonSerializer.Serialize(
                            detectedOpening.Polygon
                        ),

                    BboxX1 =
                        detectedOpening.BoundingBox?.X1,

                    BboxY1 =
                        detectedOpening.BoundingBox?.Y1,

                    BboxX2 =
                        detectedOpening.BoundingBox?.X2,

                    BboxY2 =
                        detectedOpening.BoundingBox?.Y2,

                    Room1Id = room1.Id,

                    Room2Id = room2.Id
                };


                _db.Openings.Add(opening);
            }


            await _db.SaveChangesAsync(
                cancellationToken
            );


            await transaction.CommitAsync(
                cancellationToken
            );


            return new SavedFloorPlanResult
            {
                FloorPlanId = floorPlan.Id,
                RevisionId = revision.Id,
                ImagePath = floorPlan.ImagePath
            };
        }
        catch
        {
            await transaction.RollbackAsync(
                cancellationToken
            );


            if (
                savedPhysicalPath != null
                && File.Exists(savedPhysicalPath)
            )
            {
                File.Delete(savedPhysicalPath);
            }


            throw;
        }
    }
}


public class SavedFloorPlanResult
{
    public int FloorPlanId { get; set; }

    public int RevisionId { get; set; }

    public string ImagePath { get; set; } = string.Empty;
}