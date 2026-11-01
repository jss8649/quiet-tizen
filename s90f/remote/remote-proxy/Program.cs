using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

namespace RemoteProxy
{
    internal static class Program
    {
        private const int O_RDONLY = 0x0;
        private const int O_WRONLY = 0x1;
        private const int O_NONBLOCK = 0x800;

        private const uint UI_SET_EVBIT = 0x40045564;
        private const uint UI_SET_KEYBIT = 0x40045565;
        private const uint UI_SET_RELBIT = 0x40045566;
        private const uint UI_DEV_SETUP = 0x405C5503;
        private const uint UI_DEV_CREATE = 0x5501;
        private const uint UI_DEV_DESTROY = 0x5502;

        private const uint EVIOCGNAME_256 = 0x81004506;
        private const uint EVIOCGPHYS_256 = 0x81004507;
        private const uint EVIOCGRAB = 0x40044590;

        private const ushort EV_SYN = 0x00;
        private const ushort EV_KEY = 0x01;
        private const ushort EV_REL = 0x02;
        private const ushort EV_MSC = 0x04;

        private const ushort KEY_YOUTUBE = 529;
        private const ushort KEY_TVPLUS = 560;

        private static readonly Dictionary<ushort, string> Map = new Dictionary<ushort, string>
        {
            { KEY_YOUTUBE, "9Ur5IzDKqV.TizenYouTube" },
            { KEY_TVPLUS, "rTn6ClEurC.Jellyfin" },
        };

        private static readonly HashSet<string> DeviceNames = new HashSet<string>
        {
            "Smart Control",
            "Smart Control 2016",
            "Remote-Input(Keyboard)",
        };

        private static readonly HashSet<string> Grabbed = new HashSet<string>();
        private static readonly object OutLock = new object();
        private static readonly object GrabLock = new object();

        private static int outFd = -1;
        private static string outPath = null;

        [StructLayout(LayoutKind.Sequential)]
        private struct InputId
        {
            public ushort bustype;
            public ushort vendor;
            public ushort product;
            public ushort version;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        private struct UinputSetup
        {
            public InputId id;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 80)]
            public string name;
            public uint ff_effects_max;
        }

        [DllImport("libc", SetLastError = true)]
        private static extern int open(string path, int flags);

        [DllImport("libc", SetLastError = true)]
        private static extern int close(int fd);

        [DllImport("libc", SetLastError = true)]
        private static extern IntPtr read(int fd, byte[] buffer, UIntPtr count);

        [DllImport("libc", SetLastError = true)]
        private static extern IntPtr write(int fd, byte[] buffer, UIntPtr count);

        [DllImport("libc", SetLastError = true)]
        private static extern int ioctl(int fd, UIntPtr request, int arg);

        [DllImport("libc", SetLastError = true)]
        private static extern int ioctl(int fd, UIntPtr request, byte[] arg);

        [DllImport("libc", SetLastError = true)]
        private static extern int ioctl(int fd, UIntPtr request, ref UinputSetup arg);

        private static void Log(string message)
        {
            Console.WriteLine(DateTime.UtcNow.ToString("HH:mm:ss") + " " + message);
            Console.Out.Flush();
        }

        private static int CreateOutput()
        {
            int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
            if (fd < 0)
            {
                Log("open /dev/uinput failed errno " + Marshal.GetLastWin32Error());
                return -1;
            }
            ioctl(fd, new UIntPtr(UI_SET_EVBIT), EV_KEY);
            ioctl(fd, new UIntPtr(UI_SET_EVBIT), EV_SYN);
            ioctl(fd, new UIntPtr(UI_SET_EVBIT), EV_MSC);
            ioctl(fd, new UIntPtr(UI_SET_EVBIT), EV_REL);
            for (int i = 0; i <= 767; i++)
            {
                ioctl(fd, new UIntPtr(UI_SET_KEYBIT), i);
            }
            for (int i = 0; i < 16; i++)
            {
                ioctl(fd, new UIntPtr(UI_SET_RELBIT), i);
            }
            UinputSetup setup = new UinputSetup();
            setup.id = new InputId { bustype = 0x06, vendor = 0, product = 0, version = 1 };
            setup.name = "Smart Control";
            setup.ff_effects_max = 0;
            int rc = ioctl(fd, new UIntPtr(UI_DEV_SETUP), ref setup);
            if (rc < 0)
            {
                Log("UI_DEV_SETUP failed errno " + Marshal.GetLastWin32Error());
            }
            rc = ioctl(fd, new UIntPtr(UI_DEV_CREATE), 0);
            if (rc < 0)
            {
                Log("UI_DEV_CREATE failed errno " + Marshal.GetLastWin32Error());
            }
            Thread.Sleep(300);
            return fd;
        }

