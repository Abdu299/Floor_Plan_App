using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace FloorPlan.Api.Migrations
{
    /// <inheritdoc />
    public partial class InitialFloorPlanDatabase : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "FloorPlans",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    OriginalFileName = table.Column<string>(type: "TEXT", nullable: false),
                    ImagePath = table.Column<string>(type: "TEXT", nullable: false),
                    WidthPixels = table.Column<int>(type: "INTEGER", nullable: false),
                    HeightPixels = table.Column<int>(type: "INTEGER", nullable: false),
                    CreatedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FloorPlans", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "FloorPlanMeasurements",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    FloorPlanId = table.Column<int>(type: "INTEGER", nullable: false),
                    StartX = table.Column<double>(type: "REAL", nullable: false),
                    StartY = table.Column<double>(type: "REAL", nullable: false),
                    EndX = table.Column<double>(type: "REAL", nullable: false),
                    EndY = table.Column<double>(type: "REAL", nullable: false),
                    ActualDistance = table.Column<double>(type: "REAL", nullable: false),
                    Unit = table.Column<string>(type: "TEXT", nullable: false),
                    MetresPerPixel = table.Column<double>(type: "REAL", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FloorPlanMeasurements", x => x.Id);
                    table.ForeignKey(
                        name: "FK_FloorPlanMeasurements_FloorPlans_FloorPlanId",
                        column: x => x.FloorPlanId,
                        principalTable: "FloorPlans",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "FloorPlanRevisions",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    FloorPlanId = table.Column<int>(type: "INTEGER", nullable: false),
                    RevisionNumber = table.Column<int>(type: "INTEGER", nullable: false),
                    Source = table.Column<string>(type: "TEXT", nullable: false),
                    Status = table.Column<string>(type: "TEXT", nullable: false),
                    BasedOnRevisionId = table.Column<int>(type: "INTEGER", nullable: true),
                    Valid = table.Column<bool>(type: "INTEGER", nullable: false),
                    HasBathroom = table.Column<bool>(type: "INTEGER", nullable: false),
                    HasKitchen = table.Column<bool>(type: "INTEGER", nullable: false),
                    CreatedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_FloorPlanRevisions", x => x.Id);
                    table.ForeignKey(
                        name: "FK_FloorPlanRevisions_FloorPlans_FloorPlanId",
                        column: x => x.FloorPlanId,
                        principalTable: "FloorPlans",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Rooms",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    FloorPlanRevisionId = table.Column<int>(type: "INTEGER", nullable: false),
                    SourceElementId = table.Column<int>(type: "INTEGER", nullable: false),
                    Name = table.Column<string>(type: "TEXT", nullable: false),
                    Confidence = table.Column<double>(type: "REAL", nullable: true),
                    PolygonJson = table.Column<string>(type: "TEXT", nullable: false),
                    CentroidX = table.Column<double>(type: "REAL", nullable: false),
                    CentroidY = table.Column<double>(type: "REAL", nullable: false),
                    AreaPixels = table.Column<double>(type: "REAL", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Rooms", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Rooms_FloorPlanRevisions_FloorPlanRevisionId",
                        column: x => x.FloorPlanRevisionId,
                        principalTable: "FloorPlanRevisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Windows",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    FloorPlanRevisionId = table.Column<int>(type: "INTEGER", nullable: false),
                    SourceElementId = table.Column<int>(type: "INTEGER", nullable: false),
                    PolygonJson = table.Column<string>(type: "TEXT", nullable: false),
                    BboxX1 = table.Column<double>(type: "REAL", nullable: true),
                    BboxY1 = table.Column<double>(type: "REAL", nullable: true),
                    BboxX2 = table.Column<double>(type: "REAL", nullable: true),
                    BboxY2 = table.Column<double>(type: "REAL", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Windows", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Windows_FloorPlanRevisions_FloorPlanRevisionId",
                        column: x => x.FloorPlanRevisionId,
                        principalTable: "FloorPlanRevisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Doors",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    FloorPlanRevisionId = table.Column<int>(type: "INTEGER", nullable: false),
                    SourceElementId = table.Column<int>(type: "INTEGER", nullable: false),
                    PolygonJson = table.Column<string>(type: "TEXT", nullable: false),
                    BboxX1 = table.Column<double>(type: "REAL", nullable: true),
                    BboxY1 = table.Column<double>(type: "REAL", nullable: true),
                    BboxX2 = table.Column<double>(type: "REAL", nullable: true),
                    BboxY2 = table.Column<double>(type: "REAL", nullable: true),
                    Confidence = table.Column<double>(type: "REAL", nullable: true),
                    Room1Id = table.Column<int>(type: "INTEGER", nullable: false),
                    Room2Id = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Doors", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Doors_FloorPlanRevisions_FloorPlanRevisionId",
                        column: x => x.FloorPlanRevisionId,
                        principalTable: "FloorPlanRevisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Doors_Rooms_Room1Id",
                        column: x => x.Room1Id,
                        principalTable: "Rooms",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_Doors_Rooms_Room2Id",
                        column: x => x.Room2Id,
                        principalTable: "Rooms",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "Openings",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    FloorPlanRevisionId = table.Column<int>(type: "INTEGER", nullable: false),
                    SourceElementId = table.Column<int>(type: "INTEGER", nullable: false),
                    PolygonJson = table.Column<string>(type: "TEXT", nullable: false),
                    BboxX1 = table.Column<double>(type: "REAL", nullable: true),
                    BboxY1 = table.Column<double>(type: "REAL", nullable: true),
                    BboxX2 = table.Column<double>(type: "REAL", nullable: true),
                    BboxY2 = table.Column<double>(type: "REAL", nullable: true),
                    Room1Id = table.Column<int>(type: "INTEGER", nullable: false),
                    Room2Id = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Openings", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Openings_FloorPlanRevisions_FloorPlanRevisionId",
                        column: x => x.FloorPlanRevisionId,
                        principalTable: "FloorPlanRevisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Openings_Rooms_Room1Id",
                        column: x => x.Room1Id,
                        principalTable: "Rooms",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_Openings_Rooms_Room2Id",
                        column: x => x.Room2Id,
                        principalTable: "Rooms",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Doors_FloorPlanRevisionId",
                table: "Doors",
                column: "FloorPlanRevisionId");

            migrationBuilder.CreateIndex(
                name: "IX_Doors_Room1Id",
                table: "Doors",
                column: "Room1Id");

            migrationBuilder.CreateIndex(
                name: "IX_Doors_Room2Id",
                table: "Doors",
                column: "Room2Id");

            migrationBuilder.CreateIndex(
                name: "IX_FloorPlanMeasurements_FloorPlanId",
                table: "FloorPlanMeasurements",
                column: "FloorPlanId");

            migrationBuilder.CreateIndex(
                name: "IX_FloorPlanRevisions_FloorPlanId_RevisionNumber",
                table: "FloorPlanRevisions",
                columns: new[] { "FloorPlanId", "RevisionNumber" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Openings_FloorPlanRevisionId",
                table: "Openings",
                column: "FloorPlanRevisionId");

            migrationBuilder.CreateIndex(
                name: "IX_Openings_Room1Id",
                table: "Openings",
                column: "Room1Id");

            migrationBuilder.CreateIndex(
                name: "IX_Openings_Room2Id",
                table: "Openings",
                column: "Room2Id");

            migrationBuilder.CreateIndex(
                name: "IX_Rooms_FloorPlanRevisionId_SourceElementId",
                table: "Rooms",
                columns: new[] { "FloorPlanRevisionId", "SourceElementId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Windows_FloorPlanRevisionId",
                table: "Windows",
                column: "FloorPlanRevisionId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Doors");

            migrationBuilder.DropTable(
                name: "FloorPlanMeasurements");

            migrationBuilder.DropTable(
                name: "Openings");

            migrationBuilder.DropTable(
                name: "Windows");

            migrationBuilder.DropTable(
                name: "Rooms");

            migrationBuilder.DropTable(
                name: "FloorPlanRevisions");

            migrationBuilder.DropTable(
                name: "FloorPlans");
        }
    }
}
