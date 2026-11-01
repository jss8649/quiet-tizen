using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net.Http;
using Tizen.System;
using System.Threading.Tasks;
using System.Runtime.InteropServices;
using System.Text.Json;
using Tizen.Applications;
using Tizen.NUI;
using Tizen.NUI.BaseComponents;

public sealed class QuietHome : NUIApplication
{
	private VideoView backdropVideo;

	private Timer videoWatchdog;

	private bool resumed;

	private int videoWatchdogHangs;

	private View dimOverlay;

	private bool fireplace;

	private bool fireExpired;

	private bool fireHint;

	private int fireDownCount;

	private int fireUpCount;

	private long fireUpAt;

	private bool powerLocked;

	private bool volumeFailedLogged;

	private ImageView backdropStatic;

	private Timer startupFadeTimer;

	private Timer startupRaiseTimer;

	private Timer videoStartTimer;

	private bool firstClockLogged;

	private float homeVolume = 0.7f;

	private float fireVolume = 1f;

	private float fadeSeconds = 2f;

	private int holdMinutes = 120;

	private float curVolume = 0.7f;

	private float fadeTarget = 0.7f;

	private View fireBottomHint;

	private View fireTopHint;

	private Timer bottomHintTimer;

	private Timer topHintTimer;

	private Timer fadeTimer;

	private Timer holdTimer;

	private const string LastAppFile = "/opt/usr/share/quiet-tizen-state/last-app.txt";

	private TextLabel widgetTime;

	private TextLabel widgetDate;

	private TextLabel widgetTemp;

	private TextLabel widgetDesc;

	private TextLabel widgetRange;

	private TextLabel widgetPlace;

	private TextLabel widgetTempC;

	private TextLabel widgetLow;

	private static readonly HttpClient http = new HttpClient
	{
		Timeout = TimeSpan.FromSeconds(15)
	};

	private string weatherTemp = "";

	private string weatherDesc = "";

	private string weatherRange = "";

	private string weatherTempC = "";

	private string weatherLow = "";

	private string weatherPlace = "";

	private bool weatherBusy;

	private bool weatherConfigured;

	private DateTime weatherNextTry = DateTime.MinValue;

	private DateTime weatherUpdated = DateTime.MinValue;


	private sealed class InputSource
	{
		public bool ConnectionState { get; set; }

		public string DetectedName { get; set; }

		public string EditName { get; set; }

		public string IconPath { get; set; }

		public int SourceType { get; set; }
	}

	private sealed class Slot
	{
		public View Card;

		public View Shadow;

		public View FocusRing;

		public TextLabel Label;

		public string Name;

		public string Action;

		public string Description;

		public int Row;

		public int X;

		public int Y;

		public int W;

		public int H;
	}

	private sealed class CachedArtwork
	{
		public ImageView Image;

		public View Parent;
	}

	private const string Root = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/";

	private const string StateFile = "/tmp/quiet-home-state.txt";

	private const string WeatherCacheFile = "/opt/usr/share/quiet-tizen-state/weather-cache.json";

	private readonly List<Slot> slots = new List<Slot>();

	private readonly List<View> scene = new List<View>();

	private readonly Dictionary<string, CachedArtwork> artworkCache = new Dictionary<string, CachedArtwork>();

	private View artworkPreloadRoot;

	private int artworkViewsCreated;

	private int pageArtworkCold;

	private List<LibraryApp> library = new List<LibraryApp>();

	private List<InputSource> inputSources = new List<InputSource>();

	private int libraryPage;

	private string libraryError = "";

	private TextLabel clock;

	private TextLabel notice;

	private TextLabel detail;

	private TextLabel[] tabs;

	private TextLabel toolbarHint;

	private Animation focusAnimation;

	private bool fontLoaded;

	private Timer clockTimer;

	private int page;

	private int selected;

	private int area = 1;

	private int lastSource;

	private string editing = "";

	private long buildMilliseconds;

	private int currentVolume;

	private int currentMute;

	private readonly Dictionary<string, string> settingValues = new Dictionary<string, string>();

	private readonly Dictionary<string, string> settingNames = new Dictionary<string, string>();

	private readonly Dictionary<string, bool> settingEnabled = new Dictionary<string, bool>();

	private double brightnessMin;

	private double brightnessMax = 50.0;

	private double brightnessStep = 1.0;

	private string lastKey = "";

	private long lastKeyAt;

	private readonly Color ink = new Color(0.94f, 0.95f, 0.97f, 1f);

	private readonly Color muted = new Color(0.6f, 0.63f, 0.69f, 1f);

	private readonly Color white = new Color(1f, 1f, 1f, 1f);

	private readonly Color accent = new Color(0.24f, 0.29f, 0.72f, 1f);

	[DllImport("libsource-api.so")]
	private static extern int connect_source(int sourceType);

	[DllImport("libsource-api.so")]
	private static extern IntPtr get_source_list();

	[DllImport("libc.so.6")]
	private static extern void free(IntPtr p);

	[DllImport("libvconf.so.0")]
	private static extern int vconf_get_int(string key, out int value);

	[DllImport("libcapi-appfw-app-control.so.0")]
	private static extern int app_control_create(out IntPtr app);

	[DllImport("libcapi-appfw-app-control.so.0")]
	private static extern int app_control_set_app_id(IntPtr app, string id);

	[DllImport("libcapi-appfw-app-control.so.0")]
	private static extern int app_control_set_operation(IntPtr app, string operation);

	[DllImport("libcapi-appfw-app-control.so.0")]
	private static extern int app_control_add_extra_data(IntPtr app, string key, string value);

	[DllImport("libcapi-appfw-app-control.so.0")]
	private static extern int app_control_send_launch_request(IntPtr app, IntPtr cb, IntPtr data);

	[DllImport("libcapi-appfw-app-control.so.0")]
	private static extern int app_control_destroy(IntPtr app);

	[DllImport("libcapi-media-sound-manager-tv.so.0")]
	private static extern int sound_manager_get_master_volume(out int value);

	[DllImport("libcapi-media-sound-manager-tv.so.0")]
	private static extern int sound_manager_set_master_volume(int value);

	[DllImport("libcapi-media-sound-manager-tv.so.0")]
	private static extern int sound_manager_get_master_mute(out int value);

	[DllImport("libcapi-media-sound-manager-tv.so.0")]
	private static extern int sound_manager_set_master_mute(int value);

	[DllImport("libsettings-api.so")]
	private static extern bool CSharpGetItemValue(string id, out string name, out string value);

	[DllImport("libsettings-api.so")]
	private static extern bool CSharpSetItemValue(string id, string value);

	[DllImport("libsettings-api.so")]
	private static extern bool CSharpGetItemEnable(string id, out bool enabled);

	[DllImport("libsettings-api.so")]
	private static extern bool CSharpGetItemMinMaxStepValue(string id, out double min, out double max, out double step);

	protected override void OnCreate()
	{
		base.OnCreate();
		VideoLog("oncreate start");
		try
		{
			fontLoaded = FontClient.Instance.AddCustomFontDirectory("/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/fonts");
		}
		catch
		{
			fontLoaded = false;
		}
		try
		{
			library = AppLibrary.Load("/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/apps.json");
		}
		catch (Exception ex)
		{
			libraryError = ex.Message;
		}
		Window.Default.BackgroundColor = new Color(0.035f, 0.043f, 0.059f, 1f);
		Window.Default.Title = "Quiet Home";
		Window.Default.KeyEvent += OnKey;
		LoadFireConfig();
		BuildBackdrop();
		VideoLog("oncreate backdrop");
		PreloadArtwork();
		VideoLog("oncreate artwork");
		RefreshSource();
		VideoLog("oncreate sources");
		selected = 0;
		RestoreLastApp();
		VideoLog("oncreate restore");
		LoadWeatherCache();
		VideoLog("oncreate weather");
		weatherNextTry = DateTime.Now.AddSeconds(15);
		BuildPage();
		VideoLog("oncreate page");
		clockTimer = new Timer(1000u);
		MaybeFetchWeather();
		clockTimer.Tick += delegate
		{
			if (!firstClockLogged)
			{
				firstClockLogged = true;
				VideoLog("first clock tick");
			}
			if (clock != null)
			{
				clock.Text = DateTime.Now.ToString("h:mm tt");
			}
			MaybeFetchWeather();
			UpdateWidget();
			return true;
		};
		clockTimer.Start();
		startupRaiseTimer = new Timer(1500u);
		int startupRaises = 0;
		startupRaiseTimer.Tick += delegate
		{
			try { Window.Default.Raise(); Window.Default.Activate(); } catch { }
			VideoLog("raise tick " + startupRaises);
			return ++startupRaises < 4;
		};
		startupRaiseTimer.Start();
		try { Window.Default.Raise(); Window.Default.Activate(); } catch { }
		BuildFireHints();
		StartVideoWatchdog();
		WriteState("created");
		VideoLog("created");
	}

