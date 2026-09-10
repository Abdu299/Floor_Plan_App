namespace FloorPlan.Api.Models;


// =========================================================
// COMPLETE FLOOR PLAN RESPONSE
// =========================================================

public class FloorPlanResponse
{
    public int FloorPlanId { get; set; }

    public string OriginalFileName { get; set; } =
        string.Empty;

    public string ImagePath { get; set; } =
        string.Empty;

    public int WidthPixels { get; set; }

    public int HeightPixels { get; set; }

    public DateTime CreatedAtUtc { get; set; }

    public FloorPlanRevisionResponse Revision { get; set; } =
        new();
}


// =========================================================
// COMPLETE REVISION
// =========================================================

public class FloorPlanRevisionResponse
{
    public int RevisionId { get; set; }

    public int RevisionNumber { get; set; }

    public string Source { get; set; } =
        string.Empty;

    public string Status { get; set; } =
        string.Empty;

    public int? BasedOnRevisionId { get; set; }

    public DateTime CreatedAtUtc { get; set; }


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
// REVISION HISTORY ITEM
// =========================================================

public class FloorPlanRevisionSummaryResponse
{
    public int RevisionId { get; set; }

    public int RevisionNumber { get; set; }

    public string Source { get; set; } =
        string.Empty;

    public string Status { get; set; } =
        string.Empty;

    public int? BasedOnRevisionId { get; set; }

    public DateTime CreatedAtUtc { get; set; }
}


// =========================================================
// SAVED FLOOR PLAN LIST ITEM
// =========================================================

public class FloorPlanListItemResponse
{
    public int FloorPlanId { get; set; }


    public string OriginalFileName { get; set; } =
        string.Empty;


    public string ImagePath { get; set; } =
        string.Empty;


    public int WidthPixels { get; set; }

    public int HeightPixels { get; set; }


    public DateTime CreatedAtUtc { get; set; }


    public int LatestRevisionNumber { get; set; }


    public string LatestRevisionSource { get; set; } =
        string.Empty;


    public string LatestRevisionStatus { get; set; } =
        string.Empty;


    public int RoomCount { get; set; }

    public int DoorCount { get; set; }

    public int WindowCount { get; set; }

    public int OpeningCount { get; set; }
}