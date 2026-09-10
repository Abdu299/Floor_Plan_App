namespace FloorPlan.Api.Data;


public enum RevisionSource
{
    Ai,
    User
}


public enum RevisionStatus
{
    Draft,
    Confirmed
}


// =========================================================
// FLOOR PLAN
// =========================================================

public class FloorPlanEntity
{
    public int Id { get; set; }


    public string OriginalFileName { get; set; } =
        string.Empty;


    public string ImagePath { get; set; } =
        string.Empty;


    public int WidthPixels { get; set; }

    public int HeightPixels { get; set; }


    public DateTime CreatedAtUtc { get; set; }


    public List<FloorPlanRevisionEntity> Revisions { get; set; } =
        [];


    public List<FloorPlanMeasurementEntity> Measurements { get; set; } =
        [];
}


// =========================================================
// MEASUREMENT
// =========================================================
//
// We are not using this in the UI anymore,
// but it can stay in the database.
//

public class FloorPlanMeasurementEntity
{
    public int Id { get; set; }


    public int FloorPlanId { get; set; }

    public FloorPlanEntity FloorPlan { get; set; } =
        null!;


    public double StartX { get; set; }

    public double StartY { get; set; }


    public double EndX { get; set; }

    public double EndY { get; set; }


    public double ActualDistance { get; set; }


    public string Unit { get; set; } =
        "m";


    public double? MetresPerPixel { get; set; }
}


// =========================================================
// REVISION
// =========================================================

public class FloorPlanRevisionEntity
{
    public int Id { get; set; }


    public int FloorPlanId { get; set; }

    public FloorPlanEntity FloorPlan { get; set; } =
        null!;


    public int RevisionNumber { get; set; }


    public RevisionSource Source { get; set; }


    public RevisionStatus Status { get; set; }


    public int? BasedOnRevisionId { get; set; }


    public bool Valid { get; set; }

    public bool HasBathroom { get; set; }

    public bool HasKitchen { get; set; }


    // Canonical boundary JSON for THIS immutable revision.
    //
    // We keep the complete boundary object as JSON so edits, review state,
    // provenance and automatic-assessment metadata round-trip together.
    public string BuildingBoundaryJson { get; set; } =
        "{}";


    public DateTime CreatedAtUtc { get; set; }


    public List<RoomEntity> Rooms { get; set; } =
        [];


    public List<DoorEntity> Doors { get; set; } =
        [];


    public List<WindowEntity> Windows { get; set; } =
        [];


    public List<OpeningEntity> Openings { get; set; } =
        [];
}


// =========================================================
// ROOM
// =========================================================

public class RoomEntity
{
    public int Id { get; set; }


    public int FloorPlanRevisionId { get; set; }


    // IMPORTANT:
    // Keep this named "Revision".
    //
    // AppDbContext and FloorPlanPersistenceService
    // already use this property.
    public FloorPlanRevisionEntity Revision { get; set; } =
        null!;


    public int SourceElementId { get; set; }


    public string Name { get; set; } =
        string.Empty;


    public double? Confidence { get; set; }


    // =====================================================
    // NEW
    //
    // Real-world room area entered manually by the user.
    //
    // Example:
    // 12.5 = 12.5 m²
    //
    // null = user has not entered an area yet
    // =====================================================

    public double? AreaSquareMetres { get; set; }


    public string PolygonJson { get; set; } =
        "[]";


    public double CentroidX { get; set; }

    public double CentroidY { get; set; }


    // Geometric area calculated from the image.
    // This is pixels², not real m².
    public double AreaPixels { get; set; }
}


// =========================================================
// DOOR
// =========================================================

public class DoorEntity
{
    public int Id { get; set; }


    public int FloorPlanRevisionId { get; set; }


    public FloorPlanRevisionEntity Revision { get; set; } =
        null!;


    public int SourceElementId { get; set; }


    public string PolygonJson { get; set; } =
        "[]";


    public double? BboxX1 { get; set; }

    public double? BboxY1 { get; set; }

    public double? BboxX2 { get; set; }

    public double? BboxY2 { get; set; }


    public double? Confidence { get; set; }


    public int Room1Id { get; set; }

    public RoomEntity Room1 { get; set; } =
        null!;


    // null represents Outside for an exterior door.
    public int? Room2Id { get; set; }

    public RoomEntity? Room2 { get; set; }
}


// =========================================================
// WINDOW
// =========================================================

public class WindowEntity
{
    public int Id { get; set; }


    public int FloorPlanRevisionId { get; set; }


    public FloorPlanRevisionEntity Revision { get; set; } =
        null!;


    public int SourceElementId { get; set; }


    public string PolygonJson { get; set; } =
        "[]";


    public double? BboxX1 { get; set; }

    public double? BboxY1 { get; set; }

    public double? BboxX2 { get; set; }

    public double? BboxY2 { get; set; }
}


// =========================================================
// OPENING
// =========================================================

public class OpeningEntity
{
    public int Id { get; set; }


    public int FloorPlanRevisionId { get; set; }


    public FloorPlanRevisionEntity Revision { get; set; } =
        null!;


    public int SourceElementId { get; set; }


    public string PolygonJson { get; set; } =
        "[]";


    public double? BboxX1 { get; set; }

    public double? BboxY1 { get; set; }

    public double? BboxX2 { get; set; }

    public double? BboxY2 { get; set; }


    public int Room1Id { get; set; }

    public RoomEntity Room1 { get; set; } =
        null!;


    public int Room2Id { get; set; }

    public RoomEntity Room2 { get; set; } =
        null!;
}