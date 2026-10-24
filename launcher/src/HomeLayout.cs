using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

public sealed class HomeCard
{
 public string Name {get;set;}
 public string Action {get;set;}
 public string Description {get;set;}
 public string Asset {get;set;}
 public string Eyebrow {get;set;}
 public string Headline {get;set;}
 public string CallToAction {get;set;}
}

public sealed class HomeShortcut
{
 public string Name {get;set;}
 public string Action {get;set;}
 public string Asset {get;set;}
}

public sealed class HomeLayout
{
 public int DefaultSource {get;set;}
 public List<HomeCard> Cards {get;set;}
 public List<HomeShortcut> Dock {get;set;}

 public static HomeLayout Load(string path)
 {
  var layout=JsonSerializer.Deserialize<HomeLayout>(File.ReadAllText(path));
  if(layout==null||layout.DefaultSource<13||layout.DefaultSource>15||layout.Cards?.Count!=3||layout.Dock?.Count!=6)
   throw new InvalidDataException("Invalid Home layout.");
  foreach(var card in layout.Cards)
   if(card==null||string.IsNullOrWhiteSpace(card.Name)||string.IsNullOrWhiteSpace(card.Description)
      ||!ValidAction(card.Action)||!ValidAsset(card.Asset))
    throw new InvalidDataException("Invalid Home card.");
  foreach(var shortcut in layout.Dock)
   if(shortcut==null||string.IsNullOrWhiteSpace(shortcut.Name)
      ||!ValidAction(shortcut.Action)||!ValidAsset(shortcut.Asset))
    throw new InvalidDataException("Invalid Home shortcut.");
  if(!HasSource(layout,layout.DefaultSource))
   throw new InvalidDataException("Default source has no Home shortcut.");
  return layout;
 }

 public bool HasSource(int source)=>HasSource(this,source);

 static bool HasSource(HomeLayout layout,int source)
 {
  var action="hdmi:"+source;
  return layout.Cards.Exists(c=>c.Action==action)||layout.Dock.Exists(d=>d.Action==action);
 }

 static bool ValidAction(string action)
 {
  if(action=="page:1"||action=="page:2")return true;
  if(action!=null&&action.StartsWith("hdmi:",StringComparison.Ordinal)
     &&int.TryParse(action.Substring(5),out var source))return source>=13&&source<=15;
  return action!=null&&action.StartsWith("app:",StringComparison.Ordinal)
      &&action.Length>4&&action.IndexOfAny(new[]{'/', '\\', '\n', '\r'})<0;
 }

 static bool ValidAsset(string asset)
 {
  return !string.IsNullOrWhiteSpace(asset)&&!Path.IsPathRooted(asset)
      &&asset.IndexOfAny(new[]{'/', '\\', '\n', '\r'})<0&&asset!="."&&asset!="..";
 }
}