	private void StartVideoWatchdog()
	{
		videoWatchdog = new Timer(300000u);
		videoWatchdog.Tick += delegate
		{
			try
			{
				if (!resumed || backdropVideo == null || videoWatchdogHangs >= 3)
				{
					return true;
				}
				if (fireplace && fireExpired)
				{
					return true;
				}
				DateTime mark = DateTime.UtcNow;
				try { backdropVideo.Play(); } catch (Exception ex) { VideoLog("watchdog play error " + ex.GetType().Name + " " + ex.Message); }
				long ms = (long)(DateTime.UtcNow - mark).TotalMilliseconds;
				if (ms >= 5000)
				{
					videoWatchdogHangs++;
					VideoLog("watchdog play slow ms=" + ms + " hangs=" + videoWatchdogHangs);
				}
			}
			catch
			{
			}
			return true;
		};
		videoWatchdog.Start();
	}

	protected override void OnResume()
	{
		VideoLog("onresume start");
		DateTime resumeMark = DateTime.UtcNow;
		base.OnResume();
		VideoLog("onresume t base=" + (long)(DateTime.UtcNow - resumeMark).TotalMilliseconds);
		resumeMark = DateTime.UtcNow;
		try { Window.Default.Raise(); Window.Default.Activate(); } catch { }
		VideoLog("onresume t raise=" + (long)(DateTime.UtcNow - resumeMark).TotalMilliseconds);
		resumeMark = DateTime.UtcNow;
		try { if (!(fireplace && fireExpired)) { backdropVideo?.Play(); } } catch (Exception ex) { VideoLog("onresume play error " + ex.GetType().Name + " " + ex.Message); }
		VideoLog("onresume t play=" + (long)(DateTime.UtcNow - resumeMark).TotalMilliseconds);
		if (fireplace && !fireExpired)
		{
			LockDisplay();
		}
		resumeMark = DateTime.UtcNow;
		clockTimer?.Start();
		RefreshSource();
		VideoLog("onresume t source=" + (long)(DateTime.UtcNow - resumeMark).TotalMilliseconds);
		resumeMark = DateTime.UtcNow;
		if (tabs != null && page == 2)
		{
			RefreshSettings();
			UpdateFocus(animate: false);
		}
		VideoLog("onresume t settings=" + (long)(DateTime.UtcNow - resumeMark).TotalMilliseconds);
		resumed = true;
		WriteState("resumed");
		VideoLog("onresume done");
	}

	protected override void OnAppControlReceived(AppControlReceivedEventArgs e)
	{
		base.OnAppControlReceived(e);
		try
		{
			string caller = e.ReceivedAppControl.CallerApplicationId;
			string aiKey;
			bool isAi = e.ReceivedAppControl.ExtraData.TryGet("ctxmgr_key_press", out aiKey) && aiKey == "XF86KeyAIMenu";
			VideoLog("app control from=" + caller + " ai=" + isAi);
			if (isAi)
			{
				OpenSourcePanel("ai_launch", lowerAfter: true);
				return;
			}
		}
		catch (Exception ex)
		{
			VideoLog("app control inspect failed: " + ex.GetType().Name);
		}
		if (fireplace)
		{
			ExitFireplace(animate: false);
		}
		if (e.ReceivedAppControl.ExtraData.TryGet("quiet_page", out string value) && value == "settings")
		{
			OpenSettings("settings_request");
		}
		else if (value == "apps")
		{
			page = 0;
			area = 1;
			selected = 0;
			BuildPage();
		}
		else
		{
			Home("home_request");
		}
	}

	protected override void OnPause()
	{
		VideoLog("onpause");
		resumed = false;
		base.OnPause();
		try { backdropVideo?.Pause(); UnlockDisplay(); } catch { }
		editing = "";
		clockTimer?.Stop();
		WriteState("paused");
	}

	private void Home(string activity)
	{
		if (fireplace)
		{
			ExitFireplace(animate: false);
		}
		clockTimer?.Start();
		RefreshSource();
		if (tabs != null)
		{
			bool num = page == 0 && area == 1 && editing == "" && selected == 0;
			page = 0;
			area = 1;
			editing = "";
			selected = 0;
			if (!num)
			{
				BuildPage();
			}
			WriteState(activity);
		}
	}

	private void OpenSettings(string activity)
	{
		if (fireplace)
		{
			ExitFireplace(animate: false);
		}
		clockTimer?.Start();
		page = 2;
		area = 1;
		selected = 0;
		editing = "";
		BuildPage();
		WriteState(activity);
	}

	private void RefreshSource()
	{
		try
		{
			if (vconf_get_int("memory/system/source_type", out var value) == 0 && (value == 0 || value == 16))
			{
				lastSource = value;
			}
		}
		catch
		{
		}
	}

	private void RefreshInputSources()
	{
		RefreshInputSourcesCore();
		if (!inputSources.Exists((InputSource s) => s.SourceType == 0))
		{
			inputSources.Insert(0, new InputSource
			{
				ConnectionState = true,
				SourceType = 0
			});
		}
		foreach (InputSource inputSource in inputSources)
		{
			if (inputSource.SourceType == 0 && string.IsNullOrWhiteSpace(inputSource.IconPath))
			{
				inputSource.IconPath = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/app-icons/live-tv.svg";
			}
		}
	}

	private static string VideoMode()
	{
		try
		{
			string text = File.ReadAllText("/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/video-mode.txt").Trim().ToLowerInvariant();
			return (text == "texture" || text == "off") ? text : "underlay";
		}
		catch
		{
			return "off";
		}
	}

	private static void VideoLog(string line)
	{
		try
		{
			File.AppendAllText("/tmp/quiet-home-video.txt", DateTime.UtcNow.ToString("o") + " " + line + "\n");
		}
		catch
		{
		}
	}

	private QuietHome(WindowMode windowMode)
		: base("", windowMode)
	{
	}

	private void BuildBackdrop()
	{
		string mode = VideoMode();
		string text = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/fireplace.mp4";
		VideoLog("mode=" + mode + " file=" + File.Exists(text));
		bool flag = false;
		if (mode != "off" && File.Exists(text))
		{
			bool underlay = mode == "underlay";
			AddBackdropPicture();
			VideoLog("static added");
			videoStartTimer = new Timer(3000u);
			videoStartTimer.Tick += delegate
			{
				VideoLog("video create begin");
				CreateBackdropVideo(text, underlay);
				VideoLog("repaint before play");
				BuildPage();
				VideoLog("play begin");
				try { backdropVideo?.Play(); } catch (Exception ex) { VideoLog("play error " + ex); }
				VideoLog("play returned");
				return false;
			};
			videoStartTimer.Start();
			flag = true;
		}
		if (!flag)
		{
			AddBackdropPicture();
		}
	}

	private void CreateBackdropVideo(string text, bool underlay)
	{
		try
		{
			backdropVideo = new VideoView
			{
				Looping = true,
				Muted = false,
				Underlay = underlay,
				Position2D = new Position2D(-4, -4),
				Size2D = new Size2D(1928, 1088)
			};
			backdropVideo.Finished += delegate
			{
				VideoLog("finished event");
				try { if (!(fireplace && fireExpired)) { backdropVideo?.Play(); } } catch { }
			};
			backdropVideo.ResourceUrl = text;
			if (underlay)
			{
				Window.Default.BackgroundColor = new Color(0f, 0f, 0f, 0f);
			}
			Window.Default.Add(backdropVideo);
			try { backdropVideo.LowerToBottom(); } catch { }
			SetVideoVolume(homeVolume);
			dimOverlay = new View
			{
				Position2D = new Position2D(-4, -4),
				Size2D = new Size2D(1928, 1088),
				BackgroundColor = new Color(0f, 0f, 0f, 0.5f)
			};
			Window.Default.Add(dimOverlay);
			try { dimOverlay.LowerToBottom(); } catch { }
			try { backdropVideo.LowerToBottom(); } catch { }
			if (underlay)
			{
				startupFadeTimer = new Timer(2000u);
				startupFadeTimer.Tick += delegate
				{
					if (backdropStatic != null)
					{
						Animation fadeOut = new Animation(800);
						fadeOut.AnimateTo(backdropStatic, "Opacity", 0f);
						fadeOut.Finished += delegate
						{
							ImageView img = backdropStatic;
							backdropStatic = null;
							try { Window.Default.Remove(img); img?.Dispose(); } catch { }
							startupFadeTimer = null;
							fadeOut.Dispose();
						};
						fadeOut.Play();
					}
					return false;
				};
				startupFadeTimer.Start();
			}
		}
		catch (Exception ex)
		{
			VideoLog("exception " + ex);
			backdropVideo = null;
			Window.Default.BackgroundColor = new Color(0.035f, 0.043f, 0.059f, 1f);
		}
	}

	private void AddBackdropPicture()
	{
		backdropStatic = new ImageView
		{
			ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/home-background.jpg",
			Size2D = new Size2D(1920, 1080)
		};
		Window.Default.Add(backdropStatic);
	}

	private void RefreshInputSourcesCore()
	{
		IntPtr intPtr = IntPtr.Zero;
		try
		{
			intPtr = get_source_list();
			if (intPtr == IntPtr.Zero)
			{
				inputSources = new List<InputSource>();
				return;
			}
			string json = Marshal.PtrToStringAnsi(intPtr);
			inputSources = (JsonSerializer.Deserialize<List<InputSource>>(json, new JsonSerializerOptions
			{
				PropertyNameCaseInsensitive = true
			}) ?? new List<InputSource>()).FindAll((InputSource s) => s.ConnectionState);
		}
		catch
		{
			inputSources = new List<InputSource>();
		}
		finally
		{
			if (intPtr != IntPtr.Zero)
			{
				free(intPtr);
			}
		}
	}

