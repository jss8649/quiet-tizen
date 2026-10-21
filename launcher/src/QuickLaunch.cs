using System;
using System.IO;
using System.Runtime.InteropServices;
using Tizen.NUI;
using Tizen.Applications;
// The vendor boot unit expects this application to accept its preload request.
// Acknowledge it and exit; interactive requests open the existing Quiet Home process.
public sealed class QuickLaunch : NUIApplication {
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_create(out IntPtr c);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_app_id(IntPtr c,string id);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_operation(IntPtr c,string op);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_add_extra_data(IntPtr c,string key,string val);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_send_launch_request(IntPtr c,IntPtr cb,IntPtr data);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_destroy(IntPtr c);
 protected override void OnCreate(){base.OnCreate();Window.Default.Hide();}
 protected override void OnAppControlReceived(AppControlReceivedEventArgs e){
  base.OnAppControlReceived(e);string kind;bool preload=e.ReceivedAppControl.ExtraData.TryGet("launch_type",out kind)&&kind=="preload";
  int result=0;
  if(!preload){IntPtr c;result=app_control_create(out c);if(result==0){try{
   result=app_control_set_app_id(c,QuietHomeContainer.AppId);
   if(result==0)result=app_control_set_operation(c,"http://tizen.org/appcontrol/operation/default");
   if(result==0)result=app_control_add_extra_data(c,"quiet_page","settings");
   if(result==0)result=app_control_send_launch_request(c,IntPtr.Zero,IntPtr.Zero);
  }finally{app_control_destroy(c);}}}
  try{File.WriteAllText("/tmp/quiet-home-bridge.txt",DateTime.UtcNow.ToString("o")+"\npreload="+preload+"\nresult="+result+"\n");}catch{}
  Exit();
 }
 public static void Main(string[] args){using(var app=new QuickLaunch())app.Run(args);}
}
