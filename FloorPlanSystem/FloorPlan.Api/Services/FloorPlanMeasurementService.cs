using FloorPlan.Api.Data;
using FloorPlan.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace FloorPlan.Api.Services;


public class FloorPlanMeasurementService
{
    private readonly AppDbContext _db;


    public FloorPlanMeasurementService(
        AppDbContext db)
    {
        _db = db;
    }


    // =========================================================
    // SAVE MEASUREMENT
    // =========================================================

    public async Task<FloorPlanMeasurementResponse>
        SaveMeasurementAsync(
            int floorPlanId,
            SaveFloorPlanMeasurementRequest request,
            CancellationToken cancellationToken = default)
    {
        var floorPlan =
            await _db.FloorPlans
                .AsNoTracking()
                .FirstOrDefaultAsync(
                    x => x.Id == floorPlanId,
                    cancellationToken
                );


        if (floorPlan == null)
        {
            throw new KeyNotFoundException(
                $"Floor plan {floorPlanId} was not found."
            );
        }


        ValidateCoordinates(
            request,
            floorPlan
        );


        if (request.ActualDistance <= 0)
        {
            throw new InvalidOperationException(
                "Actual distance must be greater than zero."
            );
        }


        var deltaX =
            request.EndX - request.StartX;


        var deltaY =
            request.EndY - request.StartY;


        var pixelDistance =
            Math.Sqrt(
                deltaX * deltaX +
                deltaY * deltaY
            );


        if (pixelDistance < 1)
        {
            throw new InvalidOperationException(
                "The measurement line is too short."
            );
        }


        var normalizedUnit =
            request.Unit
                .Trim()
                .ToLowerInvariant();


        var actualDistanceMetres =
            ConvertToMetres(
                request.ActualDistance,
                normalizedUnit
            );


        var metresPerPixel =
            actualDistanceMetres /
            pixelDistance;


        var measurement =
            new FloorPlanMeasurementEntity
            {
                FloorPlanId =
                    floorPlanId,

                StartX =
                    request.StartX,

                StartY =
                    request.StartY,

                EndX =
                    request.EndX,

                EndY =
                    request.EndY,

                ActualDistance =
                    request.ActualDistance,

                Unit =
                    normalizedUnit,

                MetresPerPixel =
                    metresPerPixel
            };


        _db.FloorPlanMeasurements.Add(
            measurement
        );


        await _db.SaveChangesAsync(
            cancellationToken
        );


        return ToResponse(
            measurement
        );
    }


    // =========================================================
    // GET LATEST MEASUREMENT
    // =========================================================

    public async Task<FloorPlanMeasurementResponse?>
        GetLatestMeasurementAsync(
            int floorPlanId,
            CancellationToken cancellationToken = default)
    {
        var measurement =
            await _db.FloorPlanMeasurements
                .AsNoTracking()
                .Where(
                    x =>
                        x.FloorPlanId ==
                        floorPlanId
                )
                .OrderByDescending(
                    x => x.Id
                )
                .FirstOrDefaultAsync(
                    cancellationToken
                );


        if (measurement == null)
        {
            return null;
        }


        return ToResponse(
            measurement
        );
    }


    // =========================================================
    // GET ALL MEASUREMENTS
    // =========================================================

    public async Task<List<FloorPlanMeasurementResponse>>
        GetMeasurementsAsync(
            int floorPlanId,
            CancellationToken cancellationToken = default)
    {
        var measurements =
            await _db.FloorPlanMeasurements
                .AsNoTracking()
                .Where(
                    x =>
                        x.FloorPlanId ==
                        floorPlanId
                )
                .OrderByDescending(
                    x => x.Id
                )
                .ToListAsync(
                    cancellationToken
                );


        return measurements
            .Select(ToResponse)
            .ToList();
    }


    // =========================================================
    // HELPERS
    // =========================================================

    private static double ConvertToMetres(
        double distance,
        string unit)
    {
        return unit switch
        {
            "m" =>
                distance,

            "cm" =>
                distance / 100.0,

            "mm" =>
                distance / 1000.0,

            "ft" =>
                distance * 0.3048,

            _ =>
                throw new InvalidOperationException(
                    $"Unsupported measurement unit: {unit}"
                )
        };
    }


    private static void ValidateCoordinates(
        SaveFloorPlanMeasurementRequest request,
        FloorPlanEntity floorPlan)
    {
        ValidatePoint(
            request.StartX,
            request.StartY,
            floorPlan,
            "start"
        );


        ValidatePoint(
            request.EndX,
            request.EndY,
            floorPlan,
            "end"
        );
    }


    private static void ValidatePoint(
        double x,
        double y,
        FloorPlanEntity floorPlan,
        string pointName)
    {
        if (
            x < 0 ||
            y < 0 ||
            x > floorPlan.WidthPixels ||
            y > floorPlan.HeightPixels
        )
        {
            throw new InvalidOperationException(
                $"Measurement {pointName} point is outside the image."
            );
        }
    }


    private static FloorPlanMeasurementResponse ToResponse(
        FloorPlanMeasurementEntity measurement)
    {
        var deltaX =
            measurement.EndX -
            measurement.StartX;


        var deltaY =
            measurement.EndY -
            measurement.StartY;


        var pixelDistance =
            Math.Sqrt(
                deltaX * deltaX +
                deltaY * deltaY
            );


        return new FloorPlanMeasurementResponse
        {
            Id =
                measurement.Id,

            FloorPlanId =
                measurement.FloorPlanId,

            StartX =
                measurement.StartX,

            StartY =
                measurement.StartY,

            EndX =
                measurement.EndX,

            EndY =
                measurement.EndY,

            ActualDistance =
                measurement.ActualDistance,

            Unit =
                measurement.Unit,

            PixelDistance =
                pixelDistance,

            MetresPerPixel =
                measurement.MetresPerPixel ?? 0
        };
    }
}