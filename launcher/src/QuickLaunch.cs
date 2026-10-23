using System;
using System.IO;
using System.Runtime.InteropServices;
using Tizen.NUI;
using Tizen.Applications;
// The vendor boot unit expects this application to accept its preload request.
// Acknowledge it and exit; interactive requests open the existing Quiet Home process.
// An explicit native-settings request temporarily translates directional keys.
// QuickLaunch's existing keygrab privilege is required; Home's container lacks it.
public sealed class QuickLaunch : NUIApplication {
 [DllImport("libautoinput.so.0")] static extern int VirtualKey_Initialize(string name);
 [DllImport("libautoinput.so.0")] static extern void VirtualKey_Finalize();
 [DllImport("libautoinput.so.0")] static extern void VirtualKey_Send_KeyCode(int code,int state);
 // DALi/X11 directional key codes. Generated keypad equivalents are not grabbed.
 readonly int[] arrows={111,116,113,114};
 Tizen.NUI.Timer nativeTimer;
 bool inputReady,menuSeen;
 long started;
 int forwarded;
 string lastArrow="",inputError="";
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_create(out IntPtr c);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_app_id(IntPtr c,string id);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_operation(IntPtr c,string op);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_add_extra_data(IntPtr c,string key,string val);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_send_launch_request(IntPtr c,IntPtr cb,IntPtr data);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_destroy(IntPtr c);
 protected override void OnCreate(){base.OnCreate();NUIApplication.GetDefaultWindow().Hide();}
 void InputState(string activity){try{File.WriteAllText("/tmp/quiet-native-input.txt",DateTime.UtcNow.ToString("o")+"\nactivity="+activity+"\nready="+inputReady+"\nforwarded="+forwarded+"\nlast_arrow="+lastArrow+"\nerror="+inputError+"\n");}catch{}}
 void StopInput(){
  nativeTimer?.Stop();
  if(inputReady){inputReady=false;foreach(int code in arrows)NUIApplication.GetDefaultWindow().UngrabKey(code);VirtualKey_Finalize();}
  InputState("stopped");
 }
 void StartInput(){
  if(inputReady)return;
  var window=NUIApplication.GetDefaultWindow();
  window.Title="Quiet Settings Input";window.BackgroundColor=Color.Transparent;window.SetAcceptFocus(false);
  if(VirtualKey_Initialize("Quiet settings arrows")!=1){inputError="input initialization failed";InputState("failed");Exit();return;}
  inputReady=true;
  foreach(int code in arrows){if(!window.GrabKey(code,Window.KeyGrabMode.OverrideExclusive)){inputError="key capture failed: "+code;StopInput();Exit();return;}}
  window.KeyEvent+=(s,k)=>{
   if(!inputReady||k.Key==null||k.Key.State!=Key.StateType.Down)return;
   string name=k.Key.KeyPressedName;
   int code=name=="Up"?80:name=="Down"?88:name=="Left"?83:name=="Right"?85:0;
   if(code==0)return;
   // State 2 sends a complete press/release, including for repeated remote keys.
   VirtualKey_Send_KeyCode(code,2);lastArrow=name;forwarded++;InputState("forwarded");
  };
  started=Environment.TickCount64;menuSeen=false;
  nativeTimer=new Tizen.NUI.Timer(400);
  nativeTimer.Tick+=(s,e)=>{
   try{using(var context=new ApplicationRunningContext("org.tizen.menu")){
    if(context.State.ToString()=="Foreground"){menuSeen=true;return true;}
    if(!menuSeen&&Environment.TickCount64-started<5000)return true;
   }}catch{}
   StopInput();Exit();return false;
  };
  nativeTimer.Start();InputState("ready");
 }
 protected override void OnTerminate(){StopInput();base.OnTerminate();}
 protected override void OnAppControlReceived(AppControlReceivedEventArgs e){
  base.OnAppControlReceived(e);string mode;
  if(e.ReceivedAppControl.ExtraData.TryGet("quiet_native_arrows",out mode)&&mode=="enable"){StartInput();return;}
  StopInput();string kind;bool preload=e.ReceivedAppControl.ExtraData.TryGet("launch_type",out kind)&&kind=="preload";
  int result=0;
  if(!preload){IntPtr c;result=app_control_create(out c);if(result==0){try{
   result=app_control_set_app_id(c,"com.samsung.tv.bixby-promotion");
   if(result==0)result=app_control_set_operation(c,"http://tizen.org/appcontrol/operation/default");
   if(result==0)result=app_control_add_extra_data(c,"quiet_page","settings");
   if(result==0)result=app_control_send_launch_request(c,IntPtr.Zero,IntPtr.Zero);
  }finally{app_control_destroy(c);}}}
  try{File.WriteAllText("/tmp/quiet-home-bridge.txt",DateTime.UtcNow.ToString("o")+"\npreload="+preload+"\nresult="+result+"\n");}catch{}
  Exit();
 }
 public static void Main(string[] args){using(var app=new QuickLaunch())app.Run(args);}
}