	private int SourceIndex()
	{
		if (lastSource != 16)
		{
			return 0;
		}
		return 1;
	}

	private View Add(View v)
	{
		scene.Add(v);
		Window.Default.Add(v);
		return v;
	}

	private View Panel(int x, int y, int w, int h, Color color, int radius = 18)
	{
		return Add(new View
		{
			Position2D = new Position2D(x, y),
			Size2D = new Size2D(w, h),
			BackgroundColor = color,
			CornerRadius = new Vector4(radius, radius, radius, radius)
		});
	}

	private TextLabel Text(string text, int x, int y, int w, int h, float size, Color color, string face = "Medium")
	{
		return (TextLabel)Add(Label(text, x, y, w, h, size, color, face));
	}

	private TextLabel Label(string text, int x, int y, int w, int h, float size, Color color, string face = "Medium")
	{
		return new TextLabel
		{
			Text = text,
			Position2D = new Position2D(x, y),
			Size2D = new Size2D(w, h),
			PixelSize = size,
			FontFamily = "Quiet Inter " + face,
			TextColor = color,
			VerticalAlignment = VerticalAlignment.Center
		};
	}

	private void BuildPage()
	{
		Stopwatch stopwatch = Stopwatch.StartNew();
		if (focusAnimation != null)
		{
			focusAnimation.Stop();
			focusAnimation.Dispose();
			focusAnimation = null;
		}
		ParkArtwork();
		pageArtworkCold = 0;
		foreach (View item in scene)
		{
			Window.Default.Remove(item);
			item.Dispose();
		}
		scene.Clear();
		slots.Clear();
		widgetTime = (widgetDate = (widgetTemp = (widgetDesc = (widgetRange = (widgetPlace = null)))));
		tabs = new TextLabel[3];
		string[] array = new string[3] { "Apps", "Inputs", "Settings" };
		int[] array2 = new int[3] { 54, 221, 388 };
		int[] array3 = new int[3] { 153, 153, 182 };
		for (int i = 0; i < 3; i++)
		{
			tabs[i] = Text(array[i], array2[i], 36, array3[i], 68, 30f, muted);
			tabs[i].HorizontalAlignment = HorizontalAlignment.Center;
		}
		clock = Text(DateTime.Now.ToString("h:mm tt"), 1510, 52, 330, 36, 24f, muted);
		clock.HorizontalAlignment = HorizontalAlignment.End;
		if (page == 0)
		{
			BuildLibrary();
		}
		else if (page == 1)
		{
			RefreshInputSources();
			BuildInputs();
		}
		else
		{
			RefreshSettings();
			SettingsTile("Volume", "volume", "Select · Left / Right to adjust", "volume", 0, 0);
			SettingsTile("Brightness", "brightness", "Select · Left / Right to adjust", "brightness", 1, 0);
			SettingsTile("Game Mode", "game-mode", "Select to switch on or off", "game", 2, 0);
			SettingsTile("Sleep Timer", "sleeptimer", "Select to change the timer", "sleep", 3, 0);
			SettingsTile("Sound", "mute", "Select to mute or unmute", "mute", 0, 1);
			SettingsTile("Controllers", "controllers", "DualSense · hold PS + Create", "controller", 1, 1);
			SettingsTile("Network", "network", "Wi-Fi and connection setup", "network", 2, 1);
			SettingsTile("Advanced", "app:org.tizen.menu", "Open Samsung's full settings", "settings", 3, 1);
		}
		toolbarHint = Text("", 1480, 112, 360, 40, 24f, ink);
		toolbarHint.HorizontalAlignment = HorizontalAlignment.End;
		detail = Text("", 80, 1030, 1320, 35, 20f, muted);
		notice = Text("", 80, 1008, 1760, 34, 22f, accent);
		selected = Math.Max(0, Math.Min(selected, slots.Count - 1));
		UpdateFocus(animate: false);
		buildMilliseconds = stopwatch.ElapsedMilliseconds;
		VideoLog("buildpage ms=" + buildMilliseconds + " page=" + page);
		WriteState("page_ready");
	}

	private void BuildInputs()
	{
		if (inputSources.Count == 0)
		{
			Text("No connected inputs found.", 82, 310, 1000, 70, 34f, ink, "Semibold");
			return;
		}
		for (int i = 0; i < inputSources.Count; i++)
		{
			InputSource inputSource = inputSources[i];
			int num = i % 3;
			int num2 = i / 3;
			int num3 = 80 + num * 600;
			int num4 = 270 + num2 * 322;
			int num5 = 550;
			int num6 = 276;
			View shadow = Panel(num3 - 4, num4 + 8, num5 + 8, num6 + 8, new Color(0f, 0f, 0f, 0.5f), 24);
			View view = Panel(num3 + num5 / 2, num4 + num6 / 2, num5, num6, new Color(0.075f, 0.086f, 0.11f, 1f), 22);
			view.PivotPoint = new Position(0.5f, 0.5f, 0.5f);
			view.PositionUsesPivotPoint = true;
			if (!string.IsNullOrWhiteSpace(inputSource.IconPath))
			{
				view.Add(new ImageView
				{
					ResourceUrl = inputSource.IconPath,
					Position2D = new Position2D(28, 36),
					Size2D = new Size2D(156, 156),
					FittingMode = FittingModeType.ShrinkToFit
				});
			}
			string text = ((!string.IsNullOrWhiteSpace(inputSource.DetectedName)) ? inputSource.DetectedName : inputSource.EditName);
			string text2 = ((inputSource.SourceType == 0) ? "Live TV" : (string.IsNullOrWhiteSpace(text) ? "HDMI input" : Uri.UnescapeDataString(text)));
			view.Add(Label(text2, 210, 65, 310, 62, 34f, ink, "Semibold"));
			view.Add(Label((inputSource.SourceType == 0) ? "Broadcast channels" : "Connected HDMI device", 210, 134, 310, 44, 22f, muted));
			slots.Add(new Slot
			{
				Card = view,
				Shadow = shadow,
				Name = text2,
				Action = "hdmi:" + inputSource.SourceType,
				Description = "Open " + text2,
				Row = num2,
				X = num3,
				Y = num4,
				W = num5,
				H = num6
			});
		}
	}

	private void BuildLibrary()
	{
		if (library.Count == 0)
		{
			Text("Apps could not be loaded.", 80, 300, 1500, 70, 32f, ink);
			return;
		}
		libraryPage = Math.Clamp(libraryPage, 0, AppLibrary.PageCount(library.Count) - 1);
		int num = libraryPage * 10;
		int top = 128 + Math.Max(0, 110 + (900 - (500 + ((num2Rows(library.Count, libraryPage) - 1) * 245))) / 2 - 128) / 2;
		int num2 = AppLibrary.VisibleCount(library.Count, libraryPage);
		for (int i = 0; i < num2; i++)
		{
			LibraryApp libraryApp = library[num + i];
			int num7 = Math.Min(5, num2 - i / 5 * 5);
			int num3 = 80 + (1760 - ((num7 - 1) * 358 + 328)) / 2 + i % 5 * 358;
			int num4 = top + 264 + i / 5 * 245;
			int num5 = 328;
			int num6 = 184;
			View shadow = Panel(num3 - 5, num4 + 7, num5 + 10, num6 + 8, new Color(0.12f, 0.15f, 0.25f, 0.08f), 22);
			View view = Panel(num3 + num5 / 2, num4 + num6 / 2, num5, num6, HexColor(libraryApp.Background));
			view.PivotPoint = new Position(0.5f, 0.5f, 0.5f);
			view.PositionUsesPivotPoint = true;
			AddAppArtwork(view, libraryApp, num5, num6);
			View view2 = new View
			{
				Size2D = new Size2D(num5, num6),
				BackgroundColor = new Color(0f, 0f, 0f, 0f),
				CornerRadius = new Vector4(18f, 18f, 18f, 18f),
				BorderlineWidth = 4f,
				BorderlineColor = accent,
				Opacity = 0f
			};
			view.Add(view2);
			int pillW = Math.Min(num5, 18 * libraryApp.Name.Length + 52);
			Panel(num3 + (num5 - pillW) / 2, num4 + num6 + 16, pillW, 34, new Color(0f, 0f, 0f, 0.5f), 17);
			TextLabel label = Text(libraryApp.Name, num3, num4 + num6 + 14, num5, 38, 27f, ink, "Semibold");
			label.HorizontalAlignment = HorizontalAlignment.Center;
			slots.Add(new Slot
			{
				Card = view,
				Shadow = shadow,
				FocusRing = view2,
				Label = label,
				Name = libraryApp.Name,
				Action = "app:" + libraryApp.Id,
				Description = libraryApp.Description,
				Row = i / 5,
				X = num3,
				Y = num4,
				W = num5,
				H = num6
			});
		}
		BuildWidget(top);
		if (AppLibrary.PageCount(library.Count) > 1)
		{
			Text(libraryPage + 1 + " / " + AppLibrary.PageCount(library.Count), 1650, top + 224, 190, 30, 21f, muted).HorizontalAlignment = HorizontalAlignment.End;
		}
	}

	private static int num2Rows(int count, int page)
	{
		return Math.Max(1, (AppLibrary.VisibleCount(count, page) + 4) / 5);
	}

