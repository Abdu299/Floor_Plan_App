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