using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace FloorPlan.Api.Migrations
{
    public partial class AddBuildingBoundaryJson : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "BuildingBoundaryJson",
                table: "FloorPlanRevisions",
                type: "TEXT",
                nullable: false,
                defaultValue: "{}");
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "BuildingBoundaryJson",
                table: "FloorPlanRevisions");
        }
    }
}