	private void BuildWidget(int top)
	{
		int num = top;
		View view = Panel(80, num, 1760, 214, new Color(0f, 0f, 0f, 0.5f), 30);
		view.BorderlineWidth = 1f;
		view.BorderlineColor = new Color(1f, 1f, 1f, 0.16f);
		widgetTime = Text("", 136, num + 8, 740, 132, 96f, white, "Display");
		widgetDate = Text("", 142, num + 142, 740, 52, 34f, ink, "Medium");
		Panel(1252, num + 36, 2, 142, new Color(1f, 1f, 1f, 0.16f), 1);
		widgetTemp = Text("", 1292, num + 20, 200, 84, 68f, white, "Display");
		widgetTempC = Text("", 1292, num + 106, 200, 84, 68f, ink, "Display");
		widgetDesc = Text("", 1510, num + 22, 322, 46, 36f, white, "Semibold");
		widgetRange = Text("", 1510, num + 74, 322, 36, 27f, ink, "Medium");
		widgetLow = Text("", 1510, num + 110, 322, 36, 27f, ink, "Medium");
		widgetPlace = Text("", 1510, num + 154, 322, 32, 23f, muted, "Medium");
		UpdateWidget();
	}

	private void UpdateWidget()
	{
		if (widgetTime == null)
		{
			return;
		}
		DateTime now = DateTime.Now;
		widgetTime.Text = now.ToString("h:mm") + " " + now.ToString("tt");
		widgetDate.Text = now.ToString("dddd, MMMM d");
		bool flag = weatherTemp != "" && DateTime.Now - weatherUpdated < TimeSpan.FromHours(12);
		widgetTemp.Text = flag ? weatherTemp : "";
		widgetTempC.Text = flag ? weatherTempC : "";
		widgetLow.Text = flag ? weatherLow : "";
		widgetDesc.Text = flag ? weatherDesc : "";
		widgetRange.Text = flag ? weatherRange : "";
		if (weatherBusy)
		{
			widgetPlace.Text = flag ? "Refreshing weather..." : "Retrieving weather...";
		}
		else
		{
			widgetPlace.Text = flag ? weatherPlace : "Weather unavailable";
		}
	}

	private static string WeatherText(int code)
	{
		switch (code)
		{
		case 0:
			return "Clear";
		case 1:
			return "Mostly clear";
		case 2:
			return "Partly cloudy";
		case 3:
			return "Overcast";
		case 45:
		case 48:
			return "Fog";
		case 51:
		case 53:
		case 55:
		case 56:
		case 57:
			return "Drizzle";
		case 61:
		case 63:
		case 65:
		case 66:
		case 67:
		case 80:
		case 81:
		case 82:
			return "Rain";
		case 71:
		case 73:
		case 75:
		case 77:
		case 85:
		case 86:
			return "Snow";
		case 95:
		case 96:
		case 99:
			return "Thunderstorms";
		default:
			return "";
		}
	}

	private static void WeatherLog(string line)
	{
		try
		{
			File.AppendAllText("/tmp/quiet-home-weather.txt", DateTime.UtcNow.ToString("o") + " " + line + "\n");
		}
		catch
		{
		}
	}