        private static string DeviceName(int fd)
        {
            byte[] buffer = new byte[256];
            int rc = ioctl(fd, new UIntPtr(EVIOCGNAME_256), buffer);
            if (rc <= 0)
            {
                return null;
            }
            int end = Array.IndexOf(buffer, (byte)0);
            if (end < 0)
            {
                end = buffer.Length;
            }
            return System.Text.Encoding.ASCII.GetString(buffer, 0, end);
        }

        private static string DevicePhys(int fd)
        {
            byte[] buffer = new byte[256];
            int rc = ioctl(fd, new UIntPtr(EVIOCGPHYS_256), buffer);
            if (rc <= 0)
            {
                return "";
            }
            int end = Array.IndexOf(buffer, (byte)0);
            if (end < 0)
            {
                end = buffer.Length;
            }
            return System.Text.Encoding.ASCII.GetString(buffer, 0, end);
        }

        private static string FindOutputPath()
        {
            for (int i = 0; i < 64; i++)
            {
                string path = "/dev/input/event" + i;
                int fd = open(path, O_RDONLY | O_NONBLOCK);
                if (fd < 0)
                {
                    continue;
                }
                string name = DeviceName(fd);
                string phys = DevicePhys(fd);
                close(fd);
                if (name == "Smart Control" && string.IsNullOrEmpty(phys))
                {
                    return path;
                }
            }
            return null;
        }

        private static void Forward(byte[] ev)
        {
            lock (OutLock)
            {
                if (outFd >= 0)
                {
                    write(outFd, ev, new UIntPtr((uint)ev.Length));
                }
            }
        }

        private static void Launch(string appId)
        {
            try
            {
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = "/usr/bin/app_launcher";
                info.Arguments = "--user 5001 -s " + appId;
                info.UseShellExecute = false;
                Process.Start(info);
                Log("launch " + appId);
            }
            catch (Exception ex)
            {
                Log("launch failed " + appId + ": " + ex.Message);
            }
        }

        private static void Reader(int fd, string path)
        {
            byte[] buffer = new byte[16];
            HashSet<ushort> down = new HashSet<ushort>();
            Log("reader start " + path);
            while (true)
            {
                IntPtr n = read(fd, buffer, new UIntPtr((uint)buffer.Length));
                if (n.ToInt64() != buffer.Length)
                {
                    int errno = Marshal.GetLastWin32Error();
                    if (errno == 4 || errno == 11)
                    {
                        Thread.Sleep(10);
                        continue;
                    }
                    Log("reader end " + path + " errno " + errno);
                    break;
                }
                ushort type = BitConverter.ToUInt16(buffer, 8);
                ushort code = BitConverter.ToUInt16(buffer, 10);
                int value = BitConverter.ToInt32(buffer, 12);
                bool consume = false;
                if (type == EV_KEY && Map.ContainsKey(code))
                {
                    if (value == 1)
                    {
                        if (!down.Contains(code))
                        {
                            down.Add(code);
                            Launch(Map[code]);
                        }
                    }
                    else if (value == 0)
                    {
                        down.Remove(code);
                    }
                    consume = true;
                }
                if (!consume)
                {
                    Forward(buffer);
                }
            }
            close(fd);
            lock (GrabLock)
            {
                Grabbed.Remove(path);
            }
        }

        private static void Enumerate()
        {
            for (int i = 0; i < 64; i++)
            {
                string path = "/dev/input/event" + i;
                if (path == outPath)
                {
                    continue;
                }
                lock (GrabLock)
                {
                    if (Grabbed.Contains(path))
                    {
                        continue;
                    }
                }
                int fd = open(path, O_RDONLY);
                if (fd < 0)
                {
                    continue;
                }
                string name = DeviceName(fd);
                if (name == null || !DeviceNames.Contains(name))
                {
                    close(fd);
                    continue;
                }
                int rc = ioctl(fd, new UIntPtr(EVIOCGRAB), 1);
                if (rc < 0)
                {
                    Log("grab failed " + path + " " + name + " errno " + Marshal.GetLastWin32Error());
                    close(fd);
                    continue;
                }
                lock (GrabLock)
                {
                    Grabbed.Add(path);
                }
                Log("grabbed " + path + " " + name);
                Thread thread = new Thread(() => Reader(fd, path));
                thread.IsBackground = true;
                thread.Start();
            }
        }

        public static int Main(string[] args)
        {
            Log("remote-proxy start");
            outFd = CreateOutput();
            if (outFd < 0)
            {
                return 1;
            }
            outPath = FindOutputPath();
            Log("output device " + (outPath ?? "unknown"));
            while (true)
            {
                Enumerate();
                Thread.Sleep(500);
            }
        }
    }
}
