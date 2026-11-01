using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

public static class AppLibrary
{
	public const int Columns = 5;

	public const int Rows = 3;

	public const int PageSize = 10;

	public static List<LibraryApp> Load(string path)
	{
		List<LibraryApp> list = JsonSerializer.Deserialize<List<LibraryApp>>(File.ReadAllText(path));
		if (list == null || list.Count == 0)
		{
			throw new InvalidDataException("App library is empty.");
		}
		HashSet<string> hashSet = new HashSet<string>();
		foreach (LibraryApp item in list)
		{
			if (string.IsNullOrWhiteSpace(item.Name) || string.IsNullOrWhiteSpace(item.Id) || !hashSet.Add(item.Id) || string.IsNullOrWhiteSpace(item.Asset) || Path.IsPathRooted(item.Asset) || item.Asset.Contains("..") || item.Width <= 0 || item.Height <= 0)
			{
				throw new InvalidDataException("Invalid app library entry.");
			}
			float[] crop = item.Crop;
			if (crop != null && (crop.Length != 4 || !Array.TrueForAll(crop, float.IsFinite) || crop[0] < 0f || crop[1] < 0f || crop[2] <= 0f || crop[3] <= 0f || crop[0] + crop[2] > 1f || crop[1] + crop[3] > 1f))
			{
				throw new InvalidDataException("Invalid artwork crop.");
			}
		}
		return list;
	}

	public static int PageCount(int count)
	{
		return (count + 10 - 1) / 10;
	}

	public static int VisibleCount(int count, int page)
	{
		return Math.Max(0, Math.Min(10, count - page * 10));
	}

	public static int Move(int count, int absolute, string key)
	{
		if (count <= 0)
		{
			return -1;
		}
		absolute = Math.Clamp(absolute, 0, count - 1);
		int num = absolute / 10;
		int num2 = absolute % 10;
		int num3 = num2 % 5;
		int num4 = num2 / 5;
		int num5 = num * 10;
		int num6 = VisibleCount(count, num);
		switch (key)
		{
		case "Left":
			return Math.Max(0, absolute - 1);
		case "Right":
			return Math.Min(count - 1, absolute + 1);
		case "Up":
			if (num4 > 0)
			{
				return absolute - 5;
			}
			if (num == 0)
			{
				return -1;
			}
			return num5 - 5 + num3;
		case "Down":
		{
			if ((num4 + 1) * 5 < num6)
			{
				return num5 + Math.Min(num2 + 5, num6 - 1);
			}
			int num7 = num5 + 10;
			if (num7 >= count)
			{
				return absolute;
			}
			return Math.Min(num7 + num3, count - 1);
		}
		default:
			return absolute;
		}
	}
}
