# ============================================================
# FloorPlan.Api
# ASP.NET Core 10 Docker Image
# ============================================================


# ============================================================
# BUILD STAGE
# ============================================================
#
# The SDK image contains everything required to:
#
# - restore NuGet packages
# - compile the application
# - publish the application
#
# It will NOT be included in the final runtime image.
# ============================================================

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build


WORKDIR /src


# ============================================================
# RESTORE
# ============================================================
#
# Copy the project file first.
#
# Docker can cache the NuGet restore layer as long as the
# .csproj file has not changed.
# ============================================================

COPY FloorPlan.Api.csproj ./


RUN dotnet restore \
    FloorPlan.Api.csproj


# ============================================================
# COPY SOURCE
# ============================================================

COPY . ./


# ============================================================
# PUBLISH
# ============================================================

RUN dotnet publish \
    FloorPlan.Api.csproj \
    -c Release \
    -o /app/publish \
    --no-restore


# ============================================================
# RUNTIME STAGE
# ============================================================
#
# This image contains only the ASP.NET runtime.
#
# It is much smaller than shipping the full SDK.
# ============================================================

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime


WORKDIR /app


# ============================================================
# ASP.NET CONFIGURATION
# ============================================================
#
# Listen on every network interface inside the container.
#
# Docker maps the host port to container port 8080.
# ============================================================

ENV ASPNETCORE_URLS=http://+:8080


# ============================================================
# APPLICATION DIRECTORIES
# ============================================================
#
# /app/data
#     SQLite database
#
# /app/wwwroot/uploads
#     uploaded floor-plan images
#
# Docker volumes will later be mounted here.
# ============================================================

RUN mkdir -p \
    /app/data \
    /app/wwwroot/uploads


# ============================================================
# COPY PUBLISHED APPLICATION
# ============================================================

COPY --from=build \
    /app/publish \
    ./


# ============================================================
# API PORT
# ============================================================

EXPOSE 8080


# ============================================================
# START ASP.NET
# ============================================================

ENTRYPOINT ["dotnet", "FloorPlan.Api.dll"]