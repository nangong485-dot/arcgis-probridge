using System;
using System.Diagnostics;
using System.Net.Sockets;
using System.Threading.Tasks;
using System.Windows.Controls;
using Microsoft.Web.WebView2.Core;

namespace ProBridge
{
    /// <summary>
    /// Hosts the local agent UI inside Pro. The page is served by
    /// agent/agent_server.py, which is started automatically if it is not running.
    /// </summary>
    public partial class AgentPaneView : UserControl
    {
        private const string Url = "http://127.0.0.1:7799/";
        private bool _loaded;

        public AgentPaneView()
        {
            InitializeComponent();
            Loaded += OnLoaded;
        }

        private async void OnLoaded(object sender, System.Windows.RoutedEventArgs e)
        {
            if (_loaded) return;
            _loaded = true;

            await EnsureAgentServerAsync();

            try
            {
                // Pro lives under Program Files, so WebView2's default user-data
                // folder is not writable there and initialisation takes Pro down
                // with it. Point it at LocalAppData instead.
                var userData = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "ProBridge", "WebView2");
                System.IO.Directory.CreateDirectory(userData);

                var env = await CoreWebView2Environment.CreateAsync(null, userData);
                await Browser.EnsureCoreWebView2Async(env);
                Browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
                Browser.CoreWebView2.Settings.IsStatusBarEnabled = false;
                Browser.Source = new Uri(Url);
            }
            catch (Exception ex)
            {
                Browser.NavigateToString(
                    "<html><body style='font:13px Microsoft YaHei;padding:16px;color:#d03050'>" +
                    "WebView2 初始化失败：" + ex.Message + "</body></html>");
            }
        }

        private static bool PortOpen(int port)
        {
            try
            {
                using (var client = new TcpClient())
                {
                    var task = client.ConnectAsync("127.0.0.1", port);
                    return task.Wait(400) && client.Connected;
                }
            }
            catch
            {
                return false;
            }
        }

        private static async Task EnsureAgentServerAsync()
        {
            if (PortOpen(7799)) return;

            var script = FindAgentScript();
            if (script == null) return;

            var python = @"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\pythonw.exe";
            if (!System.IO.File.Exists(python)) return;

            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = python,
                    Arguments = "\"" + script + "\"",
                    WorkingDirectory = System.IO.Path.GetDirectoryName(
                        System.IO.Path.GetDirectoryName(script)),
                    UseShellExecute = false,
                    CreateNoWindow = true
                });
            }
            catch
            {
                return;
            }

            for (var i = 0; i < 30; i++)
            {
                await Task.Delay(200);
                if (PortOpen(7799)) return;
            }
        }

        private static string FindAgentScript()
        {
            var home = Environment.GetEnvironmentVariable("PROBRIDGE_HOME");
            if (!string.IsNullOrWhiteSpace(home))
            {
                var configured = System.IO.Path.Combine(home, "agent", "agent_server.py");
                if (System.IO.File.Exists(configured)) return configured;
            }

            var directory = new System.IO.DirectoryInfo(
                System.IO.Path.GetDirectoryName(typeof(AgentPaneView).Assembly.Location) ?? "");
            while (directory != null)
            {
                var candidate = System.IO.Path.Combine(directory.FullName, "agent", "agent_server.py");
                if (System.IO.File.Exists(candidate)) return candidate;
                directory = directory.Parent;
            }

            return null;
        }
    }
}
