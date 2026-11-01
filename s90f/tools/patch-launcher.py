from pathlib import Path
import sys

# Historical development helper. The committed QuietHome.cs already contains
# these patches; running this against it will fail the exact-count guards.
repo = Path(__file__).resolve().parents[2]
p = Path(sys.argv[1]) if len(sys.argv) > 1 else repo / ".local/s90f-src/QuietHome.cs"
s = p.read_text()

def repl(old, new, label):
    global s
    n = s.count(old)
    print(label, "count", n)
    if n != 1:
        raise SystemExit("unexpected count for " + label)
    s = s.replace(old, new)

# 1. Add the static backdrop before the video is created so the 5s video
#    construction is not a black screen.
repl(
    "\t\t\t\tif (underlay)\n"
    "\t\t\t\t{\n"
    "\t\t\t\t\tWindow.Default.BackgroundColor = new Color(0f, 0f, 0f, 0f);\n"
    "\t\t\t\t}\n",
    "\t\t\t\tif (underlay)\n"
    "\t\t\t\t{\n"
    "\t\t\t\t\tWindow.Default.BackgroundColor = new Color(0f, 0f, 0f, 0f);\n"
    "\t\t\t\t\tAddBackdropPicture();\n"
    "\t\t\t\t}\n",
    "static-before-video",
)

# 2. Remove the duplicate static add and hold the static picture for 8 seconds
#    after playback starts, not 1 second.
repl(
    "\t\t\t\tif (underlay)\n"
    "\t\t\t\t{\n"
    "\t\t\t\t\tAddBackdropPicture();\n"
    "\t\t\t\t\tstartupFadeTimer = new Timer(1000u);\n",
    "\t\t\t\tif (underlay)\n"
    "\t\t\t\t{\n"
    "\t\t\t\t\tstartupFadeTimer = new Timer(8000u);\n",
    "static-fade-delay",
)

# 3. Restart the backdrop video if it ever reports finished and is not in an
#    expired fireplace hold.
repl(
    "\t\t\t\tbackdropVideo.Finished += delegate\n"
    "\t\t\t\t{\n"
    "\t\t\t\t\tVideoLog(\"finished event\");\n"
    "\t\t\t\t};\n",
    "\t\t\t\tbackdropVideo.Finished += delegate\n"
    "\t\t\t\t{\n"
    "\t\t\t\t\tVideoLog(\"finished event\");\n"
    "\t\t\t\t\ttry { if (!(fireplace && fireExpired)) { backdropVideo?.Play(); } } catch { }\n"
    "\t\t\t\t};\n",
    "finished-restart",
)

# 4. Drive the clock and widget time from the system every second.
repl(
    "\t\tclockTimer = new Timer(10000u);\n",
    "\t\tclockTimer = new Timer(1000u);\n",
    "clock-timer",
)

# 5. Raise the window and replay the video a few times after cold start so the
#    launcher is visible without pressing Home.
repl(
    "\t\tclockTimer.Start();\n"
    "\t\tBuildFireHints();\n",
    "\t\tclockTimer.Start();\n"
    "\t\tstartupRaiseTimer = new Timer(1500u);\n"
    "\t\tint startupRaises = 0;\n"
    "\t\tstartupRaiseTimer.Tick += delegate\n"
    "\t\t{\n"
    "\t\t\ttry { Window.Default.Raise(); Window.Default.Activate(); } catch { }\n"
    "\t\t\ttry { if (!(fireplace && fireExpired)) { backdropVideo?.Play(); } } catch { }\n"
    "\t\t\treturn ++startupRaises < 4;\n"
    "\t\t};\n"
    "\t\tstartupRaiseTimer.Start();\n"
    "\t\tBuildFireHints();\n",
    "startup-raise",
)

# 6. Raise and activate on resume as well.
repl(
    "\t\ttry { if (!(fireplace && fireExpired)) { backdropVideo?.Play(); } if (fireplace && !fireExpired) { LockDisplay(); } } catch { }\n",
    "\t\ttry { Window.Default.Raise(); Window.Default.Activate(); } catch { }\n"
    "\t\ttry { if (!(fireplace && fireExpired)) { backdropVideo?.Play(); } if (fireplace && !fireExpired) { LockDisplay(); } } catch { }\n",
    "resume-raise",
)

# 7. Weather has its own status text; the clock and date never wait for it.
repl(
    "\t\twidgetPlace.Text = flag ? weatherPlace : \"\";\n",
    "\t\tif (weatherBusy)\n"
    "\t\t{\n"
    "\t\t\twidgetPlace.Text = flag ? \"Refreshing weather...\" : \"Retrieving weather...\";\n"
    "\t\t}\n"
    "\t\telse\n"
    "\t\t{\n"
    "\t\t\twidgetPlace.Text = flag ? weatherPlace : \"Weather unavailable\";\n"
    "\t\t}\n",
    "weather-status",
)

p.write_text(s)
print("patched", p)
