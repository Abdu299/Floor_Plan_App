using FloorPlan.Api.Models;

namespace FloorPlan.Api.Services;


// =========================================================
// VALIDATION RESULT
// =========================================================

public class FloorPlanSaveValidationResult
{
    // Floor-plan validity without considering
    // the manually entered areas.
    public bool Valid { get; set; }


    public bool HasBathroom { get; set; }

    public bool HasKitchen { get; set; }


    // True when there is at least:
    //
    // Door OR Opening
    public bool HasConnection { get; set; }


    // True only when everything needed
    // for saving is valid.
    public bool CanSave { get; set; }


    public List<string> Errors { get; set; } =
        [];
}


// =========================================================
// VALIDATION SERVICE
// =========================================================

public class FloorPlanValidationService
{
    // =====================================================
    // BATHROOM NAMES
    // =====================================================

    private static readonly HashSet<string>
        BathroomNames =
        new(
            new[]
            {
                "bath",
                "bathroom",
                "full bathroom",
                "half bathroom",
                "ba",
                "bth",
                "main bathroom",
                "family bathroom",
                "common bathroom",
                "shared bathroom",
                "private bathroom",
                "master bathroom",
                "primary bathroom",
                "toilet",
                "wc",
                "water closet",
                "lavatory",
                "half bath",
                "guest toilet",
                "restroom",
                "bathroom/laundry",
                "bath/laundry",
                "bath/wc",
                "toilet/shower",
                "wc/shower",
                "shower",
                "shower room",
                "p.bath",
                "g.bath",
                "toil"
            },

            StringComparer.OrdinalIgnoreCase
        );


    // =====================================================
    // KITCHEN NAMES
    // =====================================================

    private static readonly HashSet<string>
        KitchenNames =
        new(
            new[]
            {
                "kitchen",
                "kitch",
                "kit",
                "kitchenette",
                "kitchen area",
                "kitchen zone",
                "cooking area",
                "cooking zone",
                "open kitchen",
                "open-plan kitchen",
                "open plan kitchen",
                "open kitchen area",
                "open-plan kitchen/living room",
                "open plan kitchen/living room",
                "kitchen/living room",
                "kitchen living room",
                "living room/kitchen",
                "living kitchen",
                "kitchen/dining room",
                "kitchen dining room",
                "dining room/kitchen",
                "kitchen/dining",
                "kitchen diner",
                "eat-in kitchen",
                "kitchen/family room",
                "kitchen/lounge",
                "lounge/kitchen",
                "studio kitchen",
                "compact kitchen",
                "small kitchen",
                "galley kitchen",
                "main kitchen",
                "shared kitchen",
                "communal kitchen",
                "service kitchen",
                "prep kitchen",
                "preparation kitchen",
                "secondary kitchen",
                "back kitchen",
                "butler's kitchen",
                "scullery",
                "pantry kitchen",
                "summer kitchen",
                "chef's kitchen",
                "commercial kitchen",
                "staff kitchen",
                "break room kitchen",
                "tea kitchen",
                "tea point",
                "refreshment area",
                "k",
                "kit.",
                "kitch.",
                "kt",
                "kitchenette/living room",
                "living room/kitchenette",
                "kitchenette/dining",
                "kitchenette area"
            },

            StringComparer.OrdinalIgnoreCase
        );


    // =========================================================
    // VALIDATE
    // =========================================================

    public FloorPlanSaveValidationResult Validate(
        SaveRevisionRequest request)
    {
        var result =
            new FloorPlanSaveValidationResult();


        // =====================================================
        // ROOMS
        // =====================================================

        var hasRooms =
            request.Rooms.Count > 0;


        if (!hasRooms)
        {
            result.Errors.Add(
                "The floor plan does not contain any rooms."
            );
        }


        // =====================================================
        // CONNECTION
        //
        // Door OR opening.
        //
        // They are NOT both required.
        // =====================================================

        var hasDoors =
            request.Doors.Count > 0;


        var hasOpenings =
            request.Openings.Count > 0;


        result.HasConnection =
            hasDoors
            ||
            hasOpenings;


        if (!result.HasConnection)
        {
            result.Errors.Add(
                "The floor plan must contain at least one door or one opening."
            );
        }


        // =====================================================
        // BATHROOM + KITCHEN
        // =====================================================

        foreach (
            var room
            in request.Rooms
        )
        {
            var normalizedName =
                NormalizeRoomName(
                    room.Name
                );


            if (
                BathroomNames.Contains(
                    normalizedName
                )
            )
            {
                result.HasBathroom =
                    true;
            }


            if (
                KitchenNames.Contains(
                    normalizedName
                )
            )
            {
                result.HasKitchen =
                    true;
            }
        }


        if (!result.HasBathroom)
        {
            result.Errors.Add(
                "The floor plan must contain at least one bathroom."
            );
        }


        if (!result.HasKitchen)
        {
            result.Errors.Add(
                "The floor plan must contain at least one kitchen or cooking area."
            );
        }


        // =====================================================
        // FLOOR PLAN VALIDITY
        //
        // IMPORTANT:
        //
        // We require:
        //
        // Rooms
        // Bathroom
        // Kitchen
        // Door OR Opening
        // =====================================================

        result.Valid =
            hasRooms
            &&
            result.HasConnection
            &&
            result.HasBathroom
            &&
            result.HasKitchen;


        // =====================================================
        // ROOM AREAS
        // =====================================================

        foreach (
            var room
            in request.Rooms
        )
        {
            if (
                room.AreaSquareMetres == null
                ||
                !double.IsFinite(
                    room.AreaSquareMetres.Value
                )
                ||
                room.AreaSquareMetres.Value <= 0
            )
            {
                result.Errors.Add(
                    $"Room {room.Id} ({room.Name}) is missing a valid area."
                );
            }
        }


        // =====================================================
        // ALL ROOMS HAVE VALID AREA
        // =====================================================

        var allRoomsHaveArea =
            hasRooms
            &&
            request.Rooms.All(
                room =>
                    room.AreaSquareMetres != null
                    &&
                    double.IsFinite(
                        room.AreaSquareMetres.Value
                    )
                    &&
                    room.AreaSquareMetres.Value > 0
            );


        // =====================================================
        // CAN SAVE
        // =====================================================

        result.CanSave =
            result.Valid
            &&
            allRoomsHaveArea;


        return result;
    }


    // =========================================================
    // NORMALIZE ROOM NAME
    // =========================================================

    private static string NormalizeRoomName(
        string? name)
    {
        if (
            string.IsNullOrWhiteSpace(
                name
            )
        )
        {
            return string.Empty;
        }


        return string.Join(
            " ",

            name
                .Trim()
                .ToLowerInvariant()
                .Split(
                    ' ',
                    StringSplitOptions
                        .RemoveEmptyEntries
                )
        );
    }
}