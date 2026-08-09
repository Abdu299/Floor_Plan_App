using FloorPlan.Api.Models;
using FloorPlan.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace FloorPlan.Api.Controllers;


[ApiController]
[Route(
    "api/floorplans/{floorPlanId:int}/measurements"
)]
public class FloorPlanMeasurementsController
    : ControllerBase
{
    private readonly FloorPlanMeasurementService
        _measurementService;


    public FloorPlanMeasurementsController(
        FloorPlanMeasurementService measurementService)
    {
        _measurementService =
            measurementService;
    }


    // =========================================================
    // POST measurement
    // =========================================================

    [HttpPost]
    public async Task<IActionResult> SaveMeasurement(
        int floorPlanId,
        [FromBody] SaveFloorPlanMeasurementRequest request,
        CancellationToken cancellationToken)
    {
        try
        {
            var result =
                await _measurementService
                    .SaveMeasurementAsync(
                        floorPlanId,
                        request,
                        cancellationToken
                    );


            return Ok(result);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(
                new
                {
                    message = ex.Message
                }
            );
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(
                new
                {
                    message = ex.Message
                }
            );
        }
    }


    // =========================================================
    // GET all
    // =========================================================

    [HttpGet]
    public async Task<IActionResult> GetMeasurements(
        int floorPlanId,
        CancellationToken cancellationToken)
    {
        var result =
            await _measurementService
                .GetMeasurementsAsync(
                    floorPlanId,
                    cancellationToken
                );


        return Ok(result);
    }


    // =========================================================
    // GET latest
    // =========================================================

    [HttpGet("latest")]
    public async Task<IActionResult> GetLatestMeasurement(
        int floorPlanId,
        CancellationToken cancellationToken)
    {
        var result =
            await _measurementService
                .GetLatestMeasurementAsync(
                    floorPlanId,
                    cancellationToken
                );


        if (result == null)
        {
            return NotFound(
                new
                {
                    message =
                        "No scale has been set for this floor plan."
                }
            );
        }


        return Ok(result);
    }
}