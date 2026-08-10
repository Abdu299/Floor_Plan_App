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
//
// Local React development:
//
// http://localhost:5173
//
// Later Docker frontend:
//
// http://localhost:3000
//
// More origins can be supplied with:
//
// Frontend__Origins
//
// Example:
//
// Frontend__Origins=http://localhost:5173;http://localhost:3000
// =========================================================

var configuredOrigins =
    builder.Configuration[
        "Frontend:Origins"
    ];


var frontendOrigins =
    string.IsNullOrWhiteSpace(
        configuredOrigins
    )
        ? new[]
        {
            "http://localhost:5173",
            "http://localhost:3000"
        }
        : configuredOrigins
            .Split(
                ';',
                StringSplitOptions.RemoveEmptyEntries
                |
                StringSplitOptions.TrimEntries
            );


builder.Services.AddCors(
    options =>
    {
        options.AddPolicy(
            "Frontend",

            policy =>
            {
                policy
                    .WithOrigins(
                        frontendOrigins
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
//
// Local development can continue using appsettings.json.
//
// Docker will override the connection string using:
//
// ConnectionStrings__DefaultConnection
//
// Example:
//
// Data Source=/app/data/floorplan.db
// =========================================================

var connectionString =
    builder.Configuration
        .GetConnectionString(
            "DefaultConnection"
        );


if (
    string.IsNullOrWhiteSpace(
        connectionString
    )
)
{
    throw new InvalidOperationException(
        "Connection string 'DefaultConnection' is missing."
    );
}


builder.Services.AddDbContext<AppDbContext>(
    options =>
    {
        options.UseSqlite(
            connectionString
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
//
// Local:
//
// http://127.0.0.1:8000
//
// Docker:
//
// http://detector:8000
//
// Docker Compose will later set:
//
// PythonDetection__BaseUrl=http://detector:8000
// =========================================================

var pythonDetectionBaseUrl =
    builder.Configuration[
        "PythonDetection:BaseUrl"
    ];


if (
    string.IsNullOrWhiteSpace(
        pythonDetectionBaseUrl
    )
)
{
    pythonDetectionBaseUrl =
        "http://127.0.0.1:8000";
}


builder.Services.AddHttpClient<
    PythonDetectionClient
>(
    client =>
    {
        client.BaseAddress =
            new Uri(
                pythonDetectionBaseUrl
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
// CREATE REQUIRED DIRECTORIES
// =========================================================
//
// Docker will later mount persistent volumes here:
//
// /app/data
// /app/wwwroot/uploads
// =========================================================

var dataDirectory =
    Path.Combine(
        app.Environment.ContentRootPath,
        "data"
    );


Directory.CreateDirectory(
    dataDirectory
);


var uploadsDirectory =
    Path.Combine(
        app.Environment.WebRootPath
        ??
        Path.Combine(
            app.Environment.ContentRootPath,
            "wwwroot"
        ),

        "uploads"
    );


Directory.CreateDirectory(
    uploadsDirectory
);


// =========================================================
// APPLY DATABASE MIGRATIONS
// =========================================================
//
// This means users DO NOT need to manually run:
//
// dotnet ef database update
//
// when starting the application.
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
// HEALTH CHECK
// =========================================================
//
// Docker / Docker Compose can use this endpoint to check
// that the ASP.NET API started successfully.
// =========================================================

app.MapGet(
    "/health",

    () =>
        Results.Ok(
            new
            {
                status = "ok",
                service = "floorplan-api"
            }
        )
);


// =========================================================
// CONTROLLERS
// =========================================================

app.MapControllers();


// =========================================================
// START
// =========================================================

app.Run();