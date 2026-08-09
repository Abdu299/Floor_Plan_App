using Microsoft.EntityFrameworkCore;

namespace FloorPlan.Api.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(
        DbContextOptions<AppDbContext> options)
        : base(options)
    {
    }


    public DbSet<FloorPlanEntity> FloorPlans =>
        Set<FloorPlanEntity>();

    public DbSet<FloorPlanRevisionEntity> FloorPlanRevisions =>
        Set<FloorPlanRevisionEntity>();

    public DbSet<FloorPlanMeasurementEntity> FloorPlanMeasurements =>
        Set<FloorPlanMeasurementEntity>();

    public DbSet<RoomEntity> Rooms =>
        Set<RoomEntity>();

    public DbSet<DoorEntity> Doors =>
        Set<DoorEntity>();

    public DbSet<WindowEntity> Windows =>
        Set<WindowEntity>();

    public DbSet<OpeningEntity> Openings =>
        Set<OpeningEntity>();


    protected override void OnModelCreating(
        ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);


        // -------------------------------------------------
        // FloorPlan
        // -------------------------------------------------

        modelBuilder.Entity<FloorPlanEntity>()
            .HasMany(x => x.Revisions)
            .WithOne(x => x.FloorPlan)
            .HasForeignKey(x => x.FloorPlanId)
            .OnDelete(DeleteBehavior.Cascade);


        modelBuilder.Entity<FloorPlanEntity>()
            .HasMany(x => x.Measurements)
            .WithOne(x => x.FloorPlan)
            .HasForeignKey(x => x.FloorPlanId)
            .OnDelete(DeleteBehavior.Cascade);


        // -------------------------------------------------
        // Revision
        // -------------------------------------------------

        modelBuilder.Entity<FloorPlanRevisionEntity>()
            .Property(x => x.Source)
            .HasConversion<string>();


        modelBuilder.Entity<FloorPlanRevisionEntity>()
            .Property(x => x.Status)
            .HasConversion<string>();


        modelBuilder.Entity<FloorPlanRevisionEntity>()
            .HasIndex(x => new
            {
                x.FloorPlanId,
                x.RevisionNumber
            })
            .IsUnique();


        // -------------------------------------------------
        // Rooms
        // -------------------------------------------------

        modelBuilder.Entity<RoomEntity>()
            .HasOne(x => x.Revision)
            .WithMany(x => x.Rooms)
            .HasForeignKey(x => x.FloorPlanRevisionId)
            .OnDelete(DeleteBehavior.Cascade);


        modelBuilder.Entity<RoomEntity>()
            .HasIndex(x => new
            {
                x.FloorPlanRevisionId,
                x.SourceElementId
            })
            .IsUnique();


        // -------------------------------------------------
        // Doors
        // -------------------------------------------------

        modelBuilder.Entity<DoorEntity>()
            .HasOne(x => x.Revision)
            .WithMany(x => x.Doors)
            .HasForeignKey(x => x.FloorPlanRevisionId)
            .OnDelete(DeleteBehavior.Cascade);


        modelBuilder.Entity<DoorEntity>()
            .HasOne(x => x.Room1)
            .WithMany()
            .HasForeignKey(x => x.Room1Id)
            .OnDelete(DeleteBehavior.Restrict);


        modelBuilder.Entity<DoorEntity>()
            .HasOne(x => x.Room2)
            .WithMany()
            .HasForeignKey(x => x.Room2Id)
            .OnDelete(DeleteBehavior.Restrict);


        // -------------------------------------------------
        // Windows
        // -------------------------------------------------

        modelBuilder.Entity<WindowEntity>()
            .HasOne(x => x.Revision)
            .WithMany(x => x.Windows)
            .HasForeignKey(x => x.FloorPlanRevisionId)
            .OnDelete(DeleteBehavior.Cascade);


        // -------------------------------------------------
        // Openings
        // -------------------------------------------------

        modelBuilder.Entity<OpeningEntity>()
            .HasOne(x => x.Revision)
            .WithMany(x => x.Openings)
            .HasForeignKey(x => x.FloorPlanRevisionId)
            .OnDelete(DeleteBehavior.Cascade);


        modelBuilder.Entity<OpeningEntity>()
            .HasOne(x => x.Room1)
            .WithMany()
            .HasForeignKey(x => x.Room1Id)
            .OnDelete(DeleteBehavior.Restrict);


        modelBuilder.Entity<OpeningEntity>()
            .HasOne(x => x.Room2)
            .WithMany()
            .HasForeignKey(x => x.Room2Id)
            .OnDelete(DeleteBehavior.Restrict);
    }
}