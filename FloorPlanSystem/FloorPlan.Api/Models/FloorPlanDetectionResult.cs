using System.Text.Json.Serialization;

namespace FloorPlan.Api.Models;



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




public class FloorPlanImageInfo
{
    public string FileName { get; set; } =
        string.Empty;


    public int WidthPixels { get; set; }

    public int HeightPixels { get; set; }
}




public class FloorPlanValidation
{
    public bool Valid { get; set; }

    public bool HasBathroom { get; set; }

    public bool HasKitchen { get; set; }
}




public class DetectionSummary
{
    public int Rooms { get; set; }

    public int Doors { get; set; }

    public int Windows { get; set; }

    public int Openings { get; set; }
}



public class BuildingBoundaryDetection
{
    // =====================================================
    // CANONICAL BUILDING GEOMETRY
    // =====================================================
    //
    // There is now ONLY ONE application boundary.
    //
    // Polygon represents the usable interior floor envelope.
    //
    // Everything outside this polygon is outside the space
    // where rooms may exist or where the optimizer may move
    // geometry.
    //
    // Coordinates are always ORIGINAL IMAGE PIXELS.
    // =====================================================

    public List<PixelPoint> Polygon { get; set; } =
        [];


    // =====================================================
    // CURRENT GEOMETRY OWNER
    // =====================================================
    //
    // "ai"
    //     Geometry is still the automatic detector result.
    //
    // "user"
    //     The user changed/redrew the polygon.
    // =====================================================

    public string Source { get; set; } =
        "ai";


    // Typical values:
    //
    // "unreviewed"
    // "edited"
    // "confirmed"
    // "needs-recalculation"

    public string ReviewStatus { get; set; } =
        "unreviewed";


    public bool IsUserEdited { get; set; }



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


    public double? AreaSquareMetres { get; set; }
}




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




public class WindowDetection
{
    public int Id { get; set; }


    public List<PixelPoint> Polygon { get; set; } =
        [];


    [JsonPropertyName("bbox")]
    public BoundingBox? BoundingBox { get; set; }
}




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




public class ConnectedRoom
{
    public int Id { get; set; }


    public string Name { get; set; } =
        string.Empty;
}



public class PixelPoint
{
    public double X { get; set; }

    public double Y { get; set; }
}




public class BoundingBox
{
    public double X1 { get; set; }

    public double Y1 { get; set; }

    public double X2 { get; set; }

    public double Y2 { get; set; }
}