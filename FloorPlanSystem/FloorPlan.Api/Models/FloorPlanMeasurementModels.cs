namespace FloorPlan.Api.Models;


public class SaveFloorPlanMeasurementRequest
{
    public double StartX { get; set; }

    public double StartY { get; set; }

    public double EndX { get; set; }

    public double EndY { get; set; }

    public double ActualDistance { get; set; }

    public string Unit { get; set; } = "m";
}


public class FloorPlanMeasurementResponse
{
    public int Id { get; set; }

    public int FloorPlanId { get; set; }


    public double StartX { get; set; }

    public double StartY { get; set; }

    public double EndX { get; set; }

    public double EndY { get; set; }


    public double ActualDistance { get; set; }

    public string Unit { get; set; } = "m";


    public double PixelDistance { get; set; }

    public double MetresPerPixel { get; set; }
}