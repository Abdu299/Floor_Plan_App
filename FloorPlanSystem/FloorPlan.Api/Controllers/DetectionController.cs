using FloorPlan.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace FloorPlan.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class DetectionController : ControllerBase
{
    private readonly PythonDetectionClient
        _pythonDetectionClient;

    private readonly FloorPlanPersistenceService
        _persistenceService;


    public DetectionController(
        PythonDetectionClient pythonDetectionClient,
        FloorPlanPersistenceService persistenceService)
    {
        _pythonDetectionClient =
            pythonDetectionClient;

        _persistenceService =
            persistenceService;
    }


    [HttpPost]
    public async Task<IActionResult> Detect(
        [FromForm] IFormFile image,
        CancellationToken cancellationToken)
    {
        if (image == null || image.Length == 0)
        {
            return BadRequest(
                new
                {
                    message =
                        "Please upload a floor plan image."
                }
            );
        }


        try
        {
            // ---------------------------------------------
            // Python AI detection
            // ---------------------------------------------

            var detection =
                await _pythonDetectionClient
                    .DetectFloorPlanAsync(
                        image,
                        cancellationToken
                    );


            // ---------------------------------------------
            // Save image + AI revision to database
            // ---------------------------------------------

            var saved =
                await _persistenceService
                    .SaveAiDetectionAsync(
                        image,
                        detection,
                        cancellationToken
                    );


            // ---------------------------------------------
            // Response
            // ---------------------------------------------

            return Ok(
                new
                {
                    floorPlanId =
                        saved.FloorPlanId,

                    revisionId =
                        saved.RevisionId,

                    imagePath =
                        saved.ImagePath,

                    detection
                }
            );
        }
        catch (Exception ex)
        {
            return StatusCode(
                StatusCodes
                    .Status500InternalServerError,

                new
                {
                    message =
                        "Floor plan detection failed.",

                    error =
                        ex.Message
                }
            );
        }
    }
}