using System;
using System.Runtime.InteropServices;
using System.Threading;

namespace UinputInjector
{
    internal static class Program
    {
        private const int O_WRONLY = 0x1;
        private const int O_NONBLOCK = 0x800;

        private const uint UI_SET_EVBIT = 0x40045564;
        private const uint UI_SET_KEYBIT = 0x40045565;
        private const uint UI_DEV_SETUP = 0x405C5503;
        private const uint UI_DEV_CREATE = 0x5501;
        private const uint UI_DEV_DESTROY = 0x5502;

        private const ushort EV_SYN = 0x00;
        private const ushort EV_KEY = 0x01;
        private const ushort SYN_REPORT = 0x00;

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
        private static extern int ioctl(int fd, UIntPtr request, int arg);

        [DllImport("libc", SetLastError = true)]
        private static extern int ioctl(int fd, UIntPtr request, ref UinputSetup arg);

        [DllImport("libc", SetLastError = true)]
        private static extern IntPtr write(int fd, byte[] buffer, UIntPtr count);

        private static byte[] Event(ushort type, ushort code, int value)
        {
            byte[] b = new byte[16];
            BitConverter.GetBytes(0).CopyTo(b, 0);
            BitConverter.GetBytes(0).CopyTo(b, 4);
            BitConverter.GetBytes(type).CopyTo(b, 8);
            BitConverter.GetBytes(code).CopyTo(b, 10);
            BitConverter.GetBytes(value).CopyTo(b, 12);
            return b;
        }

        private static void Emit(int fd, ushort type, ushort code, int value)
        {
            byte[] b = Event(type, code, value);
            IntPtr n = write(fd, b, new UIntPtr((uint)b.Length));
            Console.WriteLine("write {0},{1},{2} => {3}", type, code, value, n.ToInt64());
        }

        public static int Main(string[] args)
        {
            string name = "Smart Control";
            int first = 0;
            if (args.Length >= 2 && args[0] == "--name")
            {
                name = args[1];
                first = 2;
            }
            if (args.Length <= first)
            {
                Console.Error.WriteLine("usage: uinput-injector [--name NAME] keycode [keycode ...]");
                return 2;
            }

            int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
            if (fd < 0)
            {
                Console.Error.WriteLine("open /dev/uinput failed: errno " + Marshal.GetLastWin32Error());
                return 1;
            }

            int rc = ioctl(fd, new UIntPtr(UI_SET_EVBIT), EV_KEY);
            Console.WriteLine("set evbit => " + rc + " errno " + Marshal.GetLastWin32Error());
            for (int i = first; i < args.Length; i++)
            {
                int code = int.Parse(args[i]);
                rc = ioctl(fd, new UIntPtr(UI_SET_KEYBIT), code);
                Console.WriteLine("set keybit " + code + " => " + rc + " errno " + Marshal.GetLastWin32Error());
            }

            UinputSetup setup = new UinputSetup();
            setup.id = new InputId { bustype = 0x06, vendor = 0, product = 0, version = 1 };
            setup.name = name;
            setup.ff_effects_max = 0;
            rc = ioctl(fd, new UIntPtr(UI_DEV_SETUP), ref setup);
            Console.WriteLine("dev setup => " + rc + " errno " + Marshal.GetLastWin32Error());
            rc = ioctl(fd, new UIntPtr(UI_DEV_CREATE), 0);
            Console.WriteLine("dev create => " + rc + " errno " + Marshal.GetLastWin32Error());
            Thread.Sleep(4000);

            for (int i = first; i < args.Length; i++)
            {
                ushort code = (ushort)int.Parse(args[i]);
                Console.WriteLine("inject " + code);
                Emit(fd, EV_KEY, code, 1);
                Emit(fd, EV_SYN, SYN_REPORT, 0);
                Thread.Sleep(150);
                Emit(fd, EV_KEY, code, 0);
                Emit(fd, EV_SYN, SYN_REPORT, 0);
                Thread.Sleep(700);
            }

            Thread.Sleep(300);
            ioctl(fd, new UIntPtr(UI_DEV_DESTROY), 0);
            close(fd);
            Console.WriteLine("done");
            return 0;
        }
    }
}
