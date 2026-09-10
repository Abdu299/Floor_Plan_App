namespace FloorPlan.Api.Models;


public class SaveRevisionRequest
{
    public int BasedOnRevisionId { get; set; }


    public FloorPlanValidation Validation { get; set; } =
        new();


    public List<RoomDetection> Rooms { get; set; } =
        [];


    public List<DoorDetection> Doors { get; set; } =
        [];


    public List<WindowDetection> Windows { get; set; } =
        [];


    public List<OpeningDetection> Openings { get; set; } =
        [];


    // The boundary is revision data, just like rooms/doors/windows/openings.
    // It is saved even when the automatic assessment is valid=false.
    public BuildingBoundaryDetection BuildingBoundary { get; set; } =
        new();
}


public class SavedRevisionResponse
{
    public int FloorPlanId { get; set; }

    public int RevisionId { get; set; }

    public int RevisionNumber { get; set; }

    public int BasedOnRevisionId { get; set; }

    public string Source { get; set; } =
        string.Empty;

    public string Status { get; set; } =
        string.Empty;

    public DateTime CreatedAtUtc { get; set; }
}