	private void LoadWeatherCache()
	{
		try
		{
			var cache = JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(WeatherCacheFile));
			if (cache == null) return;
			if (cache.TryGetValue("Temp", out var t)) weatherTemp = t ?? "";
			if (cache.TryGetValue("TempC", out var tc)) weatherTempC = tc ?? "";
			if (cache.TryGetValue("Desc", out var d)) weatherDesc = d ?? "";
			if (cache.TryGetValue("Range", out var rng)) weatherRange = rng ?? "";
			if (cache.TryGetValue("Low", out var lo)) weatherLow = lo ?? "";
			if (cache.TryGetValue("Place", out var pl)) weatherPlace = pl ?? "";
			if (cache.TryGetValue("UpdatedUtc", out var ts) && DateTime.TryParse(ts, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var dt))
				weatherUpdated = dt.ToLocalTime();
			WeatherLog("cache loaded age=" + (int)(DateTime.Now - weatherUpdated).TotalMinutes + "m " + weatherTemp);
		}
		catch (Exception ex)
		{
			WeatherLog("cache load: " + ex.GetType().Name);
		}
	}

	private void MaybeFetchWeather()
	{
		if (weatherBusy || DateTime.Now < weatherNextTry)
		{
			return;
		}
		string text;
		try
		{
			text = File.ReadAllText("/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/weather.json");
		}
		catch
		{
			weatherNextTry = DateTime.Now.AddMinutes(10);
			return;
		}
		weatherBusy = true;
		weatherNextTry = DateTime.Now.AddMinutes(2);
		Task.Run(async delegate
		{
			try
			{
				using JsonDocument cfg = JsonDocument.Parse(text);
				double lat = cfg.RootElement.GetProperty("Latitude").GetDouble();
				double lon = cfg.RootElement.GetProperty("Longitude").GetDouble();
				string place = (cfg.RootElement.TryGetProperty("Place", out var p) ? p.GetString() : "") ?? "";
				string units = (cfg.RootElement.TryGetProperty("Units", out var u) ? u.GetString() : "fahrenheit") ?? "fahrenheit";
				if (units != "celsius")
				{
					units = "fahrenheit";
				}
				string url = "https://api.open-meteo.com/v1/forecast?latitude=" + lat.ToString("0.00", CultureInfo.InvariantCulture) + "&longitude=" + lon.ToString("0.00", CultureInfo.InvariantCulture) + "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto&forecast_days=1";
				string body = await http.GetStringAsync(url);
				using JsonDocument doc = JsonDocument.Parse(body);
				JsonElement cur = doc.RootElement.GetProperty("current");
				JsonElement daily = doc.RootElement.GetProperty("daily");
				double t = cur.GetProperty("temperature_2m").GetDouble();
				int code = cur.GetProperty("weather_code").GetInt32();
				double hi = daily.GetProperty("temperature_2m_max")[0].GetDouble();
				double lo = daily.GetProperty("temperature_2m_min")[0].GetDouble();
				string fmt(double f) => Math.Round(f).ToString(CultureInfo.InvariantCulture) + "\u00b0F";
				string fmtC(double f) => Math.Round((f - 32.0) * 5.0 / 9.0).ToString(CultureInfo.InvariantCulture) + "\u00b0C";
				weatherTemp = fmt(t);
				weatherTempC = fmtC(t);
				weatherDesc = WeatherText(code);
				weatherRange = "High " + fmt(hi) + " / " + fmtC(hi);
				weatherLow = "Low " + fmt(lo) + " / " + fmtC(lo);
				weatherPlace = place;
				weatherUpdated = DateTime.Now;
				weatherNextTry = DateTime.Now.AddMinutes(20);
				WeatherLog("ok " + weatherTemp + " " + weatherDesc);
				try
				{
					var wc = new Dictionary<string, string>
					{
						["Temp"] = weatherTemp, ["TempC"] = weatherTempC, ["Desc"] = weatherDesc,
						["Range"] = weatherRange, ["Low"] = weatherLow, ["Place"] = weatherPlace,
						["UpdatedUtc"] = weatherUpdated.ToUniversalTime().ToString("o")
					};
					File.WriteAllText(WeatherCacheFile, JsonSerializer.Serialize(wc));
				}
				catch { }
			}
			catch (Exception ex)
			{
				WeatherLog("failed " + ex.GetType().Name + ": " + ex.Message);
			}
			finally
			{
				weatherBusy = false;
			}
		});
	}

	private void RestoreLastApp()
	{
		try
		{
			string id = File.ReadAllText(LastAppFile).Trim();
			int index = library.FindIndex((LibraryApp a) => a.Id == id && !a.Utility);
			if (index >= 0)
			{
				libraryPage = index / 10;
				selected = index % 10;
			}
			VideoLog("last app restored: " + id + " index=" + index);
		}
		catch (Exception ex)
		{
			VideoLog("last app restore skipped: " + ex.GetType().Name);
		}
	}

	private void SaveLastApp(string id)
	{
		try
		{
			if (library.Exists((LibraryApp a) => a.Id == id))
			{
				File.WriteAllText(LastAppFile, id);
				VideoLog("last app saved: " + id);
			}
		}
		catch (Exception ex)
		{
			VideoLog("last app save failed: " + ex.GetType().Name + " " + ex.Message);
		}
	}

	private void LoadFireConfig()
	{
		try
		{
			using JsonDocument doc = JsonDocument.Parse(File.ReadAllText("/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/fireplace.json"));
			JsonElement r = doc.RootElement;
			if (r.TryGetProperty("HomeVolume", out var a))
			{
				homeVolume = Math.Clamp((float)a.GetDouble(), 0f, 1f);
			}
			if (r.TryGetProperty("FireVolume", out var b))
			{
				fireVolume = Math.Clamp((float)b.GetDouble(), 0f, 1f);
			}
			if (r.TryGetProperty("FadeSeconds", out var c))
			{
				fadeSeconds = Math.Clamp((float)c.GetDouble(), 0.2f, 15f);
			}
			if (r.TryGetProperty("HoldMinutes", out var d))
			{
				holdMinutes = Math.Clamp(d.GetInt32(), 1, 600);
			}
		}
		catch
		{
		}
		curVolume = homeVolume;
		fadeTarget = homeVolume;
	}

	private void SetVideoVolume(float v)
	{
		curVolume = v;
		try
		{
			if (backdropVideo != null)
			{
				PropertyMap propertyMap = new PropertyMap();
				propertyMap.Add("volumeLeft", new PropertyValue(v));
				propertyMap.Add("volumeRight", new PropertyValue(v));
				backdropVideo.Volume = propertyMap;
			}
		}
		catch (Exception ex)
		{
			if (!volumeFailedLogged)
			{
				volumeFailedLogged = true;
				VideoLog("volume set failed: " + ex.GetType().Name + " " + ex.Message);
			}
		}
	}

	private void FadeVolumeTo(float target)
	{
		fadeTarget = target;
		fadeTimer?.Stop();
		float step = Math.Max(0.002f, Math.Abs(fireVolume - homeVolume) / (fadeSeconds * 25f));
		fadeTimer = new Timer(40u);
		fadeTimer.Tick += delegate
		{
			float num = fadeTarget - curVolume;
			if (Math.Abs(num) <= step)
			{
				SetVideoVolume(fadeTarget);
				return false;
			}
			SetVideoVolume(curVolume + ((num > 0f) ? step : (0f - step)));
			return true;
		};
		fadeTimer.Start();
	}

	private View MakeHint(string text, int x, int y, int w)
	{
		View view = new View
		{
			Position2D = new Position2D(x, y),
			Size2D = new Size2D(w, 64),
			BackgroundColor = new Color(0f, 0f, 0f, 0.55f),
			CornerRadius = new Vector4(32f, 32f, 32f, 32f),
			BorderlineWidth = 1f,
			BorderlineColor = new Color(1f, 1f, 1f, 0.18f),
			Opacity = 0f
		};
		TextLabel textLabel = Label(text, 0, 0, w, 64, 26f, white, "Medium");
		textLabel.HorizontalAlignment = HorizontalAlignment.Center;
		view.Add(textLabel);
		Window.Default.Add(view);
		return view;
	}

	private void BuildFireHints()
	{
		fireBottomHint = MakeHint("Press down on remote twice for fireplace mode", 560, 956, 800);
		fireTopHint = MakeHint("Press up twice or press HOME to exit fireplace mode", 410, 60, 1100);
	}

	private void FadeView(View v, float to)
	{
		if (v == null)
		{
			return;
		}
		if (to > 0f)
		{
			v.RaiseToTop();
		}
		Animation a = new Animation(250);
		a.AnimateTo(v, "Opacity", to);
		a.Finished += delegate
		{
			a.Dispose();
		};
		a.Play();
	}

	private void ShowBottomHint()
	{
		fireHint = true;
		fireDownCount = 0;
		FadeView(fireBottomHint, 1f);
		RestartHintTimer(ref bottomHintTimer, 4500u, HideBottomHint);
	}

	private void HideBottomHint()
	{
		fireHint = false;
		fireDownCount = 0;
		bottomHintTimer?.Stop();
		FadeView(fireBottomHint, 0f);
	}

	private void ShowTopHint()
	{
		FadeView(fireTopHint, 1f);
		RestartHintTimer(ref topHintTimer, 4000u, delegate
		{
			FadeView(fireTopHint, 0f);
		});
	}

	private void RestartHintTimer(ref Timer t, uint ms, Action done)
	{
		t?.Stop();
		Timer timer = new Timer(ms);
		timer.Tick += delegate
		{
			done();
			return false;
		};
		timer.Start();
		t = timer;
	}

	private void FireDownAtBottom()
	{
		if (!fireHint)
		{
			ShowBottomHint();
			return;
		}
		fireDownCount++;
		if (fireDownCount >= 2)
		{
			HideBottomHint();
			EnterFireplace();
		}
		else
		{
			RestartHintTimer(ref bottomHintTimer, 4500u, HideBottomHint);
		}
	}

	private void SlideScene(float dy, bool animate)
	{
		if (animate)
		{
			Animation a = new Animation(750);
			AlphaFunction ease = new AlphaFunction(AlphaFunction.BuiltinFunctions.EaseInOutSine);
			foreach (View v in scene)
			{
				a.AnimateBy(v, "PositionY", dy, ease);
			}
			a.Finished += delegate
			{
				a.Dispose();
			};
			a.Play();
		}
		else
		{
			foreach (View v2 in scene)
			{
				v2.PositionY += dy;
			}
		}
	}

	private void LockDisplay()
	{
		if (powerLocked)
		{
			return;
		}
		try
		{
			Power.RequestLock(PowerLock.DisplayNormal, 0);
			powerLocked = true;
			VideoLog("display lock on");
		}
		catch (Exception ex)
		{
			VideoLog("display lock failed: " + ex.GetType().Name + " " + ex.Message);
		}
	}

	private void UnlockDisplay()
	{
		if (!powerLocked)
		{
			return;
		}
		powerLocked = false;
		try
		{
			Power.ReleaseLock(PowerLock.DisplayNormal);
			VideoLog("display lock off");
		}
		catch (Exception ex)
		{
			VideoLog("display unlock failed: " + ex.GetType().Name + " " + ex.Message);
		}
	}

	private void StartHold()
	{
		holdTimer?.Stop();
		fireExpired = false;
		LockDisplay();
		Timer timer = new Timer((uint)(holdMinutes * 60000));
		timer.Tick += delegate
		{
			fireExpired = true;
			UnlockDisplay();
			try
			{
				backdropVideo?.Pause();
			}
			catch
			{
			}
			VideoLog("fireplace hold expired; display lock released, video paused");
			return false;
		};
		timer.Start();
		holdTimer = timer;
	}

	private void EnterFireplace()
	{
		fireplace = true;
		fireUpCount = 0;
		SlideScene(-1200f, animate: true);
		if (dimOverlay != null)
		{
			Animation a = new Animation(750);
			a.AnimateTo(dimOverlay, "Opacity", 0.3f);
			a.Finished += delegate
			{
				a.Dispose();
			};
			a.Play();
		}
		FadeVolumeTo(fireVolume);
		StartHold();
		ShowTopHint();
		VideoLog("fireplace on");
	}

	private void ExitFireplace(bool animate)
	{
		if (!fireplace)
		{
			return;
		}
		fireplace = false;
		holdTimer?.Stop();
		UnlockDisplay();
		SlideScene(1200f, animate);
		if (dimOverlay != null)
		{
			dimOverlay.Opacity = 1f;
		}
		try
		{
			if (fireExpired)
			{
				backdropVideo?.Play();
			}
		}
		catch
		{
		}
		fireExpired = false;
		FadeVolumeTo(homeVolume);
		topHintTimer?.Stop();
		if (fireTopHint != null)
		{
			fireTopHint.Opacity = 0f;
		}
		VideoLog("fireplace off");
	}

	private void HandleFireplaceKey(string key)
	{
		if (fireExpired)
		{
			try
			{
				backdropVideo?.Play();
			}
			catch
			{
			}
			StartHold();
			ShowTopHint();
			return;
		}
		switch (key)
		{
		case "XF86Back":
		case "Back":
		case "Escape":
		case "XF86Exit":
			ExitFireplace(animate: true);
			return;
		case "Up":
		{
			long tickCount = Environment.TickCount64;
			if (tickCount - fireUpAt > 3000)
			{
				fireUpCount = 0;
			}
			fireUpAt = tickCount;
			fireUpCount++;
			if (fireUpCount >= 2)
			{
				ExitFireplace(animate: true);
				return;
			}
			break;
		}
		}
		ShowTopHint();
	}

	private Color HexColor(string hex)
	{
		try
		{
			int num = Convert.ToInt32(hex.TrimStart('#'), 16);
			return new Color((float)((num >> 16) & 0xFF) / 255f, (float)((num >> 8) & 0xFF) / 255f, (float)(num & 0xFF) / 255f, 1f);
		}
		catch
		{
			return white;
		}
	}

	private void AddAppArtwork(View card, LibraryApp app, int w, int h)
	{
		if (!app.Utility)
		{
			CachedArtwork artwork = GetArtwork(app, w, h);
			if (artwork.Image.LoadingStatus != ImageView.LoadingStatusType.Ready)
			{
				pageArtworkCold++;
			}
			artwork.Parent.Remove(artwork.Image);
			card.Add(artwork.Image);
			artwork.Parent = card;
		}
		if (app.Utility)
		{
			card.Add(new View
			{
				Position2D = new Position2D(w / 2 - 28, h / 2 - 2),
				Size2D = new Size2D(56, 4),
				BackgroundColor = ink
			});
			card.Add(new View
			{
				Position2D = new Position2D(w / 2 - 2, h / 2 - 28),
				Size2D = new Size2D(4, 56),
				BackgroundColor = ink
			});
		}
	}

	private void PreloadArtwork()
	{
		artworkPreloadRoot = new View
		{
			Size2D = new Size2D(1920, 1080),
			Opacity = 0f
		};
		Window.Default.Add(artworkPreloadRoot);
		foreach (LibraryApp item in library)
		{
			if (!item.Utility)
			{
				GetArtwork(item, 328, 184);
			}
		}
		string[] array = new string[3] { "org.tizen.netflix-app", "com.samsung.tv.cobalt-yt", "org.tizen.primevideo" };
		foreach (string id in array)
		{
			LibraryApp libraryApp = library.Find((LibraryApp a) => a.Id == id);
			if (libraryApp != null)
			{
				GetArtwork(libraryApp, 253, 126);
			}
		}
	}

	private CachedArtwork GetArtwork(LibraryApp app, int w, int h)
	{
		string key = app.Id + "@" + w + "x" + h;
		if (artworkCache.TryGetValue(key, out var value))
		{
			return value;
		}
		bool flag = app.Fit == "cover";
		int num;
		int num2;
		if (!flag)
		{
			num = ((app.Fit == "contain-full") ? 1 : 0);
			if (num == 0)
			{
				num2 = w - 54;
				goto IL_007c;
			}
		}
		else
		{
			num = 1;
		}
		num2 = w;
		goto IL_007c;
		IL_007c:
		int num3 = num2;
		int num4 = ((num != 0) ? h : (h - 40));
		float[] crop = app.Crop;
		float num5 = ((crop == null) ? 1f : crop[2]);
		float num6 = ((crop == null) ? 1f : crop[3]);
		ImageView imageView = new ImageView
		{
			Position2D = new Position2D((w - num3) / 2, (h - num4) / 2),
			Size2D = new Size2D(num3, num4),
			FittingMode = (flag ? FittingModeType.ScaleToFill : FittingModeType.ShrinkToFit),
			SamplingMode = SamplingModeType.BoxThenLanczos,
			DesiredWidth = (int)Math.Ceiling((float)(num3 * 2) / num5),
			DesiredHeight = (int)Math.Ceiling((float)(num4 * 2) / num6),
			ReleasePolicy = ReleasePolicyType.Destroyed,
			CornerRadius = new Vector4(18f, 18f, 18f, 18f)
		};
		if (crop != null)
		{
			imageView.PixelArea = new RelativeVector4(crop[0], crop[1], crop[2], crop[3]);
		}
		value = new CachedArtwork
		{
			Image = imageView,
			Parent = artworkPreloadRoot
		};
		artworkCache.Add(key, value);
		artworkViewsCreated++;
		imageView.ResourceReady += delegate
		{
			WriteState("artwork_ready");
		};
		artworkPreloadRoot.Add(imageView);
		imageView.ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/" + app.Asset;
		return value;
	}

	private void ParkArtwork()
	{
		foreach (CachedArtwork value in artworkCache.Values)
		{
			if (value.Parent != artworkPreloadRoot)
			{
				value.Parent.Remove(value.Image);
				artworkPreloadRoot.Add(value.Image);
				value.Parent = artworkPreloadRoot;
			}
		}
	}

	private int ArtworkReadyCount()
	{
		int num = 0;
		foreach (CachedArtwork value in artworkCache.Values)
		{
			if (value.Image.LoadingStatus == ImageView.LoadingStatusType.Ready)
			{
				num++;
			}
		}
		return num;
	}

	private string ArtworkPending()
	{
		List<string> list = new List<string>();
		foreach (KeyValuePair<string, CachedArtwork> item in artworkCache)
		{
			if (item.Value.Image.LoadingStatus != ImageView.LoadingStatusType.Ready)
			{
				list.Add(item.Key + ":" + item.Value.Image.LoadingStatus);
			}
		}
		return string.Join(";", list);
	}

	private void SettingsTile(string name, string action, string description, string icon, int column, int row)
	{
		int num = 80 + column * 450;
		int num2 = 262 + row * 332;
		int num3 = 410;
		int num4 = 286;
		View view = Panel(num + num3 / 2, num2 + num4 / 2, num3, num4, new Color(0f, 0f, 0f, 0.5f), 28);
		view.PivotPoint = new Position(0.5f, 0.5f, 0.5f);
		view.PositionUsesPivotPoint = true;
		view.BorderlineWidth = 1f;
		view.BorderlineColor = new Color(1f, 1f, 1f, 0.16f);
		view.Add(new View
		{
			Position2D = new Position2D(26, 26),
			Size2D = new Size2D(72, 72),
			BackgroundColor = new Color(1f, 1f, 1f, 0.12f),
			CornerRadius = new Vector4(36f, 36f, 36f, 36f)
		});
		view.Add(new ImageView
		{
			ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/lucide-" + icon + ".svg",
			Position2D = new Position2D(42, 42),
			Size2D = new Size2D(40, 40)
		});
		view.Add(Label(name, 116, 34, 270, 56, 29f, white, "Semibold"));
		TextLabel textLabel = Label("", 26, 128, 358, 72, 44f, white, "Display");
		view.Add(textLabel);
		view.Add(Label(description, 26, 218, 358, 40, 20f, ink));
		slots.Add(new Slot
		{
			Card = view,
			Label = textLabel,
			Name = name,
			Action = action,
			Description = description,
			Row = row,
			X = num,
			Y = num2,
			W = num3,
			H = num4
		});
	}

	private Slot Feature(string label, string action, string description, string asset, int x, int y, int w, int h, string shape)
	{
		View shadow = Add(new ImageView
		{
			ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/shadow-" + shape + ".svg",
			Position2D = new Position2D(x - 24, y - 10),
			Size2D = new Size2D(w + 48, h + 64)
		});
		View view = Panel(x + w / 2, y + h / 2, w, h, new Color(0f, 0f, 0f, 0f));
		view.PivotPoint = new Position(0.5f, 0.5f, 0.5f);
		view.PositionUsesPivotPoint = true;
		view.Add(new ImageView
		{
			ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/" + asset,
			Size2D = new Size2D(w, h)
		});
		TextLabel label2 = Text(label, x, 716, w, 45, 31f, ink, "Semibold");
		Text(description, x, 760, w, 36, 24f, muted);
		Slot slot = new Slot
		{
			Card = view,
			Shadow = shadow,
			Label = label2,
			Name = label,
			Action = action,
			Description = description,
			Row = 0,
			X = x,
			Y = y,
			W = w,
			H = h
		};
		slots.Add(slot);
		return slot;
	}

	private void Dock(string label, string action, string asset, int n)
	{
		int num = (int)Math.Round(80.0 + (double)n * 301.33299999999997);
		View shadow = Add(new ImageView
		{
			ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/shadow-dock.svg",
			Position2D = new Position2D(num - 24, 842),
			Size2D = new Size2D(301, 190)
		});
		View view = Panel(num + 126, 917, 253, 126, new Color(0f, 0f, 0f, 0f), 22);
		view.PivotPoint = new Position(0.5f, 0.5f, 0.5f);
		view.PositionUsesPivotPoint = true;
		LibraryApp libraryApp = library.Find((LibraryApp a) => a.Id == action.Substring(action.IndexOf(':') + 1));
		if (libraryApp != null)
		{
			view.BackgroundColor = HexColor(libraryApp.Background);
			AddAppArtwork(view, libraryApp, 253, 126);
		}
		else
		{
			view.Add(new ImageView
			{
				ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/free-dock-" + asset + ".svg",
				Size2D = new Size2D(253, 126)
			});
		}
		slots.Add(new Slot
		{
			Card = view,
			Shadow = shadow,
			Name = label,
			Action = action,
			Description = label,
			Row = 1,
			X = num,
			Y = 854,
			W = 253,
			H = 126
		});
	}

	private void Toolbar(string label, string action, string icon, int n)
	{
		int num = 1596 + n * 88;
		View view = Panel(num + 34, 70, 68, 68, new Color(0f, 0f, 0f, 0f), 34);
		view.PivotPoint = new Position(0.5f, 0.5f, 0.5f);
		view.PositionUsesPivotPoint = true;
		view.Add(new ImageView
		{
			ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/button-glass.svg",
			Size2D = new Size2D(68, 68)
		});
		View view2 = new View
		{
			Size2D = new Size2D(68, 68),
			BackgroundColor = new Color(1f, 1f, 1f, 0.94f),
			CornerRadius = new Vector4(34f, 34f, 34f, 34f),
			Opacity = 0f
		};
		view.Add(view2);
		view.Add(new ImageView
		{
			ResourceUrl = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/icon-" + icon + ".svg",
			Color = white,
			Position2D = new Position2D(17, 17),
			Size2D = new Size2D(34, 34)
		});
		slots.Add(new Slot
		{
			Card = view,
			FocusRing = view2,
			Name = label,
			Action = action,
			Description = label,
			Row = -1,
			X = num,
			Y = 36,
			W = 68,
			H = 68
		});
	}

	private List<int> Row(int row)
	{
		List<int> list = new List<int>();
		for (int i = 0; i < slots.Count; i++)
		{
			if (slots[i].Row == row)
			{
				list.Add(i);
			}
		}
		return list;
	}

	private void UpdateFocus(bool animate = true)
	{
		if (focusAnimation != null)
		{
			focusAnimation.Stop();
			focusAnimation.Dispose();
			focusAnimation = null;
		}
		if (animate)
		{
			focusAnimation = new Animation(180);
		}
		for (int i = 0; i < 3; i++)
		{
			tabs[i].TextColor = ((i == page) ? ink : muted);
			tabs[i].FontFamily = "Quiet Inter " + ((i == page) ? "Semibold" : "Medium");
			tabs[i].BackgroundColor = ((area == 0 && i == page) ? new Color(1f, 1f, 1f, 0.7f) : new Color(0f, 0f, 0f, 0f));
			tabs[i].CornerRadius = new Vector4(34f, 34f, 34f, 34f);
		}
		for (int j = 0; j < slots.Count; j++)
		{
			Slot slot = slots[j];
			bool flag = area != 0 && selected == j;
			float num = ((!flag) ? 1f : ((page == 1 && slot.Row >= 0) ? 1.055f : ((page == 2 && slot.Row >= 0) ? 1.035f : ((slot.Row == 0) ? 1.05f : ((slot.Row == 1) ? 1.2f : 1.1f)))));
			slot.Card.BorderlineWidth = ((page != 1 || slot.Row < 0) ? ((slot.Row == 0) ? 1 : 0) : ((!flag) ? 1 : 4));
			slot.Card.BorderlineColor = ((page == 1 && flag) ? accent : new Color(1f, 1f, 1f, flag ? 0.8f : 0.28f));
			if (page == 2 && slot.Row >= 0)
			{
				slot.Card.BorderlineWidth = (flag ? 3f : 1f);
				slot.Card.BorderlineColor = new Color(1f, 1f, 1f, flag ? 0.9f : 0.16f);
				slot.Card.BackgroundColor = (flag ? new Color(1f, 1f, 1f, 0.18f) : new Color(0f, 0f, 0f, 0.5f));
			}
			Position position = new Position((float)slot.X + (float)slot.W / 2f, (float)slot.Y + (float)slot.H / 2f - (float)((flag && (slot.Row == 0 || (page == 1 && slot.Row >= 0))) ? 5 : 0));
			if (animate)
			{
				focusAnimation.AnimateTo(slot.Card, "Scale", new Vector3(num, num, 1f));
				focusAnimation.AnimateTo(slot.Card, "Position", position);
			}
			else
			{
				slot.Card.Scale = new Vector3(num, num, 1f);
				slot.Card.Position = position;
			}
			if (slot.Shadow != null)
			{
				slot.Shadow.Opacity = (flag ? 1f : 0.55f);
			}
			if (slot.FocusRing != null)
			{
				slot.FocusRing.Opacity = (flag ? 1 : 0);
			}
			if (slot.Label != null && page != 2)
			{
				slot.Label.FontFamily = "Quiet Inter " + (flag ? "Semibold" : "Medium");
			}
			if (slot.Row == -1 && slot.Card.ChildCount >= 3)
			{
				ImageView imageView = slot.Card.GetChildAt(2) as ImageView;
				if (imageView != null)
				{
					imageView.Color = (flag ? new Color(0.06f, 0.07f, 0.1f, 1f) : white);
				}
				slot.Card.BackgroundColor = ((!flag && j == page) ? new Color(1f, 1f, 1f, 0.16f) : new Color(0f, 0f, 0f, 0f));
			}
			if (flag)
			{
				slot.Card.RaiseToTop();
			}
		}
		if (focusAnimation != null)
		{
			focusAnimation.Play();
		}
		clock.Opacity = ((page != 0 && area != 3) ? 1 : 0);
		toolbarHint.Text = ((area == 3) ? slots[selected].Name : "");
		detail.Text = ((page == 1 && area == 1 && slots[selected].Row >= 0) ? (slots[selected].Name + " · " + slots[selected].Description) : ((area == 0) ? "" : ((area == 2) ? slots[selected].Name : "")));
		if (page == 2)
		{
			slots[0].Label.Text = ((currentVolume < 0) ? "Unavailable" : currentVolume.ToString());
			slots[1].Label.Text = SettingName("brightness");
			slots[2].Label.Text = SettingName("game-mode");
			slots[3].Label.Text = SettingName("sleeptimer");
			slots[4].Label.Text = ((currentMute < 0) ? "Unavailable" : ((currentMute == 1) ? "Muted" : "Sound on"));
			slots[5].Label.Text = "Pair controller";
			slots[6].Label.Text = "Connections";
			slots[7].Label.Text = "More settings";
			detail.Text = "";
		}
		if (editing != "")
		{
			detail.Text = "Left / Right to adjust " + editing + " · Select or Back to finish";
		}
		WriteState("focus");
	}

	private void OnKey(object sender, Window.KeyEventArgs e)
	{
		if (e.Key == null || e.Key.State != 0)
		{
			return;
		}
		string keyPressedName = e.Key.KeyPressedName;
		long tickCount = Environment.TickCount64;
		if (keyPressedName == lastKey && tickCount - lastKeyAt < 180)
		{
			return;
		}
		lastKey = keyPressedName;
		lastKeyAt = tickCount;
		try
		{
			switch (keyPressedName)
			{
			case "XF86KeyAIMenu":
				OpenSourcePanel("ai_key", lowerAfter: false);
				return;
			case "XF86Home":
				Home("home_key");
				return;
			case "XF86SysMenu":
			case "XF86More":
				OpenSettings("settings_key");
				return;
			}
			if (fireplace)
			{
				HandleFireplaceKey(keyPressedName);
				return;
			}
			if (page == 0 && HandleLibraryKey(keyPressedName))
			{
				return;
			}
			if (editing != "")
			{
				switch (keyPressedName)
				{
				case "Left":
				case "Right":
				{
					int delta = ((!(keyPressedName == "Left")) ? 1 : (-1));
					if (editing == "volume")
					{
						ChangeVolume(delta);
					}
					else
					{
						ChangeBrightness(delta);
					}
					break;
				}
				case "Return":
				case "KP_Enter":
				case "XF86Back":
				case "Back":
				case "Escape":
					editing = "";
					UpdateFocus();
					break;
				}
				return;
			}
			switch (keyPressedName)
			{
			case "Up":
				if (area == 2)
				{
					int num2 = Row(1).IndexOf(selected);
					List<int> upRow = Row(0);
					area = 1;
					if (upRow.Count > 0)
					{
						selected = upRow[(page == 1 || page == 2) ? Math.Clamp(num2, 0, upRow.Count - 1) : 0];
					}
				}
				else if (area == 1)
				{
					area = 0;
				}
				UpdateFocus();
				break;
			case "Down":
				if (area == 0 || area == 3)
				{
					List<int> firstRow = Row(0);
					if (firstRow.Count > 0)
					{
						area = 1;
						selected = firstRow[0];
					}
				}
				else if (area == 1)
				{
					int num = Row(0).IndexOf(selected);
					List<int> nextRow = Row(1);
					if (nextRow.Count > 0)
					{
						area = 2;
						selected = nextRow[(page == 1 || page == 2) ? Math.Clamp(num, 0, nextRow.Count - 1) : 0];
					}
				}
				UpdateFocus();
				break;
			case "Left":
			case "Right":
			{
				int num3 = ((!(keyPressedName == "Left")) ? 1 : (-1));
				if (area == 0)
				{
					page = (page + num3 + 3) % 3;
					selected = 0;
					BuildPage();
				}
				else if (area == 3)
				{
					List<int> list = Row(-1);
					int num5 = list.IndexOf(selected) + num3;
					if (num5 < 0 || num5 >= list.Count)
					{
						area = 0;
						page = ((num5 < 0) ? 2 : 0);
						selected = 0;
						BuildPage();
					}
					else
					{
						selected = list[num5];
						UpdateFocus();
					}
				}
				else
				{
					List<int> list2 = Row(area - 1);
					if (list2.Count == 0)
					{
						area = 1;
						list2 = Row(0);
					}
					if (list2.Count > 0)
					{
						int num6 = list2.IndexOf(selected);
						selected = list2[(num6 + num3 + list2.Count) % list2.Count];
					}
					UpdateFocus();
				}
				break;
			}
			case "Return":
			case "KP_Enter":
				if (area == 0)
				{
					area = 1;
					selected = 0;
					UpdateFocus();
				}
				else
				{
					Activate();
				}
				break;
			case "XF86Back":
			case "Back":
			case "Escape":
			case "XF86Exit":
				SelectSource(lastSource);
				break;
			}
		}
		catch (Exception ex)
		{
			ShowError(ex.Message);
		}
	}

	private bool HandleLibraryKey(string key)
	{
		switch (key)
		{
		case "XF86Back":
		case "Back":
		case "Escape":
		case "XF86Exit":
			Home("apps_back");
			return true;
		default:
			if (fireHint && key != "Down")
			{
				HideBottomHint();
			}
			if (library.Count == 0)
			{
				if (!(key == "Up"))
				{
					return key == "Down";
				}
				return true;
			}
			if ((area == 0 || area == 3) && key == "Down")
			{
				area = 1;
				selected = 0;
				UpdateFocus();
				return true;
			}
			if (area != 1)
			{
				return false;
			}
			switch (key)
			{
			case "Left":
			case "Right":
			case "Up":
			case "Down":
			{
				int num = AppLibrary.Move(library.Count, libraryPage * 10 + selected, key);
				if (num < 0)
				{
					area = 0;
					UpdateFocus();
					return true;
				}
				if (key == "Down" && num == libraryPage * 10 + selected)
				{
					FireDownAtBottom();
					return true;
				}
				if (fireHint)
				{
					HideBottomHint();
				}
				int num2 = num / 10;
				selected = num % 10;
				if (num2 != libraryPage)
				{
					libraryPage = num2;
					BuildPage();
				}
				else
				{
					UpdateFocus();
				}
				return true;
			}
			default:
				return false;
			}
		}
	}

	private void Activate()
	{
		string action = slots[selected].Action;
		notice.Text = "";
		if (action.StartsWith("hdmi:"))
		{
			SelectSource(int.Parse(action.Substring(5)));
			return;
		}
		if (action.StartsWith("page:"))
		{
			page = int.Parse(action.Substring(5));
			selected = 0;
			area = 1;
			BuildPage();
			return;
		}
		if (action.StartsWith("app:"))
		{
			SaveLastApp(action.Substring(4));
			Launch(action.Substring(4));
			return;
		}
		switch (action)
		{
		case "controllers":
			Launch("org.tizen.menu", "add-bluetooth-keyboard");
			break;
		case "network":
			Launch("org.tizen.menu", "networksettings");
			break;
		case "volume":
		case "brightness":
			RefreshSettings();
			if (action == "brightness" && !CanEdit(action))
			{
				ShowError("Brightness is unavailable for the current input.");
				break;
			}
			editing = action;
			UpdateFocus();
			break;
		case "game-mode":
			RefreshSettings();
			SetSetting(action, (SettingValue(action) == "1") ? "0" : "1");
			break;
		case "sleeptimer":
		{
			RefreshSettings();
			if (int.TryParse(SettingValue(action), out var result))
			{
				SetSetting(action, ((result + 1) % 5).ToString());
			}
			break;
		}
		case "mute":
		{
			int value;
			int num = sound_manager_get_master_mute(out value);
			if (num == 0)
			{
				num = sound_manager_set_master_mute((value != 1) ? 1 : 0);
			}
			if (num != 0)
			{
				ShowError("Use the remote's mute button.");
			}
			RefreshSettings();
			UpdateFocus();
			WriteState("mute_changed");
			break;
		}
		}
	}

	private void RefreshSettings()
	{
		currentVolume = ((sound_manager_get_master_volume(out var value) == 0) ? value : (-1));
		currentMute = ((sound_manager_get_master_mute(out var value2) == 0) ? value2 : (-1));
		string[] array = new string[3] { "brightness", "game-mode", "sleeptimer" };
		foreach (string text in array)
		{
			try
			{
				if (CSharpGetItemValue(text, out var name, out var value3) && !string.IsNullOrEmpty(value3))
				{
					settingValues[text] = value3;
					settingNames[text] = name;
				}
				else
				{
					settingValues.Remove(text);
					settingNames.Remove(text);
				}
				settingEnabled[text] = CSharpGetItemEnable(text, out var enabled) && enabled;
			}
			catch
			{
				settingValues.Remove(text);
				settingNames.Remove(text);
				settingEnabled[text] = false;
			}
		}
		try
		{
			if (!CSharpGetItemMinMaxStepValue("brightness", out brightnessMin, out brightnessMax, out brightnessStep) || brightnessStep <= 0.0)
			{
				brightnessMin = 0.0;
				brightnessMax = 50.0;
				brightnessStep = 1.0;
			}
		}
		catch
		{
		}
	}

	private string SettingValue(string id)
	{
		if (!settingValues.TryGetValue(id, out var value))
		{
			return "";
		}
		return value;
	}

	private string SettingName(string id)
	{
		if (!settingNames.TryGetValue(id, out var value))
		{
			return "Unavailable";
		}
		return value;
	}

	private bool CanEdit(string id)
	{
		if (settingEnabled.TryGetValue(id, out var value) && value)
		{
			return settingValues.ContainsKey(id);
		}
		return false;
	}

	private void SetSetting(string id, string value)
	{
		if (!CanEdit(id))
		{
			ShowError("This setting is unavailable for the current input.");
			return;
		}
		bool flag = false;
		try
		{
			flag = CSharpSetItemValue(id, value);
		}
		catch
		{
		}
		RefreshSettings();
		UpdateFocus();
		bool flag2 = flag && SettingValue(id) == value;
		if (!flag2)
		{
			ShowError("The TV could not apply this setting. Try Advanced settings.");
		}
		WriteState("setting:" + id + ":" + value + ":" + flag2);
	}

	private void ChangeBrightness(int delta)
	{
		if (double.TryParse(SettingValue("brightness"), NumberStyles.Float, CultureInfo.InvariantCulture, out var result))
		{
			SetSetting("brightness", Math.Max(brightnessMin, Math.Min(brightnessMax, result + (double)delta * brightnessStep)).ToString(CultureInfo.InvariantCulture));
		}
	}

	private void ChangeVolume(int delta)
	{
		int value;
		int num = sound_manager_get_master_volume(out value);
		if (num == 0)
		{
			num = sound_manager_set_master_volume(Math.Max(0, Math.Min(100, value + delta)));
		}
		if (num != 0)
		{
			ShowError("Use the remote's volume buttons.");
		}
		RefreshSettings();
		UpdateFocus();
		WriteState("volume_changed");
	}

	private void SelectSource(int source)
	{
		int num = connect_source(source);
		if (num < 0)
		{
			ShowError("Input could not be switched. Open Advanced settings to check the connection.");
			WriteState("source_failed:" + num);
		}
		else
		{
			lastSource = source;
			Launch("org.tizen.tv-viewer");
		}
	}

	private void Launch(string id, string menuItem = null)
	{
		if (app_control_create(out var app) != 0)
		{
			ShowError("Could not open the app.");
			return;
		}
		try
		{
			int num = app_control_set_app_id(app, id);
			if (num == 0)
			{
				num = app_control_set_operation(app, "http://tizen.org/appcontrol/operation/default");
			}
			if (num == 0 && id == "org.tizen.menu")
			{
				if (menuItem != null)
				{
					num = app_control_add_extra_data(app, "menuitem", menuItem);
					if (num == 0)
					{
						num = app_control_add_extra_data(app, "launchoption", "pressed");
					}
				}
				if (num == 0)
				{
					num = app_control_add_extra_data(app, "__K_EX_FORCE_BOOST", "enable");
				}
				if (num == 0)
				{
					num = app_control_add_extra_data(app, "__K_SPLASH_SCREEN", "LA_UI_VR_TRANSPARENT");
				}
			}
			if (num == 0)
			{
				num = app_control_send_launch_request(app, IntPtr.Zero, IntPtr.Zero);
			}
			WriteState("launch:" + id + ((menuItem == null) ? "" : (":" + menuItem)) + ":" + num);
			if (num != 0)
			{
				ShowError("Could not open this screen. Try Advanced settings.");
			}
		}
		finally
		{
			app_control_destroy(app);
		}
	}

	private void OpenSourcePanel(string why, bool lowerAfter)
	{
		int num = app_control_create(out var app);
		if (num != 0)
		{
			VideoLog("source panel: create failed " + num);
			return;
		}
		try
		{
			num = app_control_set_app_id(app, "com.samsung.tv.csfs");
			if (num == 0)
			{
				num = app_control_set_operation(app, "http://tizen.org/appcontrol/operation/default");
			}
			if (num == 0)
			{
				num = app_control_add_extra_data(app, "entry_point", "source_key");
			}
			if (num == 0)
			{
				num = app_control_add_extra_data(app, "__NO_RAISE_WINDOW", "enable");
			}
			if (num == 0)
			{
				num = app_control_send_launch_request(app, IntPtr.Zero, IntPtr.Zero);
			}
			VideoLog("source panel (" + why + ") rc=" + num);
		}
		finally
		{
			app_control_destroy(app);
		}
		if (lowerAfter)
		{
			try
			{
				Window.Default.Lower();
				VideoLog("window lowered");
			}
			catch (Exception ex)
			{
				VideoLog("lower failed: " + ex.GetType().Name);
			}
		}
	}

	private void ShowError(string text)
	{
		notice.Text = text;
	}

	private void WriteState(string activity)
	{
		try
		{
			File.WriteAllText("/tmp/quiet-home-state.txt", DateTime.UtcNow.ToString("o") + "\npage=" + page + "\nselected=" + selected + "\narea=" + area + "\nactivity=" + activity + "\nkey=" + lastKey + "\nfont_loaded=" + fontLoaded + "\nstyle=free-my-tv\nbuild_ms=" + buildMilliseconds + "\nlibrary_page=" + libraryPage + "\nlibrary_count=" + library.Count + "\nlibrary_error=" + libraryError + "\nselected_name=" + ((selected >= 0 && selected < slots.Count) ? slots[selected].Name : "") + "\nartwork_cached=" + artworkCache.Count + "\nartwork_ready=" + ArtworkReadyCount() + "\nartwork_pending=" + ArtworkPending() + "\nartwork_views_created=" + artworkViewsCreated + "\npage_artwork_cold=" + pageArtworkCold + "\nprocess_id=" + Process.GetCurrentProcess().Id + "\nediting=" + editing + "\nvolume=" + currentVolume + "\nmute=" + currentMute + "\nbrightness=" + SettingValue("brightness") + "\ngame-mode=" + SettingValue("game-mode") + "\nsleeptimer=" + SettingValue("sleeptimer") + "\n");
		}
		catch
		{
		}
	}

	public static void Main(string[] args)
	{
		using QuietHome quietHome = new QuietHome((VideoMode() == "underlay") ? WindowMode.Transparent : WindowMode.Opaque);
		quietHome.Run(args);
	}
}
