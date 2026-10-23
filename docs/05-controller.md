# Pair a PS5 DualSense natively

The tested U8000F has Bluetooth support (Samsung lists Bluetooth 5.3).
Quiet Home's **Settings → Controllers** card opens the television's native
Bluetooth device menu. No separate controller daemon is installed.

1. Disconnect the DualSense's USB cable and turn the controller off.
2. Hold **Create + PS** until the light bar flashes.
3. Open **Quiet Home → Settings → Controllers**.
4. Select **Wireless Controller** in the TV's device list and pair it.
5. Try D-pad navigation, Cross/Select and Circle/Back in Quiet Home.

Sony documents pairing mode and device support in
[DualSense Bluetooth pairing](https://www.playstation.com/en-us/support/hardware/pair-dualsense-controller-bluetooth/).
Samsung documents [TV gamepad support](https://developer.samsung.com/smarttv/accessory/gamepad.html).

Implementation: the launcher requests `org.tizen.menu` with
`menuitem=add-bluetooth-keyboard`, `launchoption=pressed`,
`__K_EX_FORCE_BOOST=enable` and the transparent splash hint. Despite the
internal “keyboard” name, this route reached the native Bluetooth list used
for the DualSense on the tested firmware.

## Native popups ignore remote arrows

On a **UN55DU6900FXZC**, software **T-KSU2EDAKUC-1400.0** (Tizen 8,
ARMv7, .NET 6.0.9), the Samsung remote could navigate the main native Settings
screen and select a paired controller, but arrows would not move between
buttons inside its Bluetooth and confirmation popups. Ordinary directional
events reached the menu process; equivalent keypad directions moved the
popup selection. The owner confirmed working popup navigation after the fix.

Quiet Home now yields keyboard focus while the native menu is open and
restores it on return. For affected firmware, an optional QuickLaunch input
bridge translates only the four directions to their keypad equivalents.
Select and Back stay with Samsung's menu. It releases its key grabs and input
device and exits when the native menu closes; normal settings-shortcut and
preload requests retain their existing behavior.

Build and install **both** updated `BixbyPromotion.dll` and `QuickLaunch.dll`,
retaining backups of both previous assemblies. Check that QuickLaunch's
existing manifest grants `http://tizen.org/privilege/keygrab` and that the
firmware provides `libautoinput.so.0`. The Home container does not have that
key-capture privilege. No additional permission or root service is needed.

Enable the workaround only on firmware exhibiting this problem:

```sh
tv exec --command 'touch /opt/usr/apps/com.samsung.tv.bixby-promotion/res/quiet-home/native-settings-keypad-arrows'
```

Remove that marker to disable translation for subsequent menu sessions.
The marker is deliberately opt-in: this translation was not tested on the
original Tizen 9 case-study TV. This report does not expand the cleanup/root
profile's model gate or establish reboot/standby compatibility for the DU6900.
The marker activation itself was added for upstream use after the owner's
hardware test; the deployed repair enabled the same bridge unconditionally.

Test with the physical remote: Down to Scan/Stop, Left/Right between bottom
buttons, and navigation inside Cancel/Unpair without confirming a device
change. Then use Back/Home and check launcher navigation. Local overwritten
state is available in `/tmp/quiet-home-focus.txt` and
`/tmp/quiet-native-input.txt`; keep these files private.

Preserve Bluetooth and gamepad services during cleanup. The TV's input stack
delivers navigation events; support within streaming and cloud-gaming apps
depends on those apps. Successful pairing does not guarantee every button,
analog input, haptic or audio feature works everywhere.

Pairing the controller to the TV does **not** pass controller input through
HDMI to a PlayStation or other console. For console gameplay, pair it with
that console. Changing between hosts may require pairing again.
