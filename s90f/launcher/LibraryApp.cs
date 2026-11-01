public sealed class LibraryApp
{
	public string Name { get; set; }

	public string Id { get; set; }

	public string Asset { get; set; }

	public string Description { get; set; }

	public string Fit { get; set; } = "cover";


	public string Background { get; set; } = "#FFFFFF";


	public int Width { get; set; }

	public int Height { get; set; }

	public float[] Crop { get; set; }

	public bool Utility { get; set; }
}
