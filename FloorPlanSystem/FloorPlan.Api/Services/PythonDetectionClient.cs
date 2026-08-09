using System.Net.Http.Headers;
using System.Text.Json;
using FloorPlan.Api.Models;

namespace FloorPlan.Api.Services;

public class PythonDetectionClient
{
    private readonly HttpClient _httpClient;

    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    public PythonDetectionClient(HttpClient httpClient)
    {
        _httpClient = httpClient;
    }


    public async Task<FloorPlanDetectionResult> DetectFloorPlanAsync(
        IFormFile image,
        CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();

        await using var stream = image.OpenReadStream();

        using var imageContent = new StreamContent(stream);

        if (!string.IsNullOrWhiteSpace(image.ContentType))
        {
            imageContent.Headers.ContentType =
                new MediaTypeHeaderValue(image.ContentType);
        }

        form.Add(
            imageContent,
            "image",
            image.FileName
        );


        using var response = await _httpClient.PostAsync(
            "/detect",
            form,
            cancellationToken
        );


        var responseBody =
            await response.Content.ReadAsStringAsync(
                cancellationToken
            );


        if (!response.IsSuccessStatusCode)
        {
            throw new Exception(
                $"Python detection failed. " +
                $"Status: {(int)response.StatusCode}. " +
                $"Response: {responseBody}"
            );
        }
        Console.WriteLine("RAW PYTHON RESPONSE:");
        Console.WriteLine(responseBody);


        var result =
            JsonSerializer.Deserialize<FloorPlanDetectionResult>(
                responseBody,
                _jsonOptions
            );


        if (result == null)
        {
            throw new Exception(
                "Python returned an empty or invalid detection result."
            );
        }


        return result;
    }
}