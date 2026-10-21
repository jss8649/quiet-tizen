using System;
using System.IO;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using Tizen.NUI;
using Tizen.NUI.BaseComponents;
using Tizen.Applications;

public sealed class QuietHome : NUIApplication
{
 const string Root="/opt/usr/apps/"+QuietHomeContainer.AppId+"/res/quiet-home/";
 const string StateFile="/tmp/quiet-home-state.txt";
 sealed class Slot { public View Card,Shadow,FocusRing; public TextLabel Label; public string Name,Action,Description; public int Row,X,Y,W,H; }
 sealed class CachedArtwork { public ImageView Image; public View Parent; }
 readonly List<Slot> slots=new List<Slot>();
 readonly List<View> scene=new List<View>();
 readonly Dictionary<string,CachedArtwork> artworkCache=new Dictionary<string,CachedArtwork>();
 View artworkPreloadRoot;
 int artworkViewsCreated,pageArtworkCold;
 List<LibraryApp> library=new List<LibraryApp>();
 int libraryPage;
 string libraryError="";
 TextLabel clock, notice, detail;
 TextLabel[] tabs;
 TextLabel toolbarHint;
 Animation focusAnimation;
 bool fontLoaded;
 Tizen.NUI.Timer clockTimer;
 int page, selected, area=1, lastSource=14;
 string editing="";
 long buildMilliseconds;
 int currentVolume, currentMute;
 readonly Dictionary<string,string> settingValues=new Dictionary<string,string>();
 readonly Dictionary<string,string> settingNames=new Dictionary<string,string>();
 readonly Dictionary<string,bool> settingEnabled=new Dictionary<string,bool>();
 double brightnessMin,brightnessMax=50,brightnessStep=1;
 string lastKey="";
 long lastKeyAt;
 readonly Color ink=new Color(0.114f,0.114f,0.122f,1);
 readonly Color muted=new Color(0.431f,0.431f,0.451f,1);
 readonly Color white=new Color(1,1,1,1);
 readonly Color accent=new Color(0.24f,0.29f,0.72f,1);
 [DllImport("libsource-api.so")] static extern int connect_source(int sourceType);
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key,out int value);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_create(out IntPtr app);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_app_id(IntPtr app,string id);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_operation(IntPtr app,string operation);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_add_extra_data(IntPtr app,string key,string value);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_send_launch_request(IntPtr app,IntPtr cb,IntPtr data);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_destroy(IntPtr app);
 [DllImport("libcapi-media-sound-manager-tv.so.0")] static extern int sound_manager_get_master_volume(out int value);
 [DllImport("libcapi-media-sound-manager-tv.so.0")] static extern int sound_manager_set_master_volume(int value);
 [DllImport("libcapi-media-sound-manager-tv.so.0")] static extern int sound_manager_get_master_mute(out int value);
 [DllImport("libcapi-media-sound-manager-tv.so.0")] static extern int sound_manager_set_master_mute(int value);
 [DllImport("libsettings-api.so")] static extern bool CSharpGetItemValue(string id,out string name,out string value);
 [DllImport("libsettings-api.so")] static extern bool CSharpSetItemValue(string id,string value);
 [DllImport("libsettings-api.so")] static extern bool CSharpGetItemEnable(string id,out bool enabled);
 [DllImport("libsettings-api.so")] static extern bool CSharpGetItemMinMaxStepValue(string id,out double min,out double max,out double step);



 protected override void OnCreate()
 {
  base.OnCreate();
  try{fontLoaded=FontClient.Instance.AddCustomFontDirectory(Root+"fonts");}catch{fontLoaded=false;}
  try{library=AppLibrary.Load(Root+"apps.json");}catch(Exception ex){libraryError=ex.Message;}
  Window.Default.BackgroundColor=new Color(0.96f,0.96f,0.97f,1);
  Window.Default.Title="Quiet Home";Window.Default.KeyEvent+=OnKey;
  PreloadArtwork();
  RefreshSource();selected=SourceIndex();BuildPage();
  clockTimer=new Tizen.NUI.Timer(30000);
  clockTimer.Tick+=(s,e)=>{if(clock!=null)clock.Text=DateTime.Now.ToString("h:mm tt");return true;};clockTimer.Start();WriteState("created");
 }
 protected override void OnResume(){base.OnResume();clockTimer?.Start();RefreshSource();if(tabs!=null&&page==2){RefreshSettings();UpdateFocus(false);}WriteState("resumed");}
 protected override void OnAppControlReceived(AppControlReceivedEventArgs e){base.OnAppControlReceived(e);string requested; if(e.ReceivedAppControl.ExtraData.TryGet("quiet_page",out requested)&&requested=="settings")OpenSettings("settings_request");else if(requested=="apps"){page=1;area=1;selected=0;BuildPage();}else Home("home_request");}
 protected override void OnPause(){base.OnPause();editing="";clockTimer?.Stop();WriteState("paused");}
 void Home(string activity){clockTimer?.Start();RefreshSource();if(tabs!=null){bool unchanged=page==0&&area==1&&editing==""&&selected==SourceIndex();page=0;area=1;editing="";selected=SourceIndex();if(!unchanged)BuildPage();WriteState(activity);}}
 void OpenSettings(string activity){clockTimer?.Start();page=2;area=1;selected=0;editing="";BuildPage();WriteState(activity);}
 void RefreshSource(){try{int n;if(vconf_get_int("memory/system/source_type",out n)==0&&n>=13&&n<=15)lastSource=n;}catch{}}
 int SourceIndex(){return lastSource==15?1:lastSource==13?2:0;}
 View Add(View v){scene.Add(v);Window.Default.Add(v);return v;}
 View Panel(int x,int y,int w,int h,Color color,int radius=18){return Add(new View{Position2D=new Position2D(x,y),Size2D=new Size2D(w,h),BackgroundColor=color,CornerRadius=new Vector4(radius,radius,radius,radius)});}
 TextLabel Text(string text,int x,int y,int w,int h,float size,Color color,string face="Medium")
 {return (TextLabel)Add(Label(text,x,y,w,h,size,color,face));}
 TextLabel Label(string text,int x,int y,int w,int h,float size,Color color,string face="Medium")
 {return new TextLabel{Text=text,Position2D=new Position2D(x,y),Size2D=new Size2D(w,h),PixelSize=size,FontFamily="Quiet Inter "+face,TextColor=color,VerticalAlignment=VerticalAlignment.Center};}
 void BuildPage()
 {
  var stopwatch=Stopwatch.StartNew();
  if(focusAnimation!=null){focusAnimation.Stop();focusAnimation.Dispose();focusAnimation=null;}
  ParkArtwork();pageArtworkCold=0;
  foreach(var v in scene){Window.Default.Remove(v);v.Dispose();}scene.Clear();slots.Clear();
  Add(new ImageView{ResourceUrl=Root+"free-background.svg",Size2D=new Size2D(1920,1080)});
  Text(page==0?"Home":page==1?"Your Apps":"Quick Settings",76,55,1350,100,76,ink,"Display");
  tabs=new TextLabel[3];string[] nav={"Inputs","Apps","Settings"};int[] tx={54,221,366};int[] tw={153,131,182};
  for(int i=0;i<3;i++){tabs[i]=Text(nav[i],tx[i],158,tw[i],68,30,muted);tabs[i].HorizontalAlignment=HorizontalAlignment.Center;}
  clock=Text(DateTime.Now.ToString("h:mm tt"),1540,170,300,45,24,muted);clock.HorizontalAlignment=HorizontalAlignment.End;
  if(page==0){
   var hero=Feature("PlayStation 5","hdmi:14","Game console · HDMI 2","feature-ps5.svg",80,262,1040,442,"hero");
   hero.Card.Add(Label("PLAYSTATION 5",44,52,550,40,24,new Color(.86f,.91f,1,1),"Semibold"));
   hero.Card.Add(Label("Let's play.",40,124,560,100,72,white,"Display"));
   hero.Card.Add(Label("Switch to HDMI 2",46,246,440,48,30,new Color(.88f,.93f,1,1)));
   Feature("Nintendo Switch","hdmi:15","Game console · HDMI 3","feature-switch.svg",1160,262,320,442,"portrait");
   Feature("HDMI 1","hdmi:13","External device","feature-hdmi.svg",1520,262,320,442,"portrait");
  }else if(page==1){
   BuildLibrary();
  }else{
   RefreshSettings();
   SettingsTile("Volume","volume","Select · Left / Right to adjust","volume",0,0);
   SettingsTile("Brightness","brightness","Select · Left / Right to adjust","brightness",1,0);
   SettingsTile("Game Mode","game-mode","Select to switch on or off","game",2,0);
   SettingsTile("Sleep Timer","sleeptimer","Select to change the timer","sleep",3,0);
   SettingsTile("Sound","mute","Select to mute or unmute","mute",0,1);
   SettingsTile("Controllers","controllers","DualSense · hold PS + Create","controller",1,1);
   SettingsTile("Network","network","Wi-Fi and connection setup","network",2,1);
   SettingsTile("Advanced","app:org.tizen.menu","Open Samsung's full settings","settings",3,1);
  }
  if(page==0){
  Add(new ImageView{ResourceUrl=Root+"glass-shelf.svg",Position2D=new Position2D(0,784),Size2D=new Size2D(1920,280)});
  Dock("Netflix","app:org.tizen.netflix-app","netflix",0);
  Dock("YouTube","app:com.samsung.tv.cobalt-yt","youtube",1);
  Dock("Prime Video","app:org.tizen.primevideo","prime",2);
  Dock("PlayStation 5","hdmi:14","ps5",3);
  Dock("Nintendo Switch","hdmi:15","switch",4);
  Dock("Your Apps","page:1","apps",5);
  }
  Toolbar("Apps","page:1","apps",0);Toolbar("Inputs","page:0","hdmi",1);Toolbar("Settings","page:2","settings",2);
  toolbarHint=Text("",1530,170,310,45,24,ink);toolbarHint.HorizontalAlignment=HorizontalAlignment.End;
  detail=Text("",80,1030,1320,35,20,muted);
  notice=Text("",80,1008,1760,34,22,accent);
  var hint=Text(page==1?(AppLibrary.PageCount(library.Count)<=1?"Select to open · Back to Home":libraryPage+1<AppLibrary.PageCount(library.Count)?"Down for more apps · Back to Home":"Up for previous apps · Back to Home"):"Back to input",1310,1030,530,35,20,muted);hint.HorizontalAlignment=HorizontalAlignment.End;
  selected=Math.Max(0,Math.Min(selected,slots.Count-1));UpdateFocus(false);
  buildMilliseconds=stopwatch.ElapsedMilliseconds;WriteState("page_ready");
 }
 void BuildLibrary()
 {
  if(library.Count==0){Text("Apps could not be loaded.",80,300,1500,70,32,ink);return;}
  libraryPage=Math.Clamp(libraryPage,0,AppLibrary.PageCount(library.Count)-1);
  int start=libraryPage*AppLibrary.PageSize,count=AppLibrary.VisibleCount(library.Count,libraryPage);
  for(int i=0;i<count;i++)
  {
   var app=library[start+i];int x=80+(i%5)*358,y=266+(i/5)*245,w=328,h=184;
   var shadow=Panel(x-5,y+7,w+10,h+8,new Color(.12f,.15f,.25f,.08f),22);
   var card=Panel(x+w/2,y+h/2,w,h,HexColor(app.Background),18);
   card.PivotPoint=new Position(.5f,.5f,.5f);card.PositionUsesPivotPoint=true;
   AddAppArtwork(card,app,w,h);
   var ring=new View{Size2D=new Size2D(w,h),BackgroundColor=new Color(0,0,0,0),CornerRadius=new Vector4(18,18,18,18),BorderlineWidth=4,BorderlineColor=accent,Opacity=0};
   card.Add(ring);
   var label=Text(app.Name,x,y+h+14,w,38,27,ink,"Semibold");
   slots.Add(new Slot{Card=card,Shadow=shadow,FocusRing=ring,Label=label,Name=app.Name,Action="app:"+app.Id,Description=app.Description,Row=i/5,X=x,Y=y,W=w,H=h});
  }
  Text(library.FindAll(a=>!a.Utility).Count+" apps",80,218,500,30,21,muted);
  if(AppLibrary.PageCount(library.Count)>1){
   var pages=Text((libraryPage+1)+" / "+AppLibrary.PageCount(library.Count),1650,218,190,30,21,muted);
   pages.HorizontalAlignment=HorizontalAlignment.End;
  }
 }
 Color HexColor(string hex)
 {
  try{int n=Convert.ToInt32(hex.TrimStart('#'),16);return new Color(((n>>16)&255)/255f,((n>>8)&255)/255f,(n&255)/255f,1);}
  catch{return white;}
 }
 void AddAppArtwork(View card,LibraryApp app,int w,int h)
 {
  if(!app.Utility){
   var cached=GetArtwork(app,w,h);
   if(cached.Image.LoadingStatus!=ImageView.LoadingStatusType.Ready)pageArtworkCold++;
   cached.Parent.Remove(cached.Image);card.Add(cached.Image);cached.Parent=card;
  }
  if(app.Utility){
   card.Add(new View{Position2D=new Position2D(w/2-28,h/2-2),Size2D=new Size2D(56,4),BackgroundColor=ink});
   card.Add(new View{Position2D=new Position2D(w/2-2,h/2-28),Size2D=new Size2D(4,56),BackgroundColor=ink});
  }
 }
 void PreloadArtwork()
 {
  // Keep the real image views alive on the scene; moving between pages never
  // destroys their decoded textures. The zero-opacity parent is never drawn.
  artworkPreloadRoot=new View{Size2D=new Size2D(1920,1080),Opacity=0};
  Window.Default.Add(artworkPreloadRoot);
  foreach(var app in library)if(!app.Utility)GetArtwork(app,328,184);
  foreach(var id in new[]{"org.tizen.netflix-app","com.samsung.tv.cobalt-yt","org.tizen.primevideo"}){
   var app=library.Find(a=>a.Id==id);if(app!=null)GetArtwork(app,253,126);
  }
 }
 CachedArtwork GetArtwork(LibraryApp app,int w,int h)
 {
  string key=app.Id+"@"+w+"x"+h;
  if(artworkCache.TryGetValue(key,out var cached))return cached;
  bool cover=app.Fit=="cover",full=cover||app.Fit=="contain-full";
  int iw=full?w:w-54,ih=full?h:h-40;var crop=app.Crop;
  float cropWidth=crop==null?1:crop[2],cropHeight=crop==null?1:crop[3];
  var image=new ImageView{
   Position2D=new Position2D((w-iw)/2,(h-ih)/2),Size2D=new Size2D(iw,ih),
   FittingMode=cover?FittingModeType.ScaleToFill:FittingModeType.ShrinkToFit,
   SamplingMode=SamplingModeType.BoxThenLanczos,
   DesiredWidth=(int)Math.Ceiling(iw*2/cropWidth),DesiredHeight=(int)Math.Ceiling(ih*2/cropHeight),
   ReleasePolicy=ReleasePolicyType.Destroyed,CornerRadius=new Vector4(18,18,18,18)};
  if(crop!=null)image.PixelArea=new RelativeVector4(crop[0],crop[1],crop[2],crop[3]);
  cached=new CachedArtwork{Image=image,Parent=artworkPreloadRoot};
  artworkCache.Add(key,cached);artworkViewsCreated++;
  image.ResourceReady+=(s,e)=>WriteState("artwork_ready");
  artworkPreloadRoot.Add(image);image.ResourceUrl=Root+app.Asset;
  return cached;
 }
 void ParkArtwork()
 {
  foreach(var cached in artworkCache.Values)if(cached.Parent!=artworkPreloadRoot){
   cached.Parent.Remove(cached.Image);artworkPreloadRoot.Add(cached.Image);cached.Parent=artworkPreloadRoot;
  }
 }
 int ArtworkReadyCount()
 {
  int count=0;foreach(var cached in artworkCache.Values)
   if(cached.Image.LoadingStatus==ImageView.LoadingStatusType.Ready)count++;
  return count;
 }
 string ArtworkPending()
 {
  var pending=new List<string>();
  foreach(var entry in artworkCache)
   if(entry.Value.Image.LoadingStatus!=ImageView.LoadingStatusType.Ready)
    pending.Add(entry.Key+":"+entry.Value.Image.LoadingStatus);
  return string.Join(";",pending);
 }
 void SettingsTile(string name,string action,string description,string icon,int column,int row)
 {
  int x=80+column*450,y=262+row*332,w=410,h=286;
  var card=Panel(x+w/2,y+h/2,w,h,new Color(0,0,0,0),24);card.PivotPoint=new Position(.5f,.5f,.5f);card.PositionUsesPivotPoint=true;
  card.Add(new ImageView{ResourceUrl=Root+"quick-"+icon+".svg",Size2D=new Size2D(w,h)});
  card.Add(Label(name,26,25,348,42,29,white,"Semibold"));
  var value=Label("",26,151,358,56,38,white,"Display");card.Add(value);
  card.Add(Label(description,26,226,370,34,20,new Color(.95f,.96f,1,1)));
  slots.Add(new Slot{Card=card,Label=value,Name=name,Action=action,Description=description,Row=row,X=x,Y=y,W=w,H=h});
 }
 Slot Feature(string label,string action,string description,string asset,int x,int y,int w,int h,string shape)
 {
  var shadow=Add(new ImageView{ResourceUrl=Root+"shadow-"+shape+".svg",Position2D=new Position2D(x-24,y-10),Size2D=new Size2D(w+48,h+64)});
  var card=Panel(x+w/2,y+h/2,w,h,new Color(0,0,0,0),18);card.PivotPoint=new Position(.5f,.5f,.5f);card.PositionUsesPivotPoint=true;
  card.Add(new ImageView{ResourceUrl=Root+asset,Size2D=new Size2D(w,h)});
  var caption=Text(label,x,716,w,45,31,ink,"Semibold");
  Text(description,x,760,w,36,24,muted);
  var slot=new Slot{Card=card,Shadow=shadow,Label=caption,Name=label,Action=action,Description=description,Row=0,X=x,Y=y,W=w,H=h};slots.Add(slot);return slot;
 }
 void Dock(string label,string action,string asset,int n)
 {
  int x=(int)Math.Round(80+n*(253.333+48));
  var shadow=Add(new ImageView{ResourceUrl=Root+"shadow-dock.svg",Position2D=new Position2D(x-24,842),Size2D=new Size2D(301,190)});
  var card=Panel(x+126,917,253,126,new Color(0,0,0,0),22);card.PivotPoint=new Position(.5f,.5f,.5f);card.PositionUsesPivotPoint=true;
  var official=library.Find(a=>a.Id==action.Substring(action.IndexOf(':')+1));
  if(official!=null){card.BackgroundColor=HexColor(official.Background);AddAppArtwork(card,official,253,126);}
  else card.Add(new ImageView{ResourceUrl=Root+"free-dock-"+asset+".svg",Size2D=new Size2D(253,126)});
  slots.Add(new Slot{Card=card,Shadow=shadow,Name=label,Action=action,Description=label,Row=1,X=x,Y=854,W=253,H=126});
 }
 void Toolbar(string label,string action,string icon,int n)
 {
  int x=1596+n*88;
  var card=Panel(x+34,103,68,68,new Color(0,0,0,0),34);card.PivotPoint=new Position(.5f,.5f,.5f);card.PositionUsesPivotPoint=true;
  card.Add(new ImageView{ResourceUrl=Root+"glass-button.svg",Position2D=new Position2D(-16,-16),Size2D=new Size2D(100,112)});
  card.Add(new ImageView{ResourceUrl=Root+"symbol-"+icon+".png",Color=ink,Position2D=new Position2D(19,19),Size2D=new Size2D(30,30)});
  slots.Add(new Slot{Card=card,Name=label,Action=action,Description=label,Row=-1,X=x,Y=69,W=68,H=68});
 }
 List<int> Row(int row){var r=new List<int>();for(int i=0;i<slots.Count;i++)if(slots[i].Row==row)r.Add(i);return r;}
 void UpdateFocus(bool animate=true)
 {
  if(focusAnimation!=null){focusAnimation.Stop();focusAnimation.Dispose();focusAnimation=null;}
  if(animate)focusAnimation=new Animation(180);
  for(int i=0;i<3;i++){tabs[i].TextColor=i==page?ink:muted;tabs[i].FontFamily="Quiet Inter "+(i==page?"Semibold":"Medium");tabs[i].BackgroundColor=area==0&&i==page?new Color(1,1,1,.7f):new Color(0,0,0,0);tabs[i].CornerRadius=new Vector4(34,34,34,34);}
  for(int i=0;i<slots.Count;i++){
   var s=slots[i];bool f=area!=0&&selected==i;
   float scale=f?(page==1&&s.Row>=0?1.055f:page==2&&s.Row>=0?1.035f:s.Row==0?1.05f:s.Row==1?1.20f:1.10f):1;
   s.Card.BorderlineWidth=page==1&&s.Row>=0?(f?4:1):s.Row==0?1:0;
   s.Card.BorderlineColor=page==1&&f?accent:new Color(1,1,1,f?.8f:.28f);
   var pos=new Position(s.X+s.W/2f,s.Y+s.H/2f-(f&&(s.Row==0||page==1&&s.Row>=0)?5:0),0);
   if(animate){focusAnimation.AnimateTo(s.Card,"Scale",new Vector3(scale,scale,1));focusAnimation.AnimateTo(s.Card,"Position",pos);}else{s.Card.Scale=new Vector3(scale,scale,1);s.Card.Position=pos;}
   if(s.Shadow!=null)s.Shadow.Opacity=f?1:.55f;
   if(s.FocusRing!=null)s.FocusRing.Opacity=f?1:0;
   if(s.Label!=null&&page!=2)s.Label.FontFamily="Quiet Inter "+(f?"Semibold":"Medium");
   if(f)s.Card.RaiseToTop();
  }
  if(focusAnimation!=null)focusAnimation.Play();
  clock.Opacity=area==3?0:1;toolbarHint.Text=area==3?slots[selected].Name:"";
  detail.Text=page==1&&area==1&&slots[selected].Row>=0?slots[selected].Name+" · "+slots[selected].Description:area==0?"":area==2?slots[selected].Name:"";
  if(page==2){
   slots[0].Label.Text=currentVolume<0?"Unavailable":currentVolume.ToString();
   slots[1].Label.Text=SettingName("brightness");
   slots[2].Label.Text=SettingName("game-mode");
   slots[3].Label.Text=SettingName("sleeptimer");
   slots[4].Label.Text=currentMute<0?"Unavailable":currentMute==1?"Muted":"Sound on";
   slots[5].Label.Text="Pair controller";
   slots[6].Label.Text="Connections";
   slots[7].Label.Text="More settings";
   detail.Text="Your everyday controls";
  }
  if(editing!="")detail.Text="Left / Right to adjust "+editing+" · Select or Back to finish";
  WriteState("focus");
 }
 void OnKey(object sender,Window.KeyEventArgs e)
 {
  if(e.Key==null||e.Key.State!=Key.StateType.Down)return;string k=e.Key.KeyPressedName;
  long now=Environment.TickCount64;if(k==lastKey&&now-lastKeyAt<180)return;lastKey=k;lastKeyAt=now;
  try{
   if(k=="XF86Home"){Home("home_key");return;}
   if(k=="XF86SysMenu"||k=="XF86More"){OpenSettings("settings_key");return;}
   if(page==1&&HandleLibraryKey(k))return;
   if(editing!=""){if(k=="Left"||k=="Right"){int d=k=="Left"?-1:1;if(editing=="volume")ChangeVolume(d);else ChangeBrightness(d);}else if(k=="Return"||k=="KP_Enter"||k=="XF86Back"||k=="Back"||k=="Escape"){editing="";UpdateFocus();}return;}
   if(k=="Up"){if(area==2){int col=Row(1).IndexOf(selected);area=1;selected=Row(0)[page==2?col:0];}else if(area==1)area=0;UpdateFocus();}
   else if(k=="Down"){if(area==0||area==3){area=1;selected=Row(0)[0];}else if(area==1){int col=Row(0).IndexOf(selected);area=2;selected=Row(1)[page==2?col:0];}UpdateFocus();}
   else if(k=="Left"||k=="Right"){
    int d=k=="Left"?-1:1;
    if(area==0){int next=page+d;if(next<0||next>2){area=3;selected=Row(-1)[next<0?2:0];UpdateFocus();}else{page=next;selected=0;BuildPage();}}
    else if(area==3){var r=Row(-1);int n=r.IndexOf(selected)+d;if(n<0||n>=r.Count){area=0;page=n<0?2:0;selected=0;BuildPage();}else{selected=r[n];UpdateFocus();}}
    else{var r=Row(area-1);int n=r.IndexOf(selected);selected=r[(n+d+r.Count)%r.Count];UpdateFocus();}
   }
   else if(k=="Return"||k=="KP_Enter"){if(area==0){area=1;selected=0;UpdateFocus();}else Activate();}
   else if(k=="XF86Back"||k=="Back"||k=="Escape"||k=="XF86Exit")SelectSource(lastSource);
  }catch(Exception ex){ShowError(ex.Message);}
 }
 bool HandleLibraryKey(string key)
 {
  if(key=="XF86Back"||key=="Back"||key=="Escape"||key=="XF86Exit"){Home("apps_back");return true;}
  if(library.Count==0)return key=="Up"||key=="Down";
  if((area==0||area==3)&&key=="Down"){area=1;selected=0;UpdateFocus();return true;}
  if(area!=1)return false;
  if(key=="Left"||key=="Right"||key=="Up"||key=="Down"){
   int next=AppLibrary.Move(library.Count,libraryPage*AppLibrary.PageSize+selected,key);
   if(next<0){area=0;UpdateFocus();return true;}
   int nextPage=next/AppLibrary.PageSize;selected=next%AppLibrary.PageSize;
   if(nextPage!=libraryPage){libraryPage=nextPage;BuildPage();}else UpdateFocus();
   return true;
  }
  return false;
 }
 void Activate()
 {
  string a=slots[selected].Action;notice.Text="";
  if(a.StartsWith("hdmi:")){SelectSource(int.Parse(a.Substring(5)));return;}
  if(a.StartsWith("page:")){page=int.Parse(a.Substring(5));selected=page==0?SourceIndex():0;area=1;BuildPage();return;}
  if(a.StartsWith("app:")){Launch(a.Substring(4));return;}
  if(a=="controllers"){Launch("org.tizen.menu","add-bluetooth-keyboard");return;}
  if(a=="network"){Launch("org.tizen.menu","networksettings");return;}
  if(a=="volume"||a=="brightness"){RefreshSettings();if(a=="brightness"&&!CanEdit(a)){ShowError("Brightness is unavailable for the current input.");return;}editing=a;UpdateFocus();return;}
  if(a=="game-mode"){RefreshSettings();SetSetting(a,SettingValue(a)=="1"?"0":"1");return;}
  if(a=="sleeptimer"){RefreshSettings();int n;if(int.TryParse(SettingValue(a),out n))SetSetting(a,((n+1)%5).ToString());return;}
  if(a=="mute"){int n;int r=sound_manager_get_master_mute(out n);if(r==0)r=sound_manager_set_master_mute(n==1?0:1);if(r!=0)ShowError("Use the remote's mute button.");RefreshSettings();UpdateFocus();WriteState("mute_changed");}
 }
 void RefreshSettings(){
  currentVolume=sound_manager_get_master_volume(out var v)==0?v:-1;
  currentMute=sound_manager_get_master_mute(out var m)==0?m:-1;
  foreach(var id in new[]{"brightness","game-mode","sleeptimer"}){
   try{if(CSharpGetItemValue(id,out var name,out var value)&&!string.IsNullOrEmpty(value)){settingValues[id]=value;settingNames[id]=name;}else{settingValues.Remove(id);settingNames.Remove(id);}
    settingEnabled[id]=CSharpGetItemEnable(id,out var enabled)&&enabled;
   }catch{settingValues.Remove(id);settingNames.Remove(id);settingEnabled[id]=false;}
  }
  try{if(!CSharpGetItemMinMaxStepValue("brightness",out brightnessMin,out brightnessMax,out brightnessStep)||brightnessStep<=0){brightnessMin=0;brightnessMax=50;brightnessStep=1;}}catch{}
 }
 string SettingValue(string id){return settingValues.TryGetValue(id,out var v)?v:"";}
 string SettingName(string id){return settingNames.TryGetValue(id,out var v)?v:"Unavailable";}
 bool CanEdit(string id){return settingEnabled.TryGetValue(id,out var enabled)&&enabled&&settingValues.ContainsKey(id);}
 void SetSetting(string id,string value){
  if(!CanEdit(id)){ShowError("This setting is unavailable for the current input.");return;}
  bool ok=false;try{ok=CSharpSetItemValue(id,value);}catch{}
  RefreshSettings();UpdateFocus();
  bool verified=ok&&SettingValue(id)==value;
  if(!verified)ShowError("The TV could not apply this setting. Try Advanced settings.");
  WriteState("setting:"+id+":"+value+":"+verified);
 }
 void ChangeBrightness(int delta){double n;if(double.TryParse(SettingValue("brightness"),NumberStyles.Float,CultureInfo.InvariantCulture,out n))SetSetting("brightness",Math.Max(brightnessMin,Math.Min(brightnessMax,n+delta*brightnessStep)).ToString(CultureInfo.InvariantCulture));}
 void ChangeVolume(int delta){int n;int r=sound_manager_get_master_volume(out n);if(r==0)r=sound_manager_set_master_volume(Math.Max(0,Math.Min(100,n+delta)));if(r!=0)ShowError("Use the remote's volume buttons.");RefreshSettings();UpdateFocus();WriteState("volume_changed");}
 void SelectSource(int source){int r=connect_source(source);if(r<0){ShowError("Input could not be switched. Open Advanced settings to check the connection.");WriteState("source_failed:"+r);return;}lastSource=source;Launch("org.tizen.tv-viewer");}
 void Launch(string id,string menuItem=null)
 {
  IntPtr c;int r=app_control_create(out c);if(r!=0){ShowError("Could not open the app.");return;}
  try{r=app_control_set_app_id(c,id);if(r==0)r=app_control_set_operation(c,"http://tizen.org/appcontrol/operation/default");
   if(r==0&&id=="org.tizen.menu"){
    if(menuItem!=null){
     r=app_control_add_extra_data(c,"menuitem",menuItem);
     if(r==0)r=app_control_add_extra_data(c,"launchoption","pressed");
    }
    if(r==0)r=app_control_add_extra_data(c,"__K_EX_FORCE_BOOST","enable");
    if(r==0)r=app_control_add_extra_data(c,"__K_SPLASH_SCREEN","LA_UI_VR_TRANSPARENT");
   }
   if(r==0)r=app_control_send_launch_request(c,IntPtr.Zero,IntPtr.Zero);WriteState("launch:"+id+(menuItem==null?"":":"+menuItem)+":"+r);if(r!=0)ShowError("Could not open this screen. Try Advanced settings.");}finally{app_control_destroy(c);}
 }
 void ShowError(string text){notice.Text=text;}
 void WriteState(string activity){try{File.WriteAllText(StateFile,DateTime.UtcNow.ToString("o")+"\npage="+page+"\nselected="+selected+"\narea="+area+"\nactivity="+activity+"\nkey="+lastKey+"\nfont_loaded="+fontLoaded+"\nstyle=free-my-tv\nbuild_ms="+buildMilliseconds+"\nlibrary_page="+libraryPage+"\nlibrary_count="+library.Count+"\nlibrary_error="+libraryError+"\nselected_name="+(selected>=0&&selected<slots.Count?slots[selected].Name:"")+"\nartwork_cached="+artworkCache.Count+"\nartwork_ready="+ArtworkReadyCount()+"\nartwork_pending="+ArtworkPending()+"\nartwork_views_created="+artworkViewsCreated+"\npage_artwork_cold="+pageArtworkCold+"\nprocess_id="+Process.GetCurrentProcess().Id+"\nediting="+editing+"\nvolume="+currentVolume+"\nmute="+currentMute+"\nbrightness="+SettingValue("brightness")+"\ngame-mode="+SettingValue("game-mode")+"\nsleeptimer="+SettingValue("sleeptimer")+"\n");}catch{}}
 public static void Main(string[] args){using(var app=new QuietHome())app.Run(args);}
}
