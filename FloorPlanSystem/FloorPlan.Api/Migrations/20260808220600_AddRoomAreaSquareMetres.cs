using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace FloorPlan.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddRoomAreaSquareMetres : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<double>(
                name: "AreaSquareMetres",
                table: "Rooms",
                type: "REAL",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AreaSquareMetres",
                table: "Rooms");
        }
    }
}
