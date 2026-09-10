using System.Text.Json.Serialization;

namespace FloorPlan.Api.Models;


// =========================================================
// COMPLETE DETECTION RESULT
// =========================================================

public class FloorPlanDetectionResult
{
    public string Type { get; set; } =
        string.Empty;


    public FloorPlanImageInfo Image { get; set; } =
        new();


    public FloorPlanValidation Validation { get; set; } =
        new();


    public DetectionSummary Summary { get; set; } =
        new();


    public List<RoomDetection> Rooms { get; set; } =
        [];


    public List<DoorDetection> Doors { get; set; } =
        [];


    public List<WindowDetection> Windows { get; set; } =
        [];


    public List<OpeningDetection> Openings { get; set; } =
        [];


    public BuildingBoundaryDetection BuildingBoundary { get; set; } =
        new();
}


// =========================================================
// IMAGE
// =========================================================

public class FloorPlanImageInfo
{
    public string FileName { get; set; } =
        string.Empty;


    public int WidthPixels { get; set; }

    public int HeightPixels { get; set; }
}


// =========================================================
// VALIDATION
// =========================================================

public class FloorPlanValidation
{
    public bool Valid { get; set; }

    public bool HasBathroom { get; set; }

    public bool HasKitchen { get; set; }
}


// =========================================================
// SUMMARY
// =========================================================

public class DetectionSummary
{
    public int Rooms { get; set; }

    public int Doors { get; set; }

    public int Windows { get; set; }

    public int Openings { get; set; }
}


// =========================================================
// BUILDING BOUNDARY
// =========================================================

public class BuildingBoundaryDetection
{
    // Current geometry for this revision.
    // These coordinates are in ORIGINAL IMAGE PIXELS.
    public List<PixelPoint> OuterPolygon { get; set; } =
        [];

    public List<PixelPoint> UsablePolygon { get; set; } =
        [];


    // Who produced the CURRENT boundary geometry.
    //
    // "ai"   = unchanged automatic result
    // "user" = user edited the geometry
    public string Source { get; set; } =
        "ai";


    // Typical values:
    // "unreviewed", "edited", "confirmed", "needs-recalculation"
    public string ReviewStatus { get; set; } =
        "unreviewed";


    public bool IsUserEdited { get; set; }


    // This keeps the detector's original confidence/provenance information.
    // It is intentionally separate from the current geometry so a user can
    // edit a boundary even when the AI said valid=true.
    public BoundaryAutomaticAssessment AutomaticAssessment { get; set; } =
        new();
}


public class BoundaryAutomaticAssessment
{
    public bool Valid { get; set; }

    public bool RequiresReview { get; set; } =
        true;

    public string Method { get; set; } =
        "hybrid";

    public string CandidateSource { get; set; } =
        "none";

    public string Message { get; set; } =
        string.Empty;


    public double RoomAreaCoverage { get; set; }

    public double RoomCentroidCoverage { get; set; }

    public double WallSupport { get; set; }


    public int SelectedStructuralGapPixels { get; set; }

    public double EstimatedWallThicknessPixels { get; set; }
}


// =========================================================
// ROOM
// =========================================================

public class RoomDetection
{
    public int Id { get; set; }


    public double Confidence { get; set; }


    public string Name { get; set; } =
        string.Empty;


    public List<PixelPoint> Polygon { get; set; } =
        [];


    public PixelPoint Centroid { get; set; } =
        new();


    public double AreaPixels { get; set; }


    // =====================================================
    // NEW
    // =====================================================

    public double? AreaSquareMetres { get; set; }
}


// =========================================================
// DOOR
// =========================================================

public class DoorDetection
{
    public int Id { get; set; }


    public List<PixelPoint> Polygon { get; set; } =
        [];


    [JsonPropertyName("bbox")]
    public BoundingBox? BoundingBox { get; set; }


    public ConnectedRoom Room1 { get; set; } =
        new();


    // null means this door connects Room1 to Outside.
    public ConnectedRoom? Room2 { get; set; }


    public double Confidence { get; set; }
}


// =========================================================
// WINDOW
// =========================================================

public class WindowDetection
{
    public int Id { get; set; }


    public List<PixelPoint> Polygon { get; set; } =
        [];


    [JsonPropertyName("bbox")]
    public BoundingBox? BoundingBox { get; set; }
}


// =========================================================
// OPENING
// =========================================================

public class OpeningDetection
{
    public int Id { get; set; }


    public List<PixelPoint> Polygon { get; set; } =
        [];


    [JsonPropertyName("bbox")]
    public BoundingBox? BoundingBox { get; set; }


    public ConnectedRoom Room1 { get; set; } =
        new();


    public ConnectedRoom Room2 { get; set; } =
        new();
}


// =========================================================
// CONNECTED ROOM
// =========================================================

public class ConnectedRoom
{
    public int Id { get; set; }


    public string Name { get; set; } =
        string.Empty;
}


// =========================================================
// PIXEL POINT
// =========================================================

public class PixelPoint
{
    public double X { get; set; }

    public double Y { get; set; }
}


// =========================================================
// BOUNDING BOX
// =========================================================

public class BoundingBox
{
    public double X1 { get; set; }

    public double Y1 { get; set; }

    public double X2 { get; set; }

    public double Y2 { get; set; }
}