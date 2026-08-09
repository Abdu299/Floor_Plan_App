using FloorPlan.Api.Data;
using Microsoft.EntityFrameworkCore;

namespace FloorPlan.Api.Services;


public class FloorPlanDeleteService
{
    private readonly AppDbContext _db;

    private readonly IWebHostEnvironment _environment;


    public FloorPlanDeleteService(
        AppDbContext db,
        IWebHostEnvironment environment)
    {
        _db =
            db;

        _environment =
            environment;
    }


    // =========================================================
    // DELETE FLOOR PLAN
    // =========================================================

    public async Task<bool> DeleteFloorPlanAsync(
        int floorPlanId,
        CancellationToken cancellationToken = default)
    {
        var floorPlan =
            await _db.FloorPlans
                .AsNoTracking()

                .FirstOrDefaultAsync(
                    x =>
                        x.Id ==
                        floorPlanId,

                    cancellationToken
                );


        if (floorPlan == null)
        {
            return false;
        }


        var revisionIds =
            await _db.FloorPlanRevisions
                .AsNoTracking()

                .Where(
                    x =>
                        x.FloorPlanId ==
                        floorPlanId
                )

                .Select(
                    x => x.Id
                )

                .ToListAsync(
                    cancellationToken
                );


        await using var transaction =
            await _db.Database
                .BeginTransactionAsync(
                    cancellationToken
                );


        try
        {
            // =================================================
            // DELETE REVISION CHILDREN FIRST
            // =================================================

            if (
                revisionIds.Count > 0
            )
            {
                await _db.Doors
                    .Where(
                        x =>
                            revisionIds.Contains(
                                x.FloorPlanRevisionId
                            )
                    )
                    .ExecuteDeleteAsync(
                        cancellationToken
                    );


                await _db.Openings
                    .Where(
                        x =>
                            revisionIds.Contains(
                                x.FloorPlanRevisionId
                            )
                    )
                    .ExecuteDeleteAsync(
                        cancellationToken
                    );


                await _db.Windows
                    .Where(
                        x =>
                            revisionIds.Contains(
                                x.FloorPlanRevisionId
                            )
                    )
                    .ExecuteDeleteAsync(
                        cancellationToken
                    );


                await _db.Rooms
                    .Where(
                        x =>
                            revisionIds.Contains(
                                x.FloorPlanRevisionId
                            )
                    )
                    .ExecuteDeleteAsync(
                        cancellationToken
                    );


                await _db.FloorPlanRevisions
                    .Where(
                        x =>
                            x.FloorPlanId ==
                            floorPlanId
                    )
                    .ExecuteDeleteAsync(
                        cancellationToken
                    );
            }


            // =================================================
            // DELETE OLD MEASUREMENTS IF ANY EXIST
            // =================================================

            await _db.FloorPlanMeasurements
                .Where(
                    x =>
                        x.FloorPlanId ==
                        floorPlanId
                )
                .ExecuteDeleteAsync(
                    cancellationToken
                );


            // =================================================
            // DELETE FLOOR PLAN
            // =================================================

            await _db.FloorPlans
                .Where(
                    x =>
                        x.Id ==
                        floorPlanId
                )
                .ExecuteDeleteAsync(
                    cancellationToken
                );


            await transaction.CommitAsync(
                cancellationToken
            );
        }
        catch
        {
            await transaction.RollbackAsync(
                cancellationToken
            );

            throw;
        }


        // =====================================================
        // DELETE IMAGE FILE
        // =====================================================

        DeleteImageFile(
            floorPlan.ImagePath
        );


        return true;
    }


    // =========================================================
    // DELETE PHYSICAL IMAGE
    // =========================================================

    private void DeleteImageFile(
        string imagePath)
    {
        if (
            string.IsNullOrWhiteSpace(
                imagePath
            )
        )
        {
            return;
        }


        try
        {
            var webRoot =
                _environment.WebRootPath;


            if (
                string.IsNullOrWhiteSpace(
                    webRoot
                )
            )
            {
                webRoot =
                    Path.Combine(
                        _environment.ContentRootPath,
                        "wwwroot"
                    );
            }


            var relativePath =
                imagePath
                    .TrimStart('/')
                    .Replace(
                        '/',
                        Path.DirectorySeparatorChar
                    );


            var fullPath =
                Path.Combine(
                    webRoot,
                    relativePath
                );


            if (
                File.Exists(
                    fullPath
                )
            )
            {
                File.Delete(
                    fullPath
                );
            }
        }
        catch (Exception ex)
        {
            // Database deletion already succeeded.
            // Do not undo it just because file cleanup failed.

            Console.WriteLine(
                $"Could not delete floor plan image: {ex.Message}"
            );
        }
    }
}