using FloorPlan.Api.Data;
using FloorPlan.Api.Services;
using Microsoft.EntityFrameworkCore;


var builder =
    WebApplication.CreateBuilder(args);


// =========================================================
// CONTROLLERS
// =========================================================

builder.Services.AddControllers();


// =========================================================
// OPEN API
// =========================================================

builder.Services.AddOpenApi();


// =========================================================
// CORS
// =========================================================

builder.Services.AddCors(
    options =>
    {
        options.AddPolicy(
            "Frontend",

            policy =>
            {
                policy
                    .WithOrigins(
                        "http://localhost:5173"
                    )

                    .AllowAnyHeader()

                    .AllowAnyMethod();
            }
        );
    }
);


// =========================================================
// DATABASE
// =========================================================

builder.Services.AddDbContext<AppDbContext>(
    options =>
    {
        options.UseSqlite(
            builder.Configuration
                .GetConnectionString(
                    "DefaultConnection"
                )
        );
    }
);


// =========================================================
// APPLICATION SERVICES
// =========================================================

builder.Services.AddScoped<
    FloorPlanPersistenceService
>();


builder.Services.AddScoped<
    FloorPlanQueryService
>();


builder.Services.AddScoped<
    FloorPlanValidationService
>();


builder.Services.AddScoped<
    FloorPlanRevisionService
>();


builder.Services.AddScoped<
    FloorPlanDeleteService
>();


// =========================================================
// PYTHON DETECTION SERVICE
// =========================================================

builder.Services.AddHttpClient<
    PythonDetectionClient
>(
    client =>
    {
        client.BaseAddress =
            new Uri(
                "http://127.0.0.1:8000"
            );


        client.Timeout =
            TimeSpan.FromMinutes(
                5
            );
    }
);


// =========================================================
// BUILD APP
// =========================================================

var app =
    builder.Build();


// =========================================================
// APPLY DATABASE MIGRATIONS
// =========================================================

using (
    var scope =
        app.Services.CreateScope()
)
{
    var db =
        scope.ServiceProvider
            .GetRequiredService<
                AppDbContext
            >();


    db.Database.Migrate();
}


// =========================================================
// DEVELOPMENT
// =========================================================

if (
    app.Environment.IsDevelopment()
)
{
    app.MapOpenApi();
}


// =========================================================
// STATIC FILES
// =========================================================

app.UseStaticFiles();


// =========================================================
// CORS
// =========================================================

app.UseCors(
    "Frontend"
);


// =========================================================
// HTTPS
// =========================================================

app.UseHttpsRedirection();


// =========================================================
// CONTROLLERS
// =========================================================

app.MapControllers();


// =========================================================
// START
// =========================================================

app.Run();