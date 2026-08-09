using FloorPlan.Api.Models;
using FloorPlan.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace FloorPlan.Api.Controllers;


[ApiController]
[Route("api/floorplans")]
public class FloorPlansController : ControllerBase
{
    private readonly FloorPlanQueryService
        _queryService;


    private readonly FloorPlanRevisionService
        _revisionService;


    private readonly FloorPlanDeleteService
        _deleteService;


    public FloorPlansController(
        FloorPlanQueryService queryService,
        FloorPlanRevisionService revisionService,
        FloorPlanDeleteService deleteService)
    {
        _queryService =
            queryService;

        _revisionService =
            revisionService;

        _deleteService =
            deleteService;
    }


    // =========================================================
    // GET ALL FLOOR PLANS
    //
    // GET /api/floorplans
    // =========================================================

    [HttpGet]
    public async Task<IActionResult> GetFloorPlans(
        CancellationToken cancellationToken)
    {
        var floorPlans =
            await _queryService
                .GetFloorPlansAsync(
                    cancellationToken
                );


        return Ok(
            floorPlans
        );
    }


    // =========================================================
    // GET LATEST REVISION
    //
    // GET /api/floorplans/11
    // =========================================================

    [HttpGet("{floorPlanId:int}")]
    public async Task<IActionResult> GetFloorPlan(
        int floorPlanId,
        CancellationToken cancellationToken)
    {
        var result =
            await _queryService
                .GetFloorPlanAsync(
                    floorPlanId,
                    cancellationToken
                );


        if (
            result == null
        )
        {
            return NotFound(
                new
                {
                    message =
                        $"Floor plan {floorPlanId} was not found."
                }
            );
        }


        return Ok(
            result
        );
    }


    // =========================================================
    // GET REVISION HISTORY
    //
    // GET /api/floorplans/11/revisions
    // =========================================================

    [HttpGet("{floorPlanId:int}/revisions")]
    public async Task<IActionResult> GetRevisions(
        int floorPlanId,
        CancellationToken cancellationToken)
    {
        var revisions =
            await _queryService
                .GetRevisionHistoryAsync(
                    floorPlanId,
                    cancellationToken
                );


        return Ok(
            revisions
        );
    }


    // =========================================================
    // GET SPECIFIC REVISION
    //
    // GET /api/floorplans/11/revisions/1
    // =========================================================

    [HttpGet(
        "{floorPlanId:int}/revisions/{revisionNumber:int}"
    )]
    public async Task<IActionResult> GetRevision(
        int floorPlanId,
        int revisionNumber,
        CancellationToken cancellationToken)
    {
        var result =
            await _queryService
                .GetRevisionAsync(
                    floorPlanId,
                    revisionNumber,
                    cancellationToken
                );


        if (
            result == null
        )
        {
            return NotFound(
                new
                {
                    message =
                        $"Revision {revisionNumber} for floor plan " +
                        $"{floorPlanId} was not found."
                }
            );
        }


        return Ok(
            result
        );
    }


    // =========================================================
    // SAVE USER CORRECTIONS
    //
    // POST /api/floorplans/11/revisions
    // =========================================================

    [HttpPost("{floorPlanId:int}/revisions")]
    public async Task<IActionResult> SaveRevision(
        int floorPlanId,
        [FromBody] SaveRevisionRequest request,
        CancellationToken cancellationToken)
    {
        try
        {
            var result =
                await _revisionService
                    .SaveUserRevisionAsync(
                        floorPlanId,
                        request,
                        cancellationToken
                    );


            return Ok(
                result
            );
        }
        catch (
            KeyNotFoundException ex
        )
        {
            return NotFound(
                new
                {
                    message =
                        ex.Message
                }
            );
        }
        catch (
            InvalidOperationException ex
        )
        {
            return BadRequest(
                new
                {
                    message =
                        ex.Message
                }
            );
        }
        catch (Exception ex)
        {
            Console.WriteLine(
                ex
            );


            return StatusCode(
                StatusCodes
                    .Status500InternalServerError,

                new
                {
                    message =
                        "An unexpected error occurred while saving the revision.",

                    error =
                        ex.Message
                }
            );
        }
    }


    // =========================================================
    // DELETE FLOOR PLAN
    //
    // DELETE /api/floorplans/11
    // =========================================================

    [HttpDelete("{floorPlanId:int}")]
    public async Task<IActionResult> DeleteFloorPlan(
        int floorPlanId,
        CancellationToken cancellationToken)
    {
        try
        {
            var deleted =
                await _deleteService
                    .DeleteFloorPlanAsync(
                        floorPlanId,
                        cancellationToken
                    );


            if (
                !deleted
            )
            {
                return NotFound(
                    new
                    {
                        message =
                            $"Floor plan {floorPlanId} was not found."
                    }
                );
            }


            return NoContent();
        }
        catch (Exception ex)
        {
            Console.WriteLine(
                ex
            );


            return StatusCode(
                StatusCodes
                    .Status500InternalServerError,

                new
                {
                    message =
                        "Could not delete the floor plan.",

                    error =
                        ex.Message
                }
            );
        }
    }